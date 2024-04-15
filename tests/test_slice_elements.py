import xtrack as xt
import numpy as np

from xobjects.test_helpers import for_all_test_contexts
import xobjects as xo

assert_allclose= xo.assert_allclose

@for_all_test_contexts
def test_thin_slice_bend(test_context):

    bend = xt.Bend(k0=0.4, h=0.3, length=1,
                   edge_entry_angle=0.05, edge_entry_hgap=0.06, edge_entry_fint=0.08,
                   edge_exit_angle=0.05, edge_exit_hgap=0.06, edge_exit_fint=0.08)

    line = xt.Line(elements=[bend])

    line.configure_bend_model(edge='linear', core='expanded')

    line.slice_thick_elements(
        slicing_strategies=[xt.Strategy(xt.Teapot(10000))])
    line.build_tracker(_context=test_context)
    line._line_before_slicing.build_tracker(_context=test_context)
    assert line['e0..995']._parent_name == 'e0'
    assert line['e0..995']._parent is line['e0']
    assert line['drift_e0..995']._parent_name == 'e0'
    assert line['drift_e0..995']._parent is line['e0']
    assert line['e0..entry_map']._parent_name == 'e0'
    assert line['e0..entry_map']._parent is line['e0']
    assert line['e0..exit_map']._parent_name == 'e0'
    assert line['e0..exit_map']._parent is line['e0']

    p0 = xt.Particles(p0c=10e9, x=0.1, px=0.2, y=0.3, py=0.4, delta=0.03
                      ,_context=test_context)
    p_ref = p0.copy()
    p_slice = p0.copy()

    line.track(p_slice)
    line._line_before_slicing.track(p_ref)

    assert_allclose(p_slice.x, p_ref.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p_ref.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p_ref.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p_ref.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p_ref.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p_ref.delta, rtol=0, atol=1e-10)

    line.to_json('ttt.json')
    line2 = xt.Line.from_json('ttt.json')
    assert isinstance(line2['e0..995'], xt.ThinSliceBend)
    assert line2['e0..995']._parent_name == 'e0'
    assert line2['e0..995']._parent is None
    assert line2['drift_e0..995']._parent_name == 'e0'
    assert line2['drift_e0..995']._parent is None
    assert line2['e0..entry_map']._parent_name == 'e0'
    assert line2['e0..entry_map']._parent is None
    assert line2['e0..exit_map']._parent_name == 'e0'
    assert line2['e0..exit_map']._parent is None

    line2.build_tracker(_context=test_context)
    assert isinstance(line2['e0..995'], xt.ThinSliceBend)
    assert line2['e0..995']._parent_name == 'e0'
    assert line2['e0..995']._parent is line2['e0']
    assert isinstance(line2['drift_e0..995'], xt.DriftSliceBend)
    assert line2['drift_e0..995']._parent_name == 'e0'
    assert line2['drift_e0..995']._parent is line2['e0']
    assert isinstance(line2['e0..entry_map'], xt.ThinSliceBendEntry)
    assert line2['e0..entry_map']._parent_name == 'e0'
    assert line2['e0..entry_map']._parent is line2['e0']
    assert isinstance(line2['e0..exit_map'], xt.ThinSliceBendExit)
    assert line2['e0..exit_map']._parent_name == 'e0'
    assert line2['e0..exit_map']._parent is line2['e0']

    line.track(p_slice, backtrack=True)

    assert (p_slice.state == 1).all()
    assert_allclose(p_slice.x, p0.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p0.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p0.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p0.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p0.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p0.delta, rtol=0, atol=1e-10)

    line.optimize_for_tracking()

    if bend.shift_x !=0 or bend.shift_y != 0 or bend.rot_s_rad != 0 and bend.k1 != 0:
        assert isinstance(line['e0..995'], xt.Multipole)
    else:
        assert isinstance(line['e0..995'], xt.SimpleThinBend)
    assert isinstance(line['drift_e0..995'], xt.Drift)

    assert isinstance(line['e0..entry_map'], xt.DipoleEdge)
    assert isinstance(line['e0..exit_map'], xt.DipoleEdge)

    p_slice = p0.copy()
    line.track(p_slice)

    assert_allclose(p_slice.x, p_ref.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p_ref.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p_ref.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p_ref.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p_ref.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p_ref.delta, rtol=0, atol=1e-10)

    line.track(p_slice, backtrack=True)

    assert_allclose(p_slice.x, p0.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p0.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p0.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p0.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p0.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p0.delta, rtol=0, atol=1e-10)

