import numpy as np

import xtrack as xt
import xpart as xp
import xobjects as xo

from xtrack import RecordIdentifier, RecordIndex

class TestElementRecord(xo.DressedStruct):
    _xofields = {
        '_record_index': RecordIndex,
        'generated_rr': xo.Float64[:],
        'at_element': xo.Int64[:],
        'at_turn': xo.Int64[:]
        }

class TestElement(xt.BeamElement):
    _xofields={
        '_internal_record_id': RecordIdentifier,
        'n_kicks': xo.Int64,
        }

    _skip_in_to_dict = ['_internal_record_id']

    _internal_record_class = TestElementRecord

TestElement.XoStruct.extra_sources = [
    xp._pkg_root.joinpath('random_number_generator/rng_src/base_rng.h'),
    xp._pkg_root.joinpath('random_number_generator/rng_src/local_particle_rng.h'),
    ]

TestElement.XoStruct.extra_sources.append(r'''
    /*gpufun*/
    void TestElement_track_local_particle(TestElementData el, LocalParticle* part0){

        // Check if internal record is enabled
        int record_enabled = TestElementData_get__internal_record_id_buffer_id(el) > 0;

        TestElementRecordData record = NULL;
        RecordIndex record_index = NULL;

        // Extract the record_id, record and record_index
        if (record_enabled){
            RecordIdentifier record_id = TestElementData_getp__internal_record_id(el);
            record = (TestElementRecordData) RecordIdentifier_getp_record(record_id, part0);
            if (record){
                record_index = TestElementRecordData_getp__record_index(record);
            }
        }

        int64_t n_kicks = TestElementData_get_n_kicks(el);
        printf("n_kicks %d\n", (int)n_kicks);

        //start_per_particle_block (part0->part)

            for (int64_t i = 0; i < n_kicks; i++) {
                double rr = 1e-6 * LocalParticle_generate_random_double(part);
                LocalParticle_add_to_px(part, rr);

                if (record_enabled){
                    int64_t i_slot = RecordIndex_get_slot(record_index);
                    // gives negative is record is NULL or if record is full

                    printf("Hello %d\n", (int)i_slot);
                    if (i_slot>=0){
                        TestElementRecordData_set_at_element(record, i_slot,
                                                    LocalParticle_get_at_element(part));
                        TestElementRecordData_set_at_turn(record, i_slot,
                                                    LocalParticle_get_at_turn(part));
                        TestElementRecordData_set_generated_rr(record, i_slot, rr);
                    }
                }
            }


        //end_per_particle_block
    }
    ''')



context = xo.ContextCupy()
n_kicks0 = 5
n_kicks1 = 3
tracker = xt.Tracker(_context=context, line=xt.Line(elements = [
    TestElement(n_kicks=n_kicks0), TestElement(n_kicks=n_kicks1)]))
tracker.line._needs_rng = True

record = tracker.start_internal_logging_for_elements_of_type(
                                                    TestElement, capacity=10000)

part = xp.Particles(_context=context, p0c=6.5e12, x=[1,2,3])
num_turns0 = 10
num_turns1 = 3
tracker.track(part, num_turns=num_turns0)
tracker.track(part, num_turns=num_turns1)

# Checks
num_recorded = record._record_index.num_recorded
num_turns = num_turns0 + num_turns1
assert num_recorded == (part._num_active_particles * num_turns
                                          * (n_kicks0 + n_kicks1))

assert np.sum((record.at_element[:num_recorded] == 0)) == (part._num_active_particles * num_turns
                                           * n_kicks0)
assert np.sum((record.at_element[:num_recorded] == 1)) == (part._num_active_particles * num_turns
                                           * n_kicks1)
for i_turn in range(num_turns):
    assert np.sum((record.at_turn[:num_recorded] == i_turn)) == (part._num_active_particles
                                                        * (n_kicks0 + n_kicks1))

# Check stop
record = tracker.start_internal_logging_for_elements_of_type(
                                                    TestElement, capacity=10000)

part = xp.Particles(p0c=6.5e12, x=[1,2,3])
num_turns0 = 10
num_turns1 = 3
tracker.track(part, num_turns=num_turns0)
tracker.stop_internal_logging_for_elements_of_type(TestElement)
tracker.track(part, num_turns=num_turns1)

num_recorded = record._record_index.num_recorded
num_turns = num_turns0
assert np.all(part.at_turn == num_turns0 + num_turns1)
assert num_recorded == (part._num_active_particles * num_turns
                                          * (n_kicks0 + n_kicks1))

assert np.sum((record.at_element[:num_recorded] == 0)) == (part._num_active_particles * num_turns
                                           * n_kicks0)
assert np.sum((record.at_element[:num_recorded] == 1)) == (part._num_active_particles * num_turns
                                           * n_kicks1)
for i_turn in range(num_turns):
    assert np.sum((record.at_turn[:num_recorded] == i_turn)) == (part._num_active_particles
                                                        * (n_kicks0 + n_kicks1))

prrr

# Collective
n_kicks0 = 5
n_kicks1 = 3
elements = [
    TestElement(n_kicks=n_kicks0), TestElement(n_kicks=n_kicks1)]
elements[0].iscollective = True
tracker = xt.Tracker(line=xt.Line(elements=elements))
tracker.line._needs_rng = True

record = tracker.start_internal_logging_for_elements_of_type(
                                                    TestElement, capacity=10000)

part = xp.Particles(p0c=6.5e12, x=[1,2,3])
num_turns0 = 10
num_turns1 = 3
tracker.track(part, num_turns=num_turns0)
tracker.stop_internal_logging_for_elements_of_type(TestElement)
tracker.track(part, num_turns=num_turns1)

# Checks
num_recorded = record._record_index.num_recorded
num_turns = num_turns0
assert np.all(part.at_turn == num_turns0 + num_turns1)
assert num_recorded == (part._num_active_particles * num_turns
                                          * (n_kicks0 + n_kicks1))

assert np.sum((record.at_element[:num_recorded] == 0)) == (part._num_active_particles * num_turns
                                           * n_kicks0)
assert np.sum((record.at_element[:num_recorded] == 1)) == (part._num_active_particles * num_turns
                                           * n_kicks1)
for i_turn in range(num_turns):
    assert np.sum((record.at_turn[:num_recorded] == i_turn)) == (part._num_active_particles
                                                        * (n_kicks0 + n_kicks1))