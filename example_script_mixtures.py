import openpnm as op
from openpnm.phases import mixtures
ws = op.Workspace()
proj = ws.new_project()

pn = op.network.Cubic(shape=[30, 30, 10], spacing=1e-4, project=proj)
geo = op.geometry.StickAndBall(network=pn, pores=pn.Ps, throats=pn.Ts)

N2 = mixtures.species.gases.N2(network=pn, name='pure_N2')
O2 = mixtures.species.gases.O2(network=pn, name='pure_O2')
CO2 = mixtures.species.gases.CO2(network=pn, name='pure_CO2')
H2 = mixtures.species.gases.H2(network=pn, name='pure_H2')
air = mixtures.GenericMixture(network=pn, components=[N2, O2, H2, CO2],
                              name='air_mixture')
air.set_mole_fraction(N2, 0.790)
air.set_mole_fraction(O2, 0.209)
air.set_mole_fraction(CO2, 0.001)
air.add_model(propname='pore.molar_mass',
              model=op.models.phases.mixtures.mole_weighted_average,
              prop='pore.molecular_weight')
#air.add_model(propname='pore.diffusivity.pure_O2',
#              species_A=O2.name, species_B=N2.name,
#              model=op.models.phases.mixtures.fuller_diffusivity)
air.add_model(propname='pore.diffusivity.pure_O2',
              species_A=O2.name,
              model=op.models.phases.mixtures.wilke_fuller_diffusivity,
              regen_mode='iterative')
air.add_model(propname='pore.viscosity',
              model=op.models.misc.polynomial,
              prop='pore.temperature',
              a=[0.00000182082, 6.51815E-08, -3.48553E-11, 1.11409E-14])
air.add_model(propname='pore.molar_density',
              model=op.models.phases.density.ideal_gas)

phys = op.physics.GenericPhysics(network=pn, phase=air, geometry=geo)
phys.add_model(propname='throat.diffusive_conductance',
               pore_diffusivity='pore.diffusivity.pure_O2',
               model=op.models.physics.diffusive_conductance.ordinary_diffusion)
phys.add_model(propname='throat.hydraulic_conductance',
               pore_diffusivity='pore.viscosity',
               model=op.models.physics.hydraulic_conductance.classic_hagen_poiseuille)

sf = op.algorithms.StokesFlow(network=pn, phase=air)
sf.set_value_BC(pores=pn.pores('left'), values=200000)
sf.set_value_BC(pores=pn.pores('right'), values=100000)
sf.run()
air.update(sf.results())

air.regenerate_models()

fd = op.algorithms.FickianDiffusion(network=pn, phase=air)
fd.setup(quantity='pore.concentration.pure_O2')
fd.set_value_BC(pores=pn.pores('left'), values=1)
fd.set_value_BC(pores=pn.pores('right'), values=0)
fd.run()
air.update(fd.results())