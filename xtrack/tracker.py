# copyright ############################### #
# This file is part of the Xtrack Package.  #
# Copyright (c) CERN, 2021.                 #
# ######################################### #

from time import perf_counter
from typing import Literal, Union
from contextlib import contextmanager
import logging
from functools import partial
from collections import UserDict, defaultdict

from scipy.constants import c as clight

import numpy as np
import xobjects as xo
import xpart as xp
import xtrack as xt

from .general import _print

from .base_element import _handle_per_particle_blocks
from .beam_elements import Drift
from .general import _pkg_root
from .internal_record import new_io_buffer
from .line import Line, _is_thick, freeze_longitudinal as _freeze_longitudinal
from .pipeline import PipelineStatus
from .tracker_data import TrackerData
from .prebuild_kernels import get_suitable_kernel, XT_PREBUILT_KERNELS_LOCATION

logger = logging.getLogger(__name__)


def _check_is_collective(ele):
    iscoll = not hasattr(ele, 'iscollective') or ele.iscollective
    return iscoll


class Tracker:

    '''
    Xsuite tracker class. It is the core of the xsuite package, allows tracking
    particles in a given beam line. Methods to match particle distributions
    and to compute twiss parameters are also available.
    '''

    def __init__(
        self,
        _context=None,
        _buffer=None,
        line=None,
        compile=True,
        io_buffer=None,
        use_prebuilt_kernels=True,
        enable_pipeline_hold=False,
        track_kernel=None,
        particles_class=xp.Particles,
        particles_monitor_class=None,
        extra_headers=(),
        local_particle_src=None,
    ):

        # Check if there are collective elements
        self.iscollective = False
        for ee in line.elements:
            if _check_is_collective(ee):
                self.iscollective = True
                break

        if enable_pipeline_hold and not self.iscollective:
            raise ValueError("`enable_pipeline_hold` is not implemented in "
                             "non-collective mode")

        if not compile and self.iscollective:
            raise NotImplementedError("Skip compilation is not implemented in "
                                      "collective mode")

        if particles_class is None:
            particles_class = xp.Particles

        if local_particle_src is None:
            local_particle_src = particles_class.gen_local_particle_api()

        if not particles_monitor_class:
            particles_monitor_class = self._get_default_monitor_class()

        self.line = line
        self.particles_class = particles_class
        self.particles_monitor_class = particles_monitor_class
        self.extra_headers = extra_headers
        self.local_particle_src = local_particle_src
        self._enable_pipeline_hold = enable_pipeline_hold
        self.use_prebuilt_kernels = use_prebuilt_kernels

        # Some data for collective mode prepared also for non-collective lines
        # to allow collective actions by the tracker (e.g. time-functions on knobs)
        (parts, part_names, _element_part, _element_index_in_part,
            _part_element_index, noncollective_xelements) = (
            self._split_parts_for_collective_mode(line, _buffer))

        assert len(line.element_names) == len(_element_index_in_part)
        assert len(line.element_names) == len(_element_part)
        if len(line.element_names) > 0:
            assert _element_part[-1] == len(parts) - 1
        self._parts = parts
        self._part_names = part_names
        self._element_part = _element_part
        self._element_index_in_part = _element_index_in_part

        if self.iscollective:
            # Build tracker for all non-collective elements
            # (with collective elements replaced by Drifts)
            ele_dict_non_collective = {
                nn:ee for nn, ee in zip(line.element_names, noncollective_xelements)}
        else:
            ele_dict_non_collective = line.element_dict

        tracker_data_base = TrackerData(
            allow_move=True, # Will move elements to the same buffer
            element_dict=ele_dict_non_collective,
            element_names=line.element_names,
            element_s_locations=line.get_s_elements(),
            line_length=line.get_length(),
            compound_mask=line.get_compound_mask(),
            element_compound_names=line.get_element_compound_names(),
            kernel_element_classes=None,
            extra_element_classes=(particles_monitor_class._XoStruct,),
            _context=_context,
            _buffer=_buffer)
        line._freeze()

        _buffer = tracker_data_base._buffer

        # Make a "marker" element to increase at_element
        if self.iscollective:
            self._zerodrift = Drift(_context=_buffer.context, length=0)

        self._track_kernel = track_kernel or {}
        self._tracker_data_cache = {}
        self._tracker_data_cache[None] = tracker_data_base

        self._get_twiss_mask_markers() # to cache it

        self._init_io_buffer(io_buffer)

        self.line = line
        self.line.tracker = self

        if compile:
            _ = self.get_track_kernel_and_data_for_present_config()  # This triggers compilation

    def _init_io_buffer(self, io_buffer=None):
        if io_buffer is None:
            io_buffer = new_io_buffer(_context=self._context)
        self.io_buffer = io_buffer

    def _split_parts_for_collective_mode(self, line, _buffer):

        # Split the sequence
        parts = []
        part_names = []
        _element_part = []
        _element_index_in_part=[]
        _part_element_index = defaultdict(list)
        this_part = Line(elements=[], element_names=[])
        ii_in_part = 0
        i_part = 0
        idx = 0
        for nn, ee in zip(line.element_names, line.elements):
            if not _check_is_collective(ee):
                this_part.append_element(ee, nn)
                _element_part.append(i_part)
                _element_index_in_part.append(ii_in_part)
                ii_in_part += 1
                _part_element_index[i_part].append(idx)
            else:
                if len(this_part.elements) > 0:
                    parts.append(this_part)
                    part_names.append(f'part_{i_part}_non_collective')
                    i_part += 1
                parts.append(ee)
                part_names.append(nn)
                _element_part.append(i_part)
                _element_index_in_part.append(None)
                _part_element_index[i_part].append(idx)
                i_part += 1
                this_part = Line(elements=[], element_names=[])
                ii_in_part = 0
            idx += 1
        if len(this_part.elements) > 0:
            parts.append(this_part)
            part_names.append(f'part_{i_part}_non_collective')

        # Build drifts to replace non-collective elements
        noncollective_xelements = []
        for ii, pp in enumerate(parts):
            if isinstance(pp, Line):
                noncollective_xelements += pp.elements
            else:
                if _is_thick(pp):
                    ldrift = pp.length
                else:
                    ldrift = 0.

                noncollective_xelements.append(
                    Drift(_buffer=_buffer, length=ldrift))

        # Build TrackerPartNonCollective objects for non-collective parts
        for ii, pp in enumerate(parts):
            if isinstance(pp, Line):
                ele_start = _part_element_index[ii][0]
                ele_stop = _part_element_index[ii][-1] + 1
                parts[ii] = TrackerPartNonCollective(
                    tracker=self,
                    ele_start_in_tracker=ele_start,
                    ele_stop_in_tracker=ele_stop,
                )

        return (parts, part_names, _element_part, _element_index_in_part,
                _part_element_index, noncollective_xelements)

    @property
    def track_kernel(self):
        return self._track_kernel

    @property
    def _tracker_data_base(self):
        return self._tracker_data_cache[None]

    @property
    def line_element_classes(self):
        return self._tracker_data_cache[None].line_element_classes

    @property
    def config(self):
        return self.line.config

    @property
    def _buffer(self):
        return self._tracker_data_cache[None]._buffer

    @property
    def num_elements(self):
        return len(self.line.element_names)

    @property
    def _element_dict_non_collective(self):
        return self._tracker_data_cache[None]._element_dict

    @property
    def matrix_responsiveness_tol(self):
        return self.line.matrix_responsiveness_tol

    @property
    def matrix_stability_tol(self):
        return self.line.matrix_stability_tol

    @property
    def _radiation_model(self):
        return self.line._radiation_model

    @property
    def _beamstrahlung_model(self):
        return self.line._beamstrahlung_model

    @property
    def _bhabha_model(self):
        return self.line._bhabha_model

    def _invalidate(self):
        if self.iscollective:
            self._invalidated_parts = self._parts
            self._parts = None
        else:
            self._tracker_data_cache = None
        self._is_invalidated = True

    def _check_invalidated(self):
        if hasattr(self, '_is_invalidated') and self._is_invalidated:
            raise RuntimeError(
                "This tracker is not anymore valid, most probably because the corresponding line has been unfrozen. "
                "Please rebuild the tracker, for example using `line.build_tracker(...)`.")

    def _track(self, *args, **kwargs):
        assert self.iscollective in (True, False)
        if self.iscollective or self.line.enable_time_dependent_vars:
            return self._track_with_collective(*args, **kwargs)
        else:
            return self._track_no_collective(*args, **kwargs)

    @property
    def particle_ref(self) -> xp.Particles:
        self._check_invalidated()
        return self.line.particle_ref

    @particle_ref.setter
    def particle_ref(self, value: xp.Particles):
        self.line.particle_ref = value

    @property
    def vars(self):
        self._check_invalidated()
        return self.line.vars

    @property
    def element_refs(self):
        self._check_invalidated()
        return self.line.element_refs

    @property
    def enable_pipeline_hold(self):
        return self._enable_pipeline_hold

    @enable_pipeline_hold.setter
    def enable_pipeline_hold(self, value):
        if not self.iscollective:
            raise ValueError(
                'enable_pipeline_hold is not supported non collective trackers')
        else:
            self._enable_pipeline_hold = value

    @property
    def _context(self):
        return self._buffer.context

    def _build_kernel(
            self,
            compile: Union[bool, Literal['force']],
            module_name=None,
            containing_dir='.',
    ):
        if (self.use_prebuilt_kernels and compile != 'force'
                and isinstance(self._context, xo.ContextCpu)):
            kernel_info = get_suitable_kernel(
                self.config, self.line_element_classes
            )
            if kernel_info:
                module_name, modules_classes = kernel_info

                kernel_description = self.get_kernel_descriptions(
                                            modules_classes)['track_line']
                kernels = self._context.kernels_from_file(
                    module_name=module_name,
                    containing_dir=XT_PREBUILT_KERNELS_LOCATION,
                    kernel_descriptions={'track_line': kernel_description},
                )
                classes = (self.particles_class._XoStruct,)

                return kernels[('track_line', classes)]

        context = self._tracker_data_base._buffer.context

        kernel_element_classes = self._tracker_data_base.kernel_element_classes

        headers = []

        headers.extend(self.extra_headers)
        headers.append(_pkg_root.joinpath("headers/constants.h"))

        src_lines = []
        src_lines.append(
            r"""
            /*gpukern*/
            void track_line(
                /*gpuglmem*/ int8_t* buffer,
                             ElementRefData elem_ref_data,
                             ParticlesData particles,
                             int num_turns,
                             int ele_start,
                             int num_ele_track,
                             int flag_end_turn_actions,
                             int flag_reset_s_at_end_turn,
                             int flag_monitor,
                             int num_ele_line,
                             double line_length,
                /*gpuglmem*/ int8_t* buffer_tbt_monitor,
                             int64_t offset_tbt_monitor,
                /*gpuglmem*/ int8_t* io_buffer){

            const int64_t capacity = ParticlesData_get__capacity(particles);               //only_for_context cpu_openmp
            const int num_threads = omp_get_max_threads();                                 //only_for_context cpu_openmp
            const int64_t chunk_size = (capacity + num_threads - 1)/num_threads; // ceil division  //only_for_context cpu_openmp
            #pragma omp parallel for                                                       //only_for_context cpu_openmp
            for (int chunk = 0; chunk < num_threads; chunk++) {                            //only_for_context cpu_openmp
            int64_t part_id = chunk * chunk_size;                                          //only_for_context cpu_openmp
            int64_t end_id = (chunk + 1) * chunk_size;                                     //only_for_context cpu_openmp
            if (end_id > capacity) end_id = capacity;                                      //only_for_context cpu_openmp

            int64_t part_id = 0;                                      //only_for_context cpu_serial
            int64_t part_id = blockDim.x * blockIdx.x + threadIdx.x;  //only_for_context cuda
            int64_t part_id = get_global_id(0);                       //only_for_context opencl
            int64_t end_id = 0; // unused outside of openmp  //only_for_context cpu_serial cuda opencl

            LocalParticle lpart;
            lpart.io_buffer = io_buffer;

            /*gpuglmem*/ int8_t* tbt_mon_pointer =
                            buffer_tbt_monitor + offset_tbt_monitor;
            ParticlesMonitorData tbt_monitor =
                            (ParticlesMonitorData) tbt_mon_pointer;

            int64_t part_capacity = ParticlesData_get__capacity(particles);
            if (part_id<part_capacity){
            Particles_to_LocalParticle(particles, &lpart, part_id, end_id);

            int64_t isactive = check_is_active(&lpart);

            for (int64_t iturn=0; iturn<num_turns; iturn++){

                if (!isactive){
                    break;
                }

                int64_t const ele_stop = ele_start + num_ele_track;

                #ifndef XSUITE_BACKTRACK
                if (flag_monitor==1){
                    ParticlesMonitor_track_local_particle(tbt_monitor, &lpart);
                }
                int64_t elem_idx = ele_start;
                int64_t const increm = 1;
                #else
                int64_t elem_idx = ele_stop - 1;
                int64_t const increm = -1;
                if (flag_end_turn_actions>0){
                    increment_at_turn_backtrack(&lpart, flag_reset_s_at_end_turn,
                                                line_length, num_ele_line);
                }
                #endif

                for (; ((elem_idx >= ele_start) && (elem_idx < ele_stop)); elem_idx+=increm){
                        if (flag_monitor==2){
                            ParticlesMonitor_track_local_particle(tbt_monitor, &lpart);
                        }

                        // Get the pointer to and the type id of the `elem_idx`th
                        // element in `element_ref_data.elements`:
                        /*gpuglmem*/ void* el = ElementRefData_member_elements(elem_ref_data, elem_idx);
                        int64_t elem_type = ElementRefData_typeid_elements(elem_ref_data, elem_idx);

                        switch(elem_type){
        """
        )

        for ii, cc in enumerate(kernel_element_classes):
            ccnn = cc.__name__.replace("Data", "")
            src_lines.append(
                f"""
                        case {ii}:
"""
            )
            if ccnn == "Drift":
                src_lines.append(
                    """
                            #ifdef XTRACK_GLOBAL_XY_LIMIT
                            global_aperture_check(&lpart);
                            #endif

                            """
                )
            src_lines.append(
                f"""
                            {ccnn}_track_local_particle(({ccnn}Data) el, &lpart);
                            break;"""
            )

        src_lines.append(
            r"""
                        } //switch

                    // Setting the below flag will break particle losses
                    #ifndef DANGER_SKIP_ACTIVE_CHECK_AND_SWAPS

                    isactive = check_is_active(&lpart);
                    if (!isactive){
                        break;
                    }

                    #ifndef XSUITE_BACKTRACK
                        increment_at_element(&lpart, 1);
                    #else
                        increment_at_element(&lpart, -1);
                    #endif //XSUITE_BACKTRACK

                    #endif //DANGER_SKIP_ACTIVE_CHECK_AND_SWAPS

                } // for elements

                if (flag_monitor==2){
                    // End of turn (element-by-element mode)
                    ParticlesMonitor_track_local_particle(tbt_monitor, &lpart);
                }

                #ifndef XSUITE_BACKTRACK
                if (flag_end_turn_actions>0){
                    if (isactive){
                        increment_at_turn(&lpart, flag_reset_s_at_end_turn);
                    }
                }
                #endif //XSUITE_BACKTRACK


                #ifdef XSUITE_BACKTRACK
                if (flag_monitor==1){
                    ParticlesMonitor_track_local_particle(tbt_monitor, &lpart);
                }
                #endif //XSUITE_BACKTRACK
            } // for turns

            LocalParticle_to_Particles(&lpart, particles, part_id, 1);

            }// if partid
            } //only_for_context cpu_openmp

            // On OpenMP we want to additionally by default reorganize all
            // the particles.
            #ifndef XT_OMP_SKIP_REORGANIZE                             //only_for_context cpu_openmp
            LocalParticle lpart;                                       //only_for_context cpu_openmp
            lpart.io_buffer = io_buffer;                               //only_for_context cpu_openmp
            Particles_to_LocalParticle(particles, &lpart, 0, capacity);//only_for_context cpu_openmp
            check_is_active(&lpart);                                   //only_for_context cpu_openmp
            count_reorganized_particles(&lpart);                       //only_for_context cpu_openmp
            LocalParticle_to_Particles(&lpart, particles, 0, capacity);//only_for_context cpu_openmp
            #endif                                                     //only_for_context cpu_openmp
        }//kernel
        """
        )

        source_track = "\n".join(src_lines)

        kernels = self.get_kernel_descriptions(kernel_element_classes)

        # Compile!
        if isinstance(self._context, xo.ContextCpu):
            kwargs = {
                'containing_dir': containing_dir,
                'module_name': module_name,
            }
        else:
            # Saving kernels is unsupported on GPU
            kwargs = {}

        out_kernels = context.build_kernels(
            sources=[source_track],
            kernel_descriptions=kernels,
            extra_headers=self._config_to_headers() + headers,
            extra_classes=kernel_element_classes,
            apply_to_source=[
                partial(_handle_per_particle_blocks,
                        local_particle_src=self.local_particle_src)],
            specialize=True,
            compile=compile,
            save_source_as=f'{module_name}.c' if module_name else None,
            **kwargs,
        )

        classes = (self.particles_class._XoStruct,)
        return out_kernels[('track_line', classes)]

    def get_kernel_descriptions(self, kernel_element_classes):

        tdata_type = _element_ref_data_class_from_element_classes(
            kernel_element_classes)

        kernel_descriptions = {
            "track_line": xo.Kernel(
                c_name='track_line',
                args=[
                    xo.Arg(xo.Int8, pointer=True, name="buffer"),
                    xo.Arg(tdata_type, name="tracker_data"),
                    xo.Arg(self.particles_class._XoStruct, name="particles"),
                    xo.Arg(xo.Int32, name="num_turns"),
                    xo.Arg(xo.Int32, name="ele_start"),
                    xo.Arg(xo.Int32, name="num_ele_track"),
                    xo.Arg(xo.Int32, name="flag_end_turn_actions"),
                    xo.Arg(xo.Int32, name="flag_reset_s_at_end_turn"),
                    xo.Arg(xo.Int32, name="flag_monitor"),
                    xo.Arg(xo.Int32, name='num_ele_line'),
                    xo.Arg(xo.Float64, name='line_length'),
                    xo.Arg(xo.Int8, pointer=True, name="buffer_tbt_monitor"),
                    xo.Arg(xo.Int64, name="offset_tbt_monitor"),
                    xo.Arg(xo.Int8, pointer=True, name="io_buffer"),
                ],
            )
        }

        # Random number generator init kernel
        kernel_descriptions.update(self.particles_class._kernels)

        return kernel_descriptions

    def _prepare_collective_track_session(self, particles, ele_start, ele_stop,
                                       num_elements, num_turns, turn_by_turn_monitor):

        # Start position
        if particles.start_tracking_at_element >= 0:
            if ele_start != 0:
                raise ValueError("The argument ele_start is used, but particles.start_tracking_at_element is set as well. "
                                 "Please use only one of those methods.")
            ele_start = particles.start_tracking_at_element
            particles.start_tracking_at_element = -1
        if isinstance(ele_start, str):
            ele_start = self.line.element_names.index(ele_start)

        # ele_start can only have values of existing element id's,
        # but also allowed: all elements+1 (to perform end-turn actions)
        assert ele_start >= 0
        assert ele_start < self.num_elements

        # Stop position
        if num_elements is not None:
            # We are using ele_start and num_elements
            if ele_stop is not None:
                raise ValueError("Cannot use both num_elements and ele_stop!")
            if num_turns is not None:
                raise ValueError("Cannot use both num_elements and num_turns!")
            num_turns, ele_stop = np.divmod(ele_start + num_elements, self.num_elements)
            if ele_stop == 0:
                ele_stop = None
            else:
                num_turns += 1
        else:
            # We are using ele_start, ele_stop, and num_turns
            if num_turns is None:
                num_turns = 1
            else:
                assert num_turns > 0
            if isinstance(ele_stop,str):
                ele_stop = self.line.element_names.index(ele_stop)

            # If ele_stop comes before ele_start, we need to add an additional turn to
            # reach the required ele_stop
            if ele_stop == 0:
                ele_stop = None

            if ele_stop is not None and ele_stop <= ele_start:
                num_turns += 1

        if ele_stop is not None:
            assert ele_stop >= 0
            assert ele_stop < self.num_elements

        assert num_turns >= 1

        assert turn_by_turn_monitor != 'ONE_TURN_EBE', (
            "Element-by-element monitor not available in collective mode")

        (flag_monitor, monitor, buffer_monitor, offset_monitor
            ) = self._get_monitor(particles, turn_by_turn_monitor, num_turns)

        if particles._num_active_particles < 0:
            _context_needs_clean_active_lost_state = True
        else:
            _context_needs_clean_active_lost_state = False

        if self.line._needs_rng and not particles._has_valid_rng_state():
            particles._init_random_number_generator()

        return (ele_start, ele_stop, num_turns, flag_monitor, monitor,
                buffer_monitor, offset_monitor,
                _context_needs_clean_active_lost_state)

    def _prepare_particles_for_part(self, particles, pp,
                                    moveback_to_buffer, moveback_to_offset,
                                    _context_needs_clean_active_lost_state):
        if hasattr(self, '_slice_sets'):
            # If pyheadtail object, remove any stored slice sets
            # (they are made invalid by the xtrack elements changing zeta)
            self._slice_sets = {}

        if (hasattr(pp, 'needs_cpu') and pp.needs_cpu):
            # Move to CPU if not already there
            if (moveback_to_buffer is None
                and not isinstance(particles._buffer.context, xo.ContextCpu)):
                moveback_to_buffer = particles._buffer
                moveback_to_offset = particles._offset
                particles.move(_context=xo.ContextCpu())
                particles.reorganize()
        else:
            # Move to GPU if not already there
            if moveback_to_buffer is not None:
                particles.move(_buffer=moveback_to_buffer, _offset=moveback_to_offset)
                moveback_to_buffer = None
                moveback_to_offset = None
                if _context_needs_clean_active_lost_state:
                    particles._num_active_particles = -1
                    particles._num_lost_particles = -1

        # Hide lost particles if required by element
        _need_unhide_lost_particles = False
        if (hasattr(pp, 'needs_hidden_lost_particles')
            and pp.needs_hidden_lost_particles):
            if not particles.lost_particles_are_hidden:
                _need_unhide_lost_particles = True
            particles.hide_lost_particles()

        return _need_unhide_lost_particles, moveback_to_buffer, moveback_to_offset

    def _track_part(self, particles, pp, tt, ipp, ele_start, ele_stop, num_turns):
        ret = None
        skip = False
        stop_tracking = False
        if tt == 0 and ipp < self._element_part[ele_start]:
            # Do not track before ele_start in the first turn
            skip = True

        elif tt == 0 and self._element_part[ele_start] == ipp:
            # We are in the part that contains the start element
            i_start_in_part = self._element_index_in_part[ele_start]
            if i_start_in_part is None:
                # The start part is collective
                ret = pp.track(particles)
            else:
                # The start part is a non-collective tracker
                if (ele_stop is not None
                    and tt == num_turns - 1 and self._element_part[ele_stop] == ipp):
                    # The stop element is also in this part, so track until ele_stop
                    i_stop_in_part = self._element_index_in_part[ele_stop]
                    ret = pp.track(particles, ele_start=i_start_in_part, ele_stop=i_stop_in_part)
                    stop_tracking = True
                else:
                    # Track until end of part
                    ret = pp.track(particles, ele_start=i_start_in_part)

        elif (ele_stop is not None
                and tt == num_turns-1 and self._element_part[ele_stop] == ipp):
            # We are in the part that contains the stop element
            i_stop_in_part = self._element_index_in_part[ele_stop]
            if i_stop_in_part is not None:
                # If not collective, track until ele_stop
                ret = pp.track(particles, num_elements=i_stop_in_part)
            stop_tracking = True

        else:
            # We are in between the part that contains the start element,
            # and the one that contains the stop element, so track normally
            ret = pp.track(particles)

        return stop_tracking, skip, ret

    def resume(self, session):
        """
        Resume a track session that had been placed on hold.
        """
        return self._track_with_collective(particles=None, _session_to_resume=session)

    def _track_with_collective(
        self,
        particles,
        ele_start=None,
        ele_stop=None,     # defaults to full lattice
        num_elements=None, # defaults to full lattice
        num_turns=None,    # defaults to 1
        turn_by_turn_monitor=None,
        freeze_longitudinal=False,
        backtrack=False,
        time=False,
        _session_to_resume=None
    ):

        if time:
            t0 = perf_counter()

        if ele_start is None:
            ele_start = 0

        if freeze_longitudinal:
            raise NotImplementedError('freeze_longitudinal not implemented yet'
                                      ' for collective tracking')

        if backtrack:
            raise NotImplementedError('backtrack not available for collective'
                                      ' tracking')

        self._check_invalidated()

        if (isinstance(self._buffer.context, xo.ContextCpu)
                and _session_to_resume is None):
            if not (particles._num_active_particles >= 0 and
                    particles._num_lost_particles >= 0):
                raise ValueError("Particles state is not valid to run on CPU, "
                                 "please call `particles.reorganize()` first.")

        if _session_to_resume is not None:
            if isinstance(_session_to_resume, PipelineStatus):
                _session_to_resume = _session_to_resume.data

            assert not(_session_to_resume['resumed']), (
                "This session hase been already resumed")

            assert _session_to_resume['tracker'] is self, (
                "This session was not created by this tracker")

            ele_start = _session_to_resume['ele_start']
            ele_stop = _session_to_resume['ele_stop']
            num_turns = _session_to_resume['num_turns']
            flag_monitor = _session_to_resume['flag_monitor']
            monitor = _session_to_resume['monitor']
            _context_needs_clean_active_lost_state = _session_to_resume[
                                    '_context_needs_clean_active_lost_state']
            tt_resume = _session_to_resume['tt']
            ipp_resume = _session_to_resume['ipp']
            _session_to_resume['resumed'] = True
        else:
            (ele_start, ele_stop, num_turns, flag_monitor, monitor,
                buffer_monitor, offset_monitor,
                _context_needs_clean_active_lost_state
                ) = self._prepare_collective_track_session(
                                particles, ele_start, ele_stop,
                                num_elements, num_turns, turn_by_turn_monitor)
            tt_resume = None
            ipp_resume = None

        for tt in range(num_turns):
            if tt_resume is not None and tt < tt_resume:
                continue

            if (flag_monitor and (ele_start == 0 or tt>0)): # second condition is for delayed start
                if not(tt_resume is not None and tt == tt_resume):
                    monitor.track(particles)

            if self.line.enable_time_dependent_vars:
                # Find first active particle
                state = particles.state
                if isinstance(particles._context, xo.ContextPyopencl):
                    state = state.get()
                ii_first_active = int((state > 0).argmax())
                if ii_first_active == 0 and particles._xobject.state[0] <= 0:
                    # No active particles
                    break

                # Needs to be generalized for acceleration
                beta0 = particles._xobject.beta0[ii_first_active]
                at_turn = particles._xobject.at_turn[ii_first_active]
                t_turn = (at_turn * self._tracker_data_base.line_length
                          / (beta0 * clight)) + self.line.t0_time_dependent_vars

                if (self.line._t_last_update_time_dependent_vars is None
                    or self.line.dt_update_time_dependent_vars is None
                    or t_turn > self.line._t_last_update_time_dependent_vars
                                + self.line.dt_update_time_dependent_vars):
                    self.line._t_last_update_time_dependent_vars = t_turn
                    self.vars['t_turn_s'] = t_turn

            moveback_to_buffer = None
            moveback_to_offset = None
            for ipp, pp in enumerate(self._parts):
                if (ipp_resume is not None and ipp < ipp_resume):
                    continue
                elif (ipp_resume is not None and ipp == ipp_resume):
                    assert particles is None
                    particles = _session_to_resume['particles']
                    pp = self._parts[ipp]
                    moveback_to_buffer = _session_to_resume['moveback_to_buffer']
                    moveback_to_offset = _session_to_resume['moveback_to_offset']
                    _context_needs_clean_active_lost_state = _session_to_resume[
                                    '_context_needs_clean_active_lost_state']
                    _need_unhide_lost_particles = _session_to_resume[
                                    '_need_unhide_lost_particles']
                    # Clear
                    tt_resume = None
                    ipp_resume = None
                else:
                    (_need_unhide_lost_particles, moveback_to_buffer,
                        moveback_to_offset) = self._prepare_particles_for_part(
                                            particles, pp,
                                            moveback_to_buffer, moveback_to_offset,
                                            _context_needs_clean_active_lost_state)

                # Track!
                stop_tracking, skip, returned_by_track = self._track_part(
                        particles, pp, tt, ipp, ele_start, ele_stop, num_turns)

                if returned_by_track is not None:
                    if returned_by_track.on_hold:

                        assert self.enable_pipeline_hold, (
                            "Hold session not enabled for this tracker.")

                        session_on_hold = {
                            'particles': particles,
                            'tracker': self,
                            'status_from_element': returned_by_track,
                            'ele_start': ele_start,
                            'ele_stop': ele_stop,
                            'num_elements': num_elements,
                            'num_turns': num_turns,
                            'flag_monitor': flag_monitor,
                            'monitor': monitor,
                            '_context_needs_clean_active_lost_state':
                                        _context_needs_clean_active_lost_state,
                            '_need_unhide_lost_particles':
                                        _need_unhide_lost_particles,
                            'moveback_to_buffer': moveback_to_buffer,
                            'moveback_to_offset': moveback_to_offset,
                            'ipp': ipp,
                            'tt': tt,
                            'resumed': False
                        }
                    return PipelineStatus(on_hold=True, data=session_on_hold)

                # Do nothing before ele_start in the first turn
                if skip:
                    continue

                # For collective parts increment at_element
                if not isinstance(pp, TrackerPartNonCollective) and not stop_tracking:
                    if moveback_to_buffer is not None: # The particles object is temporarily on CPU
                        if not hasattr(self, '_zerodrift_cpu'):
                            self._zerodrift_cpu = self._zerodrift.copy(particles._buffer.context)
                        self._zerodrift_cpu.track(particles, increment_at_element=True)
                    else:
                        self._zerodrift.track(particles, increment_at_element=True)

                if _need_unhide_lost_particles:
                    particles.unhide_lost_particles()

                # Break from loop over parts if stop element reached
                if stop_tracking:
                    break

            ## Break from loop over turns if stop element reached
            if stop_tracking:
                break

            if moveback_to_buffer is not None:
                particles.move(
                        _buffer=moveback_to_buffer, _offset=moveback_to_offset)
                moveback_to_buffer = None
                moveback_to_offset = None
                if _context_needs_clean_active_lost_state:
                    particles._num_active_particles = -1
                    particles._num_lost_particles = -1

            # Increment at_turn and reset at_element
            # (use the non-collective track method to perform only end-turn actions)
            self._track_no_collective(particles,
                               ele_start=self.num_elements,
                               num_elements=0)

        self.record_last_track = monitor

        if time:
            t1 = perf_counter()
            self._context.synchronize()
            self.time_last_track = t1 - t0
        else:
            self.time_last_track = None

    def _track_no_collective(
        self,
        particles,
        ele_start=None,
        ele_stop=None,     # defaults to full lattice
        num_elements=None, # defaults to full lattice
        num_turns=None,    # defaults to 1
        turn_by_turn_monitor=None,
        freeze_longitudinal=False,
        backtrack=False,
        time=False,
        _force_no_end_turn_actions=False,
    ):

        self._check_invalidated()

        if backtrack != False:
            kwargs = locals().copy()
            if isinstance(backtrack, str):
                assert backtrack == 'force'
                force_backtrack = True
            else:
                force_backtrack = False
            if not(force_backtrack) and not(self._tracker_data_base._is_backtrackable):
                raise ValueError("This line is not backtrackable.")
            kwargs.pop('self')
            kwargs.pop('backtrack')
            with xt.line._preserve_config(self):
                self.config.XSUITE_BACKTRACK = True
                return self._track_no_collective(**kwargs)

        # Add the Particles class to the config, so the kernel is recompiled
        # and stored if a new Particles class is given.
        if type(particles) != xp.Particles:
            self.config.particles_class_name = type(particles).__name__
        else:
            self.config.pop('particles_class_name', None)
        self.particles_class = particles.__class__
        self.local_particle_src = particles.gen_local_particle_api()

        if time:
            t0 = perf_counter()

        if freeze_longitudinal:
            kwargs = locals().copy()
            kwargs.pop('self')
            kwargs.pop('freeze_longitudinal')

            with _freeze_longitudinal(self.line):
                return self._track_no_collective(**kwargs)

        if isinstance(self._buffer.context, xo.ContextCpu):
            assert (particles._num_active_particles >= 0 and
                    particles._num_lost_particles >= 0), (
                        "Particles state is not valid to run on CPU, please "
                        "call `particles.reorganize()` first."
                    )

        # Start position
        if particles.start_tracking_at_element >= 0:
            if ele_start != 0:
                raise ValueError("The argument ele_start is used, but particles.start_tracking_at_element is set as well. "
                                 "Please use only one of those methods.")
            ele_start = particles.start_tracking_at_element
            particles.start_tracking_at_element = -1
        if isinstance(ele_start, str):
            ele_start = self.line.element_names.index(ele_start)

        if ele_start is None:
            ele_start = 0

        assert ele_start >= 0
        assert ele_start <= self.num_elements

        # Logic to split the tracking turns:
        # Case 1: 0 <= start < stop <= L
        #      Track first turn from start until stop (with num_elements_first_turn=stop-start)
        # Case 2: 0 <= start < L < stop < 2L
        #      Track first turn from start until L    (with num_elements_first_turn=L-start)
        #      Track last turn from 0 until stop      (with num_elements_last_turn=stop)
        # Case 3: 0 <= start < L < stop=nL
        #      Track first turn from start until L    (with num_elements_first_turn=L-start)
        #      Track middle turns from 0 until (n-1)L (with num_middle_turns=n-1)
        # Case 4: 0 <= start < L < nL < stop
        #      Track first turn from start until L    (with num_elements_first_turn=L-start)
        #      Track middle turns from 0 until (n-1)L (with num_middle_turns=n-1)
        #      Track last turn from 0 until stop      (with num_elements_last_turn=stop)

        num_middle_turns = 0
        num_elements_last_turn = 0

        if num_elements is not None:
            # We are using ele_start and num_elements
            assert num_elements >= 0
            if ele_stop is not None:
                raise ValueError("Cannot use both num_elements and ele_stop!")
            if num_turns is not None:
                raise ValueError("Cannot use both num_elements and num_turns!")
            if num_elements + ele_start <= self.num_elements:
                # Track only the first (potentially partial) turn
                num_elements_first_turn = num_elements
            else:
                # Track the first turn until the end of the lattice
                num_elements_first_turn = self.num_elements - ele_start
                # Middle turns and potential last turn
                num_middle_turns, ele_stop = np.divmod(ele_start + num_elements, self.num_elements)
                num_elements_last_turn = ele_stop
                num_middle_turns -= 1

        else:
            # We are using ele_start, ele_stop, and num_turns
            if num_turns is None:
                num_turns = 1
            else:
                assert num_turns > 0
            if ele_stop is None:
                # Track the first turn until the end of the lattice
                # (last turn is also a full cycle, so will be treated as a middle turn)
                num_elements_first_turn = self.num_elements - ele_start
                num_middle_turns = num_turns - 1
            else:
                if isinstance(ele_stop, str):
                    ele_stop = self.line.element_names.index(ele_stop)
                assert ele_stop >= 0
                assert ele_stop <= self.num_elements
                if ele_stop <= ele_start:
                    # Correct for overflow:
                    num_turns += 1
                if num_turns == 1:
                    # Track only the first partial turn
                    num_elements_first_turn = ele_stop - ele_start
                else:
                    # Track the first turn until the end of the lattice
                    num_elements_first_turn = self.num_elements - ele_start
                    # Track the middle turns
                    num_middle_turns = num_turns - 2
                    # Track the last turn until ele_stop
                    num_elements_last_turn = ele_stop

        if self.skip_end_turn_actions or _force_no_end_turn_actions:
            flag_end_first_turn_actions = False
            flag_end_middle_turn_actions = False
        else:
            flag_end_first_turn_actions = (
                    num_elements_first_turn + ele_start == self.num_elements)
            flag_end_middle_turn_actions = True

        if num_elements_last_turn > 0:
            # One monitor record for the initial turn, num_middle_turns records for the middle turns,
            # and one for the last turn
            monitor_turns = num_middle_turns + 2
        else:
            # One monitor record for the initial turn, and num_middle_turns record for the middle turns
            monitor_turns = num_middle_turns + 1

        (flag_monitor, monitor, buffer_monitor, offset_monitor
            ) = self._get_monitor(particles, turn_by_turn_monitor, monitor_turns)

        if self.line._needs_rng and not particles._has_valid_rng_state():
            particles._init_random_number_generator()

        track_kernel, tracker_data = self.get_track_kernel_and_data_for_present_config()
        track_kernel.description.n_threads = particles._capacity

        # First turn
        assert num_elements_first_turn >= 0
        track_kernel(
            buffer=tracker_data._buffer.buffer,
            tracker_data=tracker_data._element_ref_data,
            particles=particles._xobject,
            num_turns=1,
            ele_start=ele_start,
            num_ele_track=num_elements_first_turn,
            flag_end_turn_actions=flag_end_first_turn_actions,
            flag_reset_s_at_end_turn=self.reset_s_at_end_turn,
            flag_monitor=flag_monitor,
            num_ele_line=len(tracker_data.element_names),
            line_length=tracker_data.line_length,
            buffer_tbt_monitor=buffer_monitor,
            offset_tbt_monitor=offset_monitor,
            io_buffer=self.io_buffer.buffer,
        )

        # Middle turns
        if num_middle_turns > 0:
            assert self.num_elements > 0
            track_kernel(
                buffer=tracker_data._buffer.buffer,
                tracker_data=tracker_data._element_ref_data,
                particles=particles._xobject,
                num_turns=num_middle_turns,
                ele_start=0, # always full turn
                num_ele_track=self.num_elements, # always full turn
                flag_end_turn_actions=flag_end_middle_turn_actions,
                flag_reset_s_at_end_turn=self.reset_s_at_end_turn,
                flag_monitor=flag_monitor,
                num_ele_line=len(tracker_data.element_names),
                line_length=tracker_data.line_length,
                buffer_tbt_monitor=buffer_monitor,
                offset_tbt_monitor=offset_monitor,
                io_buffer=self.io_buffer.buffer,
            )

        # Last turn, only if incomplete
        if num_elements_last_turn > 0:
            assert num_elements_last_turn > 0
            track_kernel(
                buffer=tracker_data._buffer.buffer,
                tracker_data=tracker_data._element_ref_data,
                particles=particles._xobject,
                num_turns=1,
                ele_start=0,
                num_ele_track=num_elements_last_turn,
                flag_end_turn_actions=False,
                flag_reset_s_at_end_turn=self.reset_s_at_end_turn,
                flag_monitor=flag_monitor,
                num_ele_line=len(tracker_data.element_names),
                line_length=tracker_data.line_length,
                buffer_tbt_monitor=buffer_monitor,
                offset_tbt_monitor=offset_monitor,
                io_buffer=self.io_buffer.buffer,
            )

        self.record_last_track = monitor

        if time:
            self._context.synchronize()
            t1 = perf_counter()
            self.time_last_track = t1 - t0
        else:
            self.time_last_track = None

    @staticmethod
    def _get_default_monitor_class():
        return xt.ParticlesMonitor

    def _get_monitor(self, particles, turn_by_turn_monitor, num_turns):

        if turn_by_turn_monitor is None or turn_by_turn_monitor is False:
            flag_monitor = 0
            monitor = None
            buffer_monitor = particles._buffer.buffer  # I just need a valid buffer
            offset_monitor = 0
        elif turn_by_turn_monitor is True:
            flag_monitor = 1
            # TODO Assumes at_turn starts from zero, to be generalized
            monitor = self.particles_monitor_class(
                _context=particles._buffer.context,
                start_at_turn=0,
                stop_at_turn=num_turns,
                particle_id_range=particles.get_active_particle_id_range()
            )
            buffer_monitor = monitor._buffer.buffer
            offset_monitor = monitor._offset
        elif turn_by_turn_monitor == 'ONE_TURN_EBE':
            (_, monitor, buffer_monitor, offset_monitor
                ) = self._get_monitor(particles, turn_by_turn_monitor=True,
                                      num_turns=len(self.line.element_names)+1)
            monitor.ebe_mode = 1
            flag_monitor = 2
        elif isinstance(turn_by_turn_monitor, self.particles_monitor_class):
            if turn_by_turn_monitor.ebe_mode == 1:
                flag_monitor = 2
            else:
                flag_monitor = 1
            monitor = turn_by_turn_monitor
            buffer_monitor = monitor._buffer.buffer
            offset_monitor = monitor._offset
        else:
            raise ValueError('Please provide a valid monitor object')

        return flag_monitor, monitor, buffer_monitor, offset_monitor

    def to_binary_file(self, path):

       raise NotImplementedError('to_binary_file not implemented anymore')

    @classmethod
    def from_binary_file(cls, path, particles_monitor_class=None, **kwargs) -> 'Tracker':
        raise NotImplementedError('from_binary_file not implemented anymore')

    def _hashable_config(self):
        items = ((k, v) for k, v in self.config.items() if v is not False)
        return tuple(sorted(items))

    def _config_to_headers(self):
        headers = []
        for k, v in self.config.items():
            if not isinstance(v, bool):
                headers.append(f'#define {k} {v}')
            elif v is True:
                headers.append(f'#define {k}')
            else:
                headers.append(f'#undef {k}')
        return headers

    def _get_twiss_mask_markers(self):
        if hasattr(self._tracker_data_base, 'mask_markers_for_twiss'):
            return self._tracker_data_base.mask_markers_for_twiss
        tt = self.line.get_table()
        mask_twiss = np.ones(len(tt) + 1, dtype=bool)
        mask_twiss[:-1] = tt.element_type == 'Marker'
        self._tracker_data_base.mask_markers_for_twiss = mask_twiss
        return mask_twiss

    def get_track_kernel_and_data_for_present_config(self):

        hash_config = self._hashable_config()

        if hash_config not in self.track_kernel:
            new_kernel = self._build_kernel(compile=True)
            self.track_kernel[hash_config] = new_kernel

        out_kernel = self.track_kernel[hash_config]

        if hash_config not in self._tracker_data_cache:
            kernel_element_classes = _element_classes_from_track_kernel(out_kernel)
            td_base = self._tracker_data_base
            td = TrackerData(
                element_dict=td_base._element_dict,
                element_names=td_base._element_names,
                element_s_locations=td_base.element_s_locations,
                line_length=td_base.line_length,
                compound_mask=td_base.compound_mask,
                element_compound_names=td_base.element_compound_names,
                kernel_element_classes=kernel_element_classes,
                extra_element_classes=td_base.extra_element_classes,
                _context=self._context,
                _buffer=self._buffer)

            self._tracker_data_cache[hash_config] = td

        out_tracker_data = self._tracker_data_cache[hash_config]

        # sanity check
        assert (len(_element_classes_from_track_kernel(out_kernel))
                == len(out_tracker_data.kernel_element_classes))

        return out_kernel, out_tracker_data

    @property
    def reset_s_at_end_turn(self):
        return self.line.reset_s_at_end_turn

    @reset_s_at_end_turn.setter
    def reset_s_at_end_turn(self, value):
        self.line.reset_s_at_end_turn = value

    @property
    def skip_end_turn_actions(self):
        return self.line.skip_end_turn_actions

    @skip_end_turn_actions.setter
    def skip_end_turn_actions(self, value):
        self.line.skip_end_turn_actions = value

    # def __getattr__(self, attr):
    #     # If not in self look in self.line (if not None)
    #     if attr == 'line':
    #         raise AttributeError(f'Tracker object has no attribute `{attr}`')
    #     if self.line is not None and attr in object.__dir__(self.line):
    #         _print(f'Warning! The use of `Tracker.{attr}` is deprecated.'
    #             f' Please use `Line.{attr}` (for more info see '
    #             'https://github.com/xsuite/xsuite/issues/322)')
    #         return getattr(self.line, attr)
    #     else:
    #         raise AttributeError(f'Tracker object has no attribute `{attr}`')

    def __dir__(self):
        return list(set(object.__dir__(self) + dir(self.line)))

    def __getstate__(self):
        if not isinstance(self._context, xo.ContextCpu):
            raise TypeError("Only CPU trackers can be pickled.")

        # Remove the compiled kernels from the state
        state = self.__dict__.copy()
        state['_track_kernel'].clear()
        return state

    def check_compatibility_with_prebuilt_kernels(self):
        get_suitable_kernel(
            config=self.line.config,
            line_element_classes=self.line_element_classes,
            verbose=True)


