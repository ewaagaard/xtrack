import numpy as np

import xpart as xp
import xtrack as xt

particles_ave = xp.Particles(
        p0c=5e9, # 5 GeV
        x=np.zeros(1000000),
        mass0=xp.ELECTRON_MASS_EV)
particles_rnd = particles_ave.copy()

particles_ave._init_random_number_generator()
particles_rnd._init_random_number_generator()

dipole_ave = xt.Multipole(knl=[0.05], length=5, hxl=0.05,
                      radiation_flag=1)
dipole_rnd = xt.Multipole(knl=[0.05], length=5, hxl=0.05,
                      radiation_flag=2)

dipole_ave.track(particles_ave)
dipole_rnd.track(particles_rnd)

dct_ave = particles_ave.to_dict()
dct_rng = particles_rnd.to_dict()

assert np.allclose(dct_ave['delta'], np.mean(dct_rng['delta']),
                  atol=0, rtol= 1e-3)