@for_all_test_contexts
def test_thin_slice_quadrupole(test_context):

    quad = xt.Quadrupole(k1=0.1, length=1)

    line = xt.Line(elements=[quad])

    line.slice_thick_elements(
        slicing_strategies=[xt.Strategy(xt.Teapot(10000))])
    line.build_tracker(_context=test_context)
    assert line['e0..995']._parent_name == 'e0'
    assert line['e0..995']._parent is line['e0']
    assert line['drift_e0..995']._parent_name == 'e0'
    assert line['drift_e0..995']._parent is line['e0']

    p0 = xt.Particles(p0c=10e9, x=0.1, px=0.2, y=0.3, py=0.4, delta=0.03,
                        _context=test_context)
    p_ref = p0.copy()
    p_slice = p0.copy()

    line.track(p_slice)
    quad.track(p_ref)

    assert_allclose(p_slice.x, p_ref.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p_ref.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p_ref.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p_ref.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p_ref.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p_ref.delta, rtol=0, atol=1e-10)

    line.to_json('ttt.json')
    line2 = xt.Line.from_json('ttt.json')
    assert isinstance(line2['e0..995'], xt.ThinSliceQuadrupole)
    assert line2['e0..995']._parent_name == 'e0'
    assert line2['e0..995']._parent is None
    assert line2['drift_e0..995']._parent_name == 'e0'
    assert line2['drift_e0..995']._parent is None

    line2.build_tracker(_context=test_context)
    assert isinstance(line2['e0..995'], xt.ThinSliceQuadrupole)
    assert line2['e0..995']._parent_name == 'e0'
    assert line2['e0..995']._parent is line2['e0']
    assert isinstance(line2['drift_e0..995'], xt.DriftSliceQuadrupole)
    assert line2['drift_e0..995']._parent_name == 'e0'
    assert line2['drift_e0..995']._parent is line2['e0']

    line.track(p_slice, backtrack=True)

    assert_allclose(p_slice.x, p0.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p0.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p0.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p0.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p0.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p0.delta, rtol=0, atol=1e-10)

    line.optimize_for_tracking()

    if quad.shift_x !=0 or quad.shift_y != 0 or quad.rot_s_rad != 0:
        assert isinstance(line['e0..995'], xt.Multipole)
    else:
        assert isinstance(line['e0..995'], xt.SimpleThinQuadrupole)
    assert isinstance(line['drift_e0..995'], xt.Drift)

    p_slice = p0.copy()
    line.track(p_slice)

    assert_allclose(p_slice.x, p_ref.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p_ref.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p_ref.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p_ref.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p_ref.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p_ref.delta, rtol=0, atol=1e-10)

    line.track(p_slice, backtrack=True)

    assert_allclose(p_slice.x, p0.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p0.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p0.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p0.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p0.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p0.delta, rtol=0, atol=1e-10)

@for_all_test_contexts
def test_thin_slice_sextupole(test_context):

    sext = xt.Sextupole(k2=0.1, length=1,
                shift_x=1e-3, shift_y=2e-3, rot_s_rad=0.2
                )

    line = xt.Line(elements=[sext])

    line.slice_thick_elements(
        slicing_strategies=[xt.Strategy(xt.Teapot(1))])
    line.build_tracker(_context=test_context)
    assert line['e0..0']._parent_name == 'e0'
    assert line['e0..0']._parent is line['e0']
    assert line['drift_e0..0']._parent_name == 'e0'
    assert line['drift_e0..0']._parent is line['e0']

    p0 = xt.Particles(p0c=10e9, x=0.1, px=0.2, y=0.3, py=0.4, delta=0.03,
                        _context=test_context)
    p_ref = p0.copy()
    p_slice = p0.copy()

    line.track(p_slice)
    sext.track(p_ref)

    assert_allclose(p_slice.x, p_ref.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p_ref.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p_ref.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p_ref.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p_ref.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p_ref.delta, rtol=0, atol=1e-10)

    line.to_json('ttt.json')
    line2 = xt.Line.from_json('ttt.json')
    assert isinstance(line2['e0..0'], xt.ThinSliceSextupole)
    assert line2['e0..0']._parent_name == 'e0'
    assert line2['e0..0']._parent is None
    assert line2['drift_e0..0']._parent_name == 'e0'
    assert line2['drift_e0..0']._parent is None

    line2.build_tracker(_context=test_context)
    assert isinstance(line2['e0..0'], xt.ThinSliceSextupole)
    assert line2['e0..0']._parent_name == 'e0'
    assert line2['e0..0']._parent is line2['e0']
    assert isinstance(line2['drift_e0..0'], xt.DriftSliceSextupole)
    assert line2['drift_e0..0']._parent_name == 'e0'
    assert line2['drift_e0..0']._parent is line2['e0']

    line.track(p_slice, backtrack=True)

    assert_allclose(p_slice.x, p0.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p0.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p0.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p0.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p0.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p0.delta, rtol=0, atol=1e-10)

    line.optimize_for_tracking()

    assert isinstance(line['e0..0'], xt.Multipole)
    assert isinstance(line['drift_e0..0'], xt.Drift)

    p_slice = p0.copy()
    line.track(p_slice)

    assert_allclose(p_slice.x, p_ref.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p_ref.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p_ref.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p_ref.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p_ref.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p_ref.delta, rtol=0, atol=1e-10)

    line.track(p_slice, backtrack=True)

    assert_allclose(p_slice.x, p0.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p0.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p0.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p0.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p0.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p0.delta, rtol=0, atol=1e-10)

