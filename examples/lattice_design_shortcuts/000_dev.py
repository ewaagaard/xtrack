import xtrack as xt
import numpy as np

line = xt.Line()
line.particle_ref = xt.Particles(p0c=2e9)

n_bends_per_cell = 6
n_cells_par_arc = 3
n_arcs = 3

n_bends = n_bends_per_cell * n_cells_par_arc * n_arcs


line.vars({
    'k1l.qf': 0.027 / 2,
    'k1l.qd': -0.0271 / 2,
    'l.mq': 0.5,
    'kqf.1': 'k1l.qf / l.mq',
    'kqd.1': 'k1l.qd / l.mq',
    'l.mb': 12,
    'angle.mb': 2 * np.pi / n_bends,
    'k0.mb': 'angle.mb / l.mb',
})

halfcell = line.new_section(components=[
    line.new_element('drift.1', xt.Drift,      length='l.mq / 2'),
    line.new_element('qf',      xt.Quadrupole, k1='kqf.1', length='l.mq'),
    line.new_element('drift.2', xt.Replica,    parent_name='drift.1'),
    line.new_element('mb.1',    xt.Bend,       k0='k0.mb', h='k0.mb', length='l.mb'),
    line.new_element('mb.2',    xt.Replica,    parent_name='mb.1'),
    line.new_element('mb.3',    xt.Replica,    parent_name='mb.1'),
    line.new_element('drift.3', xt.Replica,    parent_name='drift.1'),
    line.new_element('qd',      xt.Quadrupole, k1='kqd.1', length='l.mq'),
    line.new_element('drift.4', xt.Replica,    parent_name='drift.1'),
])

hcell_left = halfcell.replicate(name='l')
hcell_right = halfcell.replicate(name='r') # could add mirror=True
hcell_right.mirror()

cell = line.new_section(components=[
    line.new_element('start', xt.Marker),
    hcell_left,
    line.new_element('mid', xt.Marker),
    hcell_right,
    line.new_element('end', xt.Marker),
])

arc = line.new_section(components=[
    cell.replicate(name='cell.1'),
    cell.replicate(name='cell.2'),
    cell.replicate(name='cell.3'),
])

cell_ss = cell.replicate('ss')
line.new_element('drift_ss', xt.Drift, length='l.mb')
for ii, nn in enumerate(cell_ss.components):
    if nn.startswith('mb'):
        cell_ss.components[ii] = line.new_element(
            f'drift.{ii}.ss', xt.Replica, parent_name='drift_ss')

ss = line.new_section(components=[
    cell_ss.replicate('cell.1'),
    cell_ss.replicate('cell.2'),
])

arc1 = arc.replicate(name='arc.1')
arc2 = arc.replicate(name='arc.2')
arc3 = arc.replicate(name='arc.3')

# ss1 = ss.replicate(name='ss.1')
# ss2 = ss.replicate(name='ss.2')
# ss3 = ss.replicate(name='ss.3')



line.replace_all_replicas()

opt = cell.match(
    method='4d',
    vary=xt.VaryList(['k1l.qf', 'k1l.qd'], step=1e-5),
    targets=xt.TargetSet(
        qx=0.333333,
        qy=0.333333,
    ))

line.vars({
    'k1l.q1': 0.012,
    'k1l.q2': -0.012,
    'k1l.q3': 0.012,
    'k1l.q4': -0.012,
    'k1l.q5': 0.012,
    'k1.q1': 'k1l.q1 / l.mq',
    'k1.q2': 'k1l.q2 / l.mq',
    'k1.q3': 'k1l.q3 / l.mq',
    'k1.q4': 'k1l.q4 / l.mq',
    'k1.q5': 'k1l.q5 / l.mq',
})

half_straight = line.new_section(components=[
    line.new_element('ip', xt.Marker),
    line.new_element('dd.0', xt.Drift, length=20),
    line.new_element('mq.1', xt.Quadrupole, k1='k1l.q1', length='l.mq'),
    line.new_element('dd.1', xt.Drift, length=5),
    line.new_element('mq.2', xt.Quadrupole, k1='k1l.q2', length='l.mq'),
    line.new_element('dd.2', xt.Drift, length=12),
    line.new_element('mq.3', xt.Quadrupole, k1='k1l.q3', length='l.mq'),
    line.new_element('dd.3', xt.Drift, length=18),
    line.new_element('mq.4', xt.Quadrupole, k1='k1l.q4', length='l.mq'),
    line.new_element('dd.4', xt.Drift, length=18),
    line.new_element('mq.5', xt.Quadrupole, k1='k1l.q5', length='l.mq'),
    line.new_element('dd.5', xt.Drift, length=0.5),
    line.new_element('e.ss.r', xt.Marker),
])
half_straight.build_tracker()
print(f'Half straight length: {half_straight.get_length()}')

