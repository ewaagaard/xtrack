import xobjects as xo

from ..dress_element import dress_element
from ..general import _pkg_root

def _monitor_init(self, _context=None, _buffer=None, _offset=None,
                  start_at_turn=None, stop_at_turn=None,
                  num_particles=None):

    n_turns = stop_at_turn - stop_at_turn
    n_records = n_turns * num_particles

    data_init = {nn: n_records for tt, nn in
                     self._data_structure['per_particle_vars']}

    self.xoinitialize(_context=_context, _buffer=_buffer, _offset=_offset,
            start_at_turn=start_at_turn, stop_at_turn=stop_at_turn
            data=data_init)



def generate_monitor_class(ParticlesClass):

    ParticlesMonitorDataClass = type(
            'ParticlesMonitorData',
            (xo.Struct),
            {'start_at_turn': xo.Int64,
             'stop_at_turn': xo.Int64,
             'data': ParticlesClass.XoStruct})

    ParticlesMonitorDataClass.extra_sources = [
        _pkg_root.joinpath('monitors_src/monitors.h')]

    ParticlesMonitorClass = type(
            'ParticlesMonitor',
            (dress_element(ParticlesMonitorDataClass),)
            {'_data_structure': ParticlesClass._structure})

    return ParticlesMonitor