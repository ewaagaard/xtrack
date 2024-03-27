// copyright ############################### //
// This file is part of the Xtrack Package.  //
// Copyright (c) CERN, 2023.                 //
// ######################################### //

#ifndef XTRACK_QUADRUPOLE_THIN_SLICE_H
#define XTRACK_QUADRUPOLE_THIN_SLICE_H

void QuadrupoleThinSlice_track_local_particle(
        QuadrupoleThinSliceData el,
        LocalParticle* part0
) {

    double weight = QuadrupoleThinSliceData_get_weight(el);
    const double k1 = QuadrupoleThinSliceData_get_parent_k1(el);
    const double k1s = QuadrupoleThinSliceData_get_parent_k1s(el);

    SynchrotronRadiationRecordData record = NULL;
    RecordIndex record_index = NULL;

    #ifndef XTRACK_MULTIPOLE_NO_SYNRAD
    int64_t radiation_flag = QuadrupoleThinSliceData_get_radiation_flag(el);

    // Extract record and record_index
    if (radiation_flag==2){
        record = (SynchrotronRadiationRecordData) QuadrupoleThinSliceData_getp_internal_record(el, part0);
        if (record){
            record_index = SynchrotronRadiationRecordData_getp__index(record);
        }
    }

    #else
    int64_t radiation_flag = 0;
    #endif

    double dp_record_entry = 0.;
    double dpx_record_entry = 0.;
    double dpy_record_entry = 0.;
    double dp_record_exit = 0.;
    double dpx_record_exit = 0.;
    double dpy_record_exit = 0.;

    #ifdef XTRACK_MULTIPOLE_NO_SYNRAD
    #define delta_taper (0)
    #else
        double delta_taper = QuadrupoleThinSliceData_get_delta_taper(el);
    #endif


    #ifndef XSUITE_BACKTRACK
        double const length = QuadrupoleThinSliceData_get_length(el); // m
        double const backtrack_sign = 1;
    #else
        double const length = -QuadrupoleThinSliceData_get_length(el); // m
        double const backtrack_sign = -1;
    #endif

    double const knl_quad[2] = {0., k1 * length / weight}; // the length is supposed to be already scaled by the weight
    double const ksl_quad[2] = {0., k1s * length / weight};

    //start_per_particle_block (part0->part)

        #ifdef XTRACK_MULTIPOLE_TAPER
            delta_taper = LocalParticle_get_delta(part);
        #endif

        Multipole_track_single_particle(part,
            0., 0., length, weight, // weight 1
            NULL, NULL, -1, -1, // first tap unused
            knl_quad, ksl_quad, 1, 1,
            backtrack_sign,
            delta_taper, radiation_flag,
            &dp_record_entry, &dpx_record_entry, &dpy_record_entry,
            &dp_record_exit, &dpx_record_exit, &dpy_record_exit,
            record, record_index);

    //end_per_particle_block

}

#endif