tw_arc = arc.twiss4d()

opt = half_straight.match(
    solve=False,
    betx=tw_arc.betx[0], bety=tw_arc.bety[0],
    alfx=tw_arc.alfx[0], alfy=tw_arc.alfy[0],
    init_at='e.ss.r',
    start='ip', end='e.ss.r',
    vary=xt.VaryList(['k1l.q1', 'k1l.q2', 'k1l.q3', 'k1l.q4'], step=1e-5),
    targets=[
        xt.TargetSet(alfx=0, alfy=0, at='ip'),
        xt.Target(lambda tw: tw.betx[0] - tw.bety[0], 0),
        xt.Target(lambda tw: tw.betx.max(), xt.LessThan(400)),
        xt.Target(lambda tw: tw.bety.max(), xt.LessThan(400)),
        xt.Target(lambda tw: tw.betx.min(), xt.GreaterThan(2)),
        xt.Target(lambda tw: tw.bety.min(), xt.GreaterThan(2)),
    ]
    )


opt.step(40)

half_straight_left = half_straight.replicate('ss.l')
half_straight_left.mirror()
half_straight_right = half_straight.replicate('ss.r')
straight = line.new_section(components=[half_straight_left, half_straight_right])

ss_arc = line.new_section(components=[arc1, straight, arc2])
tw_ss_arc = ss_arc.twiss4d(betx=tw_arc.betx[-1], bety=tw_arc.bety[-1],
                           alfx=tw_arc.alfx[-1], alfy=tw_arc.alfy[-1],
                           init_at=xt.END)

line.vars({
    'k1l.qfss': 0.027 / 2,
    'k1l.qdss': -0.0271 / 2,
    'kqfss.1': 'k1l.qfss / l.mq',
    'kqdss.1': 'k1l.qdss / l.mq',
    'angle.mb': 2 * np.pi / n_bends,
    'k0.mb': 'angle.mb / l.mb',
})
cell_ss = line.new_section(components=[
    line.new_element('ss.start', xt.Marker),
    line.new_element('dd.ss.1.l', xt.Drift,        length='l.mq'),
    line.new_element('qfss.l',    xt.Quadrupole, k1='kqfss.1', length='l.mq'),

    line.new_element('dd.ss.3.l', xt.Drift,        length='3 *l.mb'),

    line.new_element('qdss.l',    xt.Quadrupole, k1='kqdss.1', length='l.mq'),
    line.new_element('dd.ss.5.l', xt.Drift,        length='l.mq'),

    line.new_element('dd.ss.5.r', xt.Drift,        length='l.mq'),
    line.new_element('qdss.r',    xt.Quadrupole, k1='kqdss.1', length='l.mq'),

    line.new_element('dd.ss.3.r', xt.Drift,        length='3 *l.mb'),

    line.new_element('qfss.r',    xt.Quadrupole, k1='kqfss.1', length='l.mq'),
    line.new_element('dd.ss.1.r', xt.Drift,        length='l.mq'),

])

opt = cell_ss.match(
    solve=False,
    method='4d',
    vary=xt.VaryList(['k1l.qfss', 'k1l.qdss'], step=1e-5),
    targets=xt.TargetSet(at='ss.start',
        betx=tw_arc.betx[-1],
        bety=tw_arc.bety[-1],
    ))
opt.step(40)
opt.solve()

tw_ss_arc.plot()


cell1_ss = cell_ss.replicate('cell.1')
cell2_ss = cell_ss.replicate('cell.2')
std_ss = line.new_section(components=[cell1_ss, cell2_ss])

ss1 = std_ss.replicate('ss.1')
ss2 = std_ss.replicate('ss.2')
line.discard_tracker()

line.append(ss1)
line.append(arc1)
line.append(ss2)
line.append(arc2)
line.append(straight)
line.append(arc3)

line.replace_all_replicas()
line.build_tracker()
sv = line.survey()

buffer = line._buffer
line.discard_tracker()
line.cut_at_s(np.arange(0, line.get_length(), 0.5))
line.build_tracker(_buffer=buffer)
tw = line.twiss4d()

two = line.twiss(start=xt.START, betx=tw_arc.betx[-1], bety=tw_arc.bety[-1])

import matplotlib.pyplot as plt
plt.close('all')
fig = plt.figure(1, figsize=(6.4*1.2, 4.8))
ax1 = fig.add_subplot(2, 1, 1)
pltbet = tw.plot('betx bety', ax=ax1)
ax2 = fig.add_subplot(2, 1, 2, sharex=ax1)
pltdx = tw.plot('dx', ax=ax2)
fig.subplots_adjust(right=.85)
pltbet.move_legend(1.2,1)
pltdx.move_legend(1.2,1)

import xplt
xplt.FloorPlot(sv, line, element_width=10)

plt.show()