class TrackerConfig(UserDict):

    def __setitem__(self, idx, val):
        if val is False and idx in self:
            del(self[idx]) # We don't want to store flags that are False
        else:
            super(TrackerConfig, self).__setitem__(idx, val)

    def __setattr__(self, idx, val):
        if idx == 'data':
            object.__setattr__(self, idx, val)
        elif val is not False and val is not None:
            self.data[idx] = val
        elif idx in self:
            del(self.data[idx])

    def __getattr__(self, idx):
        if idx == 'data':
            return object.__getattribute__(self, idx)
        if idx in self.data:
            return self.data[idx]
        else:
            raise AttributeError(f'No attribute {idx}')

    def update(self, other, **kwargs):
        super().update(other, **kwargs)
        keys_for_none_vals = [k for k, v in self.items() if v is False]
        for k in keys_for_none_vals:
            del self[k]


class TrackerPartNonCollective:
    def __init__(self, tracker, ele_start_in_tracker, ele_stop_in_tracker):
        self.tracker = tracker
        self.ele_start_in_tracker = ele_start_in_tracker
        self.ele_stop_in_tracker = ele_stop_in_tracker

    def track(self, particles, ele_start=None, ele_stop=None, num_elements=None):
        if ele_start is None:
            temp_ele_start = self.ele_start_in_tracker
        else:
            temp_ele_start = self.ele_start_in_tracker + ele_start

        if ele_stop is None:
            temp_ele_stop = self.ele_stop_in_tracker
        else:
            temp_ele_stop = self.ele_start_in_tracker + ele_stop

        if num_elements is None:
            temp_num_elements = temp_ele_stop - temp_ele_start
        else:
            temp_num_elements = num_elements

        self.tracker._track_no_collective(particles, ele_start=temp_ele_start,
                           num_elements=temp_num_elements,
                           _force_no_end_turn_actions=True)

    def __repr__(self):
        return (f'TrackerPartNonCollective({self.ele_start_in_tracker}, '
                f'{self.ele_stop_in_tracker})')


def _element_classes_from_track_kernel(kernel):
    assert kernel.description.args[1].name == 'tracker_data'
    kernel_tracker_data_type = kernel.description.args[1].atype
    kernel_element_ref_class = kernel_tracker_data_type.elements.ftype._itemtype
    kernel_element_classes = kernel_element_ref_class._reftypes
    return kernel_element_classes

def _element_ref_data_class_from_element_classes(element_classes):

    # exctrace XoStruct if needed
    element_classes_xostruct = []
    for cc in element_classes:
        if issubclass(cc, xo.Struct):
            element_classes_xostruct.append(cc)
        else:
            element_classes_xostruct.append(cc._XoStruct)

    class ElementRefClass(xo.UnionRef):
        _reftypes = element_classes_xostruct

    class ElementRefData(xo.Struct):
            elements = ElementRefClass[:]
            names = xo.String[:]
            _overridable = False

    return ElementRefData
