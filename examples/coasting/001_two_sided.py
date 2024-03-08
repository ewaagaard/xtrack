import numpy as np
from cpymad.madx import Madx
import xtrack as xt

from scipy.constants import c as clight

# We get the model from MAD-X
# mad = Madx()
# folder = ('../../test_data/elena')
# mad.call(folder + '/elena.seq')
# mad.call(folder + '/highenergy.str')
# mad.call(folder + '/highenergy.beam')
# mad.use('elena')
# seq = mad.sequence.elena
# line = xt.Line.from_madx_sequence(seq)
# line.particle_ref = xt.Particles(gamma0=seq.beam.gamma,
#                                     mass0=seq.beam.mass * 1e9,
#                                     q0=seq.beam.charge)


line = xt.Line.from_json(
    '../../test_data/psb_injection/line_and_particle.json')

# RF off!
tt = line.get_table()
ttcav = tt.rows[tt.element_type == 'Cavity']
for nn in ttcav.name:
    line.element_refs[nn].voltage=0


line.configure_bend_model(core='bend-kick-bend', edge='full')

line.twiss_default['method'] = '4d'

tw = line.twiss()
beta1 = tw.beta0 * 1.1
class CoastWrap:

    def __init__(self, circumference, id, beta1, at_start=False):
        assert id > 10000
        self.id = id
        self.beta1 = beta1
        self.circumference = circumference
        self.at_start = at_start

    def track(self, particles):

        # ---- For debugging
        # particles.sort(interleave_lost_particles=True)
        # particles.get_table().cols['zeta state delta s at_turn'].show()
        # import pdb; pdb.set_trace()
        # particles.reorganize()

        if self.at_start:
            mask_alive = particles.state > 0
            particles.zeta[mask_alive] -= (
                self.circumference * (1 - tw.beta0 / self.beta1))

        # Resume particles previously stopped
        particles.state[particles.state==-self.id] = 1
        particles.reorganize()

        zeta_prime = self.zeta_to_zeta_prime(particles.zeta,
                                             particles.beta0, particles.s,
                                             particles.at_turn)

        # Identify particles that need to be stopped
        mask_alive = particles.state > 0
        mask_stop = mask_alive & (zeta_prime < -self.circumference / 2)

        # Update zeta for particles that are stopped
        zeta_prime[mask_stop] += self.circumference
        particles.at_turn[mask_stop] += 1
        particles.pdg_id[mask_stop] += 1 # HACK!!!!!
        zeta_stopped = self.zeta_prime_to_zeta(zeta_prime[mask_stop],
                                               particles.beta0[mask_stop],
                                               particles.s[mask_stop],
                                               particles.at_turn[mask_stop])
        # zeta_stopped -= self.circumference * (1 - tw.beta0 / self.beta1)
        particles.zeta[mask_stop] = zeta_stopped

        # Stop particles
        particles.state[mask_stop] = -self.id


        # assert np.all(particles.zeta.max() - particles.zeta.min()
        #               < self.circumference * tw.beta0 / self.beta1)

        # # ---- For debugging
        # particles.sort(interleave_lost_particles=True)
        # particles.get_table().cols['zeta state delta s at_turn'].show()
        # import pdb; pdb.set_trace()
        # particles.reorganize()

    def zeta_to_zeta_prime(self, zeta, beta0, s, at_turn):
        S_capital = s + at_turn * self.circumference
        beta1_beta0 = self.beta1 / beta0
        beta0_beta1 = beta0 / self.beta1
        zeta_full = zeta + (1 - beta0_beta1) * self.circumference * (at_turn + 1)
        zeta_prime =  zeta_full * beta1_beta0 + (1 - beta1_beta0) * S_capital
        return zeta_prime

    def zeta_prime_to_zeta(self, zeta_prime, beta0, s, at_turn):
        S_capital = s + at_turn * self.circumference
        beta0_beta1 = beta0 / self.beta1
        zeta_full = zeta_prime * beta0_beta1 + (1 - beta0_beta1) * S_capital
        zeta = zeta_full - (1 - beta0_beta1) * self.circumference * (at_turn + 1)
        return zeta

circumference = line.get_length()
wrap_end = CoastWrap(circumference=circumference, beta1=beta1, id=10001)
wrap_start = CoastWrap(circumference=circumference, beta1=beta1, id=10002, at_start=True)

zeta_min = -circumference/2*tw.beta0/beta1
zeta_max = circumference/2*tw.beta0/beta1

num_particles = 10000
p = line.build_particles(
    zeta=np.random.uniform(-circumference/2, circumference/2, num_particles),
    delta=1e-2 + 0e-2*np.random.uniform(-1, 1, num_particles),
    x_norm=0, y_norm=0
)

p.y[(p.zeta > 1) & (p.zeta < 2)] = 1e-3  # kick

# zeta_grid= np.linspace(zeta_max-circumference, zeta_max, 20)
# zeta_grid= np.linspace(-circumference/2, circumference/2, 20)
# delta_grid = [1e-2] #np.linspace(0, 1e-2, 5)
# ZZ, DD = np.meshgrid(zeta_grid, delta_grid)
# p = line.build_particles(
#     zeta=ZZ.flatten(),
#     delta=DD.flatten()
# )
# p.i_frame = 0