@for_all_test_contexts
def test_thin_slice_octupole(test_context):

    oct = xt.Octupole(k3=0.1, length=1)

    line = xt.Line(elements=[oct])

    line.slice_thick_elements(
        slicing_strategies=[xt.Strategy(xt.Teapot(1))])
    line.build_tracker(_context=test_context)
    assert line['e0..0']._parent_name == 'e0'
    assert line['e0..0']._parent is line['e0']
    assert line['drift_e0..0']._parent_name == 'e0'
    assert line['drift_e0..0']._parent is line['e0']

    p0 = xt.Particles(p0c=10e9, x=0.1, px=0.2, y=0.3, py=0.4, delta=0.03,
                        _context=test_context)
    p_ref = p0.copy()
    p_slice = p0.copy()

    line.track(p_slice)
    oct.track(p_ref)

    assert_allclose(p_slice.x, p_ref.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p_ref.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p_ref.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p_ref.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p_ref.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p_ref.delta, rtol=0, atol=1e-10)

    line.to_json('ttt.json')
    line2 = xt.Line.from_json('ttt.json')
    assert isinstance(line2['e0..0'], xt.ThinSliceOctupole)
    assert line2['e0..0']._parent_name == 'e0'
    assert line2['e0..0']._parent is None
    assert line2['drift_e0..0']._parent_name == 'e0'
    assert line2['drift_e0..0']._parent is None

    line2.build_tracker(_context=test_context)
    assert isinstance(line2['e0..0'], xt.ThinSliceOctupole)
    assert line2['e0..0']._parent_name == 'e0'
    assert line2['e0..0']._parent is line2['e0']
    assert isinstance(line2['drift_e0..0'], xt.DriftSliceOctupole)
    assert line2['drift_e0..0']._parent_name == 'e0'
    assert line2['drift_e0..0']._parent is line2['e0']

    line.track(p_slice, backtrack=True)

    assert_allclose(p_slice.x, p0.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p0.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p0.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p0.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p0.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p0.delta, rtol=0, atol=1e-10)

    line.optimize_for_tracking()

    assert isinstance(line['e0..0'], xt.Multipole)
    assert isinstance(line['drift_e0..0'], xt.Drift)

    p_slice = p0.copy()
    line.track(p_slice)

    assert_allclose(p_slice.x, p_ref.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p_ref.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p_ref.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p_ref.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p_ref.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p_ref.delta, rtol=0, atol=1e-10)

    line.track(p_slice, backtrack=True)

    assert_allclose(p_slice.x, p0.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p0.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p0.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p0.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p0.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p0.delta, rtol=0, atol=1e-10)

