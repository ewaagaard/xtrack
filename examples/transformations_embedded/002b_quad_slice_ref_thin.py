import xtrack as xt
import xobjects as xo
from pathlib import Path
import numpy as np


quad = xt.Quadrupole(k1=0.1, length=1)

line = xt.Line(elements=[quad])
line.build_tracker() # Put everything in the same buffer
line.discard_tracker()

line.slice_thick_elements(
    slicing_strategies=[xt.Strategy(xt.Teapot(1000))])
line.build_tracker()
assert line['e0..995']._parent_name == 'e0'
assert line['e0..995']._parent is line['e0']

p0 = xt.Particles(p0c=10e9, x=0.1, px=0.2, y=0.3, py=0.4, delta=0.03)
p_ref = p0.copy()
p_slice = p0.copy()

assert_allclose = np.testing.assert_allclose
assert_allclose = np.testing.assert_allclose
assert_allclose(p_slice.x, p_ref.x, rtol=0, atol=1e-14)
assert_allclose(p_slice.px, p_ref.px, rtol=0, atol=1e-14)
assert_allclose(p_slice.y, p_ref.y, rtol=0, atol=1e-14)
assert_allclose(p_slice.py, p_ref.py, rtol=0, atol=1e-14)
assert_allclose(p_slice.zeta, p_ref.zeta, rtol=0, atol=1e-14)
assert_allclose(p_slice.delta, p_ref.delta, rtol=0, atol=1e-14)

line.track(p_slice)
quad.track(p_ref)

line.to_json('ttt.json')
line2 = xt.Line.from_json('ttt.json')
assert isinstance(line2['e0..995'], xt.ThinSliceQuadrupole)
assert line2['e0..995']._parent_name == 'e0'
assert line2['e0..995']._parent is None

line2.build_tracker()
assert isinstance(line2['e0..995'], xt.ThinSliceQuadrupole)
assert line2['e0..995']._parent_name == 'e0'
assert line2['e0..995']._parent is line2['e0']