# import pdb; pdb.set_trace()

# wrap_start.at_start = False
# wrap_start.track(p)
# wrap_start.at_start = True

# p.at_turn[:] = 0

line.discard_tracker()
line.insert_element(element=wrap_start, name='wrap_start', at_s=0)
line.append_element(wrap_end, name='wrap_end')
line.build_tracker()

def intensity(line, particles):
    return np.sum(particles.state > 0)/((zeta_max - zeta_min)/tw.beta0/clight)

def z_range(line, particles):
    mask_alive = particles.state > 0
    return particles.zeta[mask_alive].min(), particles.zeta[mask_alive].max()

def long_density(line, particles):
    mask_alive = particles.state > 0
    if not(np.any(particles.at_turn[mask_alive] == 0)): # don't check at the first turn
        assert np.all(particles.zeta[mask_alive] > zeta_min)
        assert np.all(particles.zeta[mask_alive] < zeta_max)
    return np.histogram(particles.zeta[mask_alive], bins=200,
                        range=(zeta_min, zeta_max))

def y_mean_hist(line, particles):

    mask_alive = particles.state > 0
    if not(np.any(particles.at_turn[mask_alive] == 0)): # don't check at the first turn
        assert np.all(particles.zeta[mask_alive] > zeta_min)
        assert np.all(particles.zeta[mask_alive] < zeta_max)
    return np.histogram(particles.zeta[mask_alive], bins=200,
                        range=(zeta_min, zeta_max), weights=particles.y[mask_alive])


line.enable_time_dependent_vars = True
line.track(p, num_turns=200, log=xt.Log(intensity=intensity,
                                         long_density=long_density,
                                         y_mean_hist=y_mean_hist,
                                         z_range=z_range,
                                         ), with_progress=10)

inten = line.log_last_track['intensity']

f_rev_ave = 1 / tw.T_rev0 * (1 - tw.slip_factor * p.delta.mean())
t_rev_ave = 1 / f_rev_ave

inten_exp =  len(p.zeta) / t_rev_ave

import matplotlib.pyplot as plt
plt.close('all')
plt.figure(1)
plt.plot(inten, label='xtrack')
plt.axhline(inten_exp, color='C1', label='expected')
plt.axhline(len(p.zeta) / tw.T_rev0, color='C3', label='N/T_rev0')
plt.legend(loc='best')
plt.xlabel('Turn')

plt.figure(2)
plt.plot(p.delta, p.pdg_id, '.')
plt.ylabel('Missing turns')
plt.xlabel(r'$\delta$')

plt.figure(3)
plt.plot([zz[1]-zz[0] for zz in line.log_last_track['z_range']])
plt.ylabel('z range [m]')
plt.xlabel('Turn')

plt.figure(4)
plt.plot(np.array([0.5*(zz[1] + zz[0]) for zz in line.log_last_track['z_range']]))
plt.plot()
plt.ylabel('z range center [m]')
plt.xlabel('Turn')

z_axis = line.log_last_track['long_density'][0][1]

hist_mat = np.array([rr[0] for rr in line.log_last_track['long_density']])
plt.figure(5)
plt.pcolormesh(z_axis, np.arange(0, hist_mat.shape[0],1),
           hist_mat[:-1,:])

hist_y = np.array([rr[0] for rr in line.log_last_track['y_mean_hist']])
plt.figure(6)
plt.pcolormesh(z_axis, np.arange(0, hist_y.shape[0],1),
           hist_y[:-1,:])

plt.figure(7)
mask_alive = p.state>0
plt.plot(p.zeta[mask_alive], p.y[mask_alive], '.')
plt.axvline(x=circumference/2*tw.beta0/beta1, color='C1')
plt.axvline(x=-circumference/2*tw.beta0/beta1, color='C1')
plt.xlabel('z [m]')
plt.ylabel('x [m]')

dz = z_axis[1] - z_axis[0]
y_vs_t = np.fliplr(hist_y).flatten() # need to flip because of the minus in z = -beta0 c t
intensity_vs_t = np.fliplr(hist_mat).flatten()
z_unwrapped = np.arange(0, len(y_vs_t)) * dz
t_unwrapped = z_unwrapped / (tw.beta0 * clight)

z_range_size = z_axis[-1] - z_axis[0]
t_range_size = z_range_size / (tw.beta0 * clight)

plt.figure(8)
ax1 = plt.subplot(2, 1, 1)
plt.plot(t_unwrapped*1e6, y_vs_t, '-')
plt.ylabel('y mean [m]')
plt.grid()
ax2 = plt.subplot(2, 1, 2, sharex=ax1)
plt.plot(t_unwrapped*1e6, intensity_vs_t, '-')
plt.ylabel('intensity')
plt.xlabel('t [us]')
for tt in t_range_size * np.arange(0, hist_y.shape[0]):
    ax1.axvline(x=tt*1e6, color='red', linestyle='--', alpha=0.5)


plt.show()