@for_all_test_contexts
def test_thin_slice_drift(test_context):

    drift = xt.Drift(length=1)

    line = xt.Line(elements=[drift])

    line.slice_thick_elements(
        slicing_strategies=[xt.Strategy(xt.Uniform(5), element_type=xt.Drift)])
    line.build_tracker(_context=test_context)
    assert line['drift_e0..0']._parent_name == 'e0'
    assert line['drift_e0..0']._parent is line['e0']

    p0 = xt.Particles(p0c=10e9, x=0.1, px=0.2, y=0.3, py=0.4, delta=0.03,
                      _context=test_context)
    p_ref = p0.copy()
    p_slice = p0.copy()

    line.track(p_slice)
    drift.track(p_ref)

    assert_allclose(p_slice.x, p_ref.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p_ref.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p_ref.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p_ref.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p_ref.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p_ref.delta, rtol=0, atol=1e-10)

    line.to_json('ttt.json')
    line2 = xt.Line.from_json('ttt.json')
    assert line2['drift_e0..0']._parent_name == 'e0'
    assert line2['drift_e0..0']._parent is None

    line2.build_tracker(_context=test_context)
    assert isinstance(line2['drift_e0..0'], xt.DriftSlice)
    assert line2['drift_e0..0']._parent_name == 'e0'
    assert line2['drift_e0..0']._parent is line2['e0']

    line.track(p_slice, backtrack=True)

    assert_allclose(p_slice.x, p0.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p0.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p0.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p0.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p0.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p0.delta, rtol=0, atol=1e-10)

    line.optimize_for_tracking()

    assert isinstance(line['drift_e0..0'], xt.Drift)

    p_slice = p0.copy()
    line.track(p_slice)

    assert_allclose(p_slice.x, p_ref.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p_ref.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p_ref.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p_ref.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p_ref.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p_ref.delta, rtol=0, atol=1e-10)

    line.track(p_slice, backtrack=True)

    assert_allclose(p_slice.x, p0.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p0.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p0.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p0.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p0.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p0.delta, rtol=0, atol=1e-10)

@for_all_test_contexts
def test_thick_slice_bend(test_context):

    bend = xt.Bend(k0=0.4, h=0.3, length=1,
                edge_entry_angle=0.05, edge_entry_hgap=0.06, edge_entry_fint=0.08,
                edge_exit_angle=0.05, edge_exit_hgap=0.06, edge_exit_fint=0.08)

    line = xt.Line(elements=[bend])

    line.configure_bend_model(edge='linear', core='expanded')

    line.slice_thick_elements(
        slicing_strategies=[xt.Strategy(xt.Teapot(5, mode='thick'))])
    line.build_tracker(_context=test_context)
    line._line_before_slicing.build_tracker(_context=test_context)
    assert line['e0..3']._parent_name == 'e0'
    assert line['e0..3']._parent is line['e0']
    assert line['e0..entry_map']._parent_name == 'e0'
    assert line['e0..entry_map']._parent is line['e0']
    assert line['e0..exit_map']._parent_name == 'e0'
    assert line['e0..exit_map']._parent is line['e0']

    p0 = xt.Particles(p0c=10e9, x=0.1, px=0.2, y=0.3, py=0.4, delta=0.03,
                        _context=test_context)
    p_ref = p0.copy()
    p_slice = p0.copy()

    line.track(p_slice)
    line._line_before_slicing.track(p_ref)

    assert_allclose(p_slice.x, p_ref.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p_ref.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p_ref.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p_ref.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p_ref.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p_ref.delta, rtol=0, atol=1e-10)

    line.to_json('ttt.json')
    line2 = xt.Line.from_json('ttt.json')
    assert isinstance(line2['e0..3'], xt.ThickSliceBend)
    assert line2['e0..3']._parent_name == 'e0'
    assert line2['e0..3']._parent is None
    assert line2['e0..entry_map']._parent_name == 'e0'
    assert line2['e0..entry_map']._parent is None
    assert line2['e0..exit_map']._parent_name == 'e0'
    assert line2['e0..exit_map']._parent is None

    line2.build_tracker(_context=test_context)
    assert isinstance(line2['e0..3'], xt.ThickSliceBend)
    assert line2['e0..3']._parent_name == 'e0'
    assert line2['e0..3']._parent is line2['e0']
    assert line2['e0..entry_map']._parent_name == 'e0'
    assert line2['e0..entry_map']._parent is line2['e0']
    assert line2['e0..exit_map']._parent_name == 'e0'
    assert line2['e0..exit_map']._parent is line2['e0']

    line.track(p_slice, backtrack=True)

    assert (p_slice.state == 1).all()
    assert_allclose(p_slice.x, p0.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p0.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p0.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p0.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p0.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p0.delta, rtol=0, atol=1e-10)

@for_all_test_contexts
def test_thick_slice_quadrupole(test_context):

    quad = xt.Quadrupole(k1=0.1, length=1)

    line = xt.Line(elements=[quad])

    line.slice_thick_elements(
        slicing_strategies=[xt.Strategy(xt.Teapot(5, mode='thick'))])
    line.build_tracker(_context=test_context)
    assert line['e0..3']._parent_name == 'e0'
    assert line['e0..3']._parent is line['e0']

    p0 = xt.Particles(p0c=10e9, x=0.1, px=0.2, y=0.3, py=0.4, delta=0.03,
                        _context=test_context)
    p_ref = p0.copy()
    p_slice = p0.copy()

    line.track(p_slice)
    quad.track(p_ref)

    assert_allclose(p_slice.x, p_ref.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p_ref.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p_ref.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p_ref.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p_ref.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p_ref.delta, rtol=0, atol=1e-10)

    line.to_json('ttt.json')
    line2 = xt.Line.from_json('ttt.json')
    assert isinstance(line2['e0..3'], xt.ThickSliceQuadrupole)
    assert line2['e0..3']._parent_name == 'e0'
    assert line2['e0..3']._parent is None

    line2.build_tracker(_context=test_context)
    assert isinstance(line2['e0..3'], xt.ThickSliceQuadrupole)
    assert line2['e0..3']._parent_name == 'e0'
    assert line2['e0..3']._parent is line2['e0']

    line.track(p_slice, backtrack=True)

    assert_allclose(p_slice.x, p0.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p0.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p0.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p0.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p0.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p0.delta, rtol=0, atol=1e-10)

@for_all_test_contexts
def test_thick_slice_sextupole(test_context):

    sext = xt.Sextupole(k2=0.1, length=1)

    line = xt.Line(elements=[sext])

    line.slice_thick_elements(
        slicing_strategies=[xt.Strategy(xt.Teapot(1, mode='thick'))])
    line.build_tracker(_context=test_context)
    assert line['e0..0']._parent_name == 'e0'
    assert line['e0..0']._parent is line['e0']

    p0 = xt.Particles(p0c=10e9, x=0.1, px=0.2, y=0.3, py=0.4, delta=0.03,
                        _context=test_context)
    p_ref = p0.copy()
    p_slice = p0.copy()

    line.track(p_slice)
    sext.track(p_ref)

    assert_allclose(p_slice.x, p_ref.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p_ref.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p_ref.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p_ref.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p_ref.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p_ref.delta, rtol=0, atol=1e-10)

    line.to_json('ttt.json')
    line2 = xt.Line.from_json('ttt.json')
    assert isinstance(line2['e0..0'], xt.ThickSliceSextupole)
    assert line2['e0..0']._parent_name == 'e0'
    assert line2['e0..0']._parent is None

    line2.build_tracker(_context=test_context)
    assert isinstance(line2['e0..0'], xt.ThickSliceSextupole)
    assert line2['e0..0']._parent_name == 'e0'
    assert line2['e0..0']._parent is line2['e0']

    line.track(p_slice, backtrack=True)

    assert_allclose(p_slice.x, p0.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p0.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p0.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p0.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p0.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p0.delta, rtol=0, atol=1e-10)

@for_all_test_contexts
def test_thick_slice_octupole(test_context):

    oct = xt.Octupole(k3=0.1, length=1)

    line = xt.Line(elements=[oct])

    line.slice_thick_elements(
        slicing_strategies=[xt.Strategy(xt.Teapot(1, mode='thick'))])
    line.build_tracker(_context=test_context)
    assert line['e0..0']._parent_name == 'e0'
    assert line['e0..0']._parent is line['e0']

    p0 = xt.Particles(p0c=10e9, x=0.1, px=0.2, y=0.3, py=0.4, delta=0.03,
                        _context=test_context)
    p_ref = p0.copy()
    p_slice = p0.copy()

    line.track(p_slice)
    oct.track(p_ref)

    assert_allclose(p_slice.x, p_ref.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p_ref.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p_ref.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p_ref.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p_ref.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p_ref.delta, rtol=0, atol=1e-10)

    line.to_json('ttt.json')
    line2 = xt.Line.from_json('ttt.json')
    assert isinstance(line2['e0..0'], xt.ThickSliceOctupole)
    assert line2['e0..0']._parent_name == 'e0'
    assert line2['e0..0']._parent is None

    line2.build_tracker(_context=test_context)
    assert isinstance(line2['e0..0'], xt.ThickSliceOctupole)
    assert line2['e0..0']._parent_name == 'e0'
    assert line2['e0..0']._parent is line2['e0']

    line.track(p_slice, backtrack=True)

    assert_allclose(p_slice.x, p0.x, rtol=0, atol=1e-10)
    assert_allclose(p_slice.px, p0.px, rtol=0, atol=1e-10)
    assert_allclose(p_slice.y, p0.y, rtol=0, atol=1e-10)
    assert_allclose(p_slice.py, p0.py, rtol=0, atol=1e-10)
    assert_allclose(p_slice.zeta, p0.zeta, rtol=0, atol=1e-10)
    assert_allclose(p_slice.delta, p0.delta, rtol=0, atol=1e-10)