# from collections import ChainMap  # Might use eventually
import numpy as np
from openpnm.phases import GenericPhase as GenericPhase
from openpnm.utils import logging, HealthDict, PrintableList
logger = logging.getLogger(__name__)


class GenericMixture(GenericPhase):
    r"""
    Creates Phase object that represents a multicomponent mixture system
    consisting of a given list of OpenPNM Phase objects as components.

    Parameters
    ----------
    network : OpenPNM Network object
        The network to which this phase object will be attached.

    components : list of OpenPNM Phase objects
        A list of all components that constitute this mixture

    project : OpenPNM Project object, optional
        The Project with which this phase should be associted.  If a
        ``network`` is given then this is ignored and the Network's project
        is used.  If a ``network`` is not given then this is mandatory.

    name : string, optional
        The name of the phase.  This is useful to keep track of the objects
        throughout the simulation.  The name must be unique to the project.
        If no name is given, one is generated.

    """
    def __init__(self, components=[], settings={}, **kwargs):
        self.settings.update({'components': [],
                              })
        super().__init__(**kwargs)
        self.settings.update(settings)

        # Add any supplied phases to the phases list
        for comp in components:
            self.settings['components'].append(comp.name)
            self['pore.mole_fraction.'+comp.name] = 0.0

        self['pore.mole_fraction.all'] = np.zeros(self.Np, dtype=float)

    def __getitem__(self, key):
        try:
            vals = super().__getitem__(key)
        except KeyError:
            try:
                # If key ends in component name, fetch it
                if key.split('.')[-1] in self.settings['components']:
                    comp = self.project[key.split('.')[-1]]
                    vals = comp[key.rsplit('.', maxsplit=1)[0]]
                    return vals
                else:
                    raise KeyError
            except KeyError:
                vals = self.interleave_data(key)
        return vals

    def __setitem__(self, key, value):
        prop = '.'.join(key.split('.')[:2])
        invalid_keys = set(self.props()).difference(set(self.keys()))
        # invalid_keys = []
        # [invalid_keys.extend(item.keys()) for item in self.components.values()]
        if prop in invalid_keys:
            raise Exception(prop + ' already assigned to a component object')
        super().__setitem__(key, value)

    def props(self, deep=False, **kwargs):
        temp = PrintableList()
        if deep:
            for item in self.components.values():
                temp.extend([prop+'.'+item.name for prop in item.props(**kwargs)])
        temp.extend(super().props(**kwargs))
        temp.sort()
        return temp

    def __str__(self):
        horizontal_rule = '―' * 78
        lines = super().__str__()
        lines = '\n'.join((lines, 'Component Phases', horizontal_rule))
        for item in self.components.values():
            lines = '\n'.join((lines, item.__module__.replace('__', '') +
                               ' : ' + item.name))
        lines = '\n'.join((lines, horizontal_rule))
        return lines

    def _update_total_molfrac(self):
        # Update concentration.all
        self['pore.mole_fraction.all'] = 0.0
        dict_ = list(self['pore.mole_fraction'].values())
        if len(dict_) > 1:
            self['pore.mole_fraction.all'] = np.sum(dict_, axis=0)
        self['throat.mole_fraction.all'] = 0.0
        dict_ = list(self['throat.mole_fraction'].values())
        if len(dict_) > 1:
            self['throat.mole_fraction.all'] = np.sum(dict_, axis=0)

    def update_mole_fractions(self, concentration=None, molar_density=None):
        r"""
        Re-calculate mole fractions of each species in mixture

        This method looks up the concentration of each species (using the
        optionally specified concentration dictionary key), and calculates
        the mole fraction.

        Parameters
        ----------
        concentration : string, optional
            The dictionary key pointing to the desired concentration values.
            The default is 'pore.concentration'.
        molar_density : string, optional
            The dictionary key pointing to the molar density of the mixture.
            If not given (default), all species must have a specified value of
            concentration.  If given, then only N-1 species must have a
            specified concentration value, where N is the total number of
            species in the mixture.  This is useful for air, where the O2
            concentration may be known, then the ideal gas law can be used
            to find the ``molar_density``, then the N2 mole fraction can be
            inferred.

        Notes
        -----
        The method does not return any values.  Instead it updates the mole
        fraction arrays of each species directly.
        """
        if concentration is None:
            concentration = ['pore.concentration.'+comp for comp
                             in self.settings['components']
                             if 'pore.concentration.'+comp in self.keys()]
        if type(concentration) == str:
            concentration = [concentration]
        if molar_density is None:
            if len(concentration) < len(self.components):
                raise Exception('Insufficient concentration values found on ' +
                                'component species, must specify molar_density')
            # Find total number of moles per unit volume
            density = 0.0
            for conc in concentration:
                density += self[conc]
            # Normalize moles per unit volume for each species by the total
            for conc in concentration:
                element, quantity, component = conc.split('.')
                self[element+'.mole_fraction.'+component] = self[conc]/density
        else:
            n_spec = len(concentration) - len(self.components)
            if n_spec < -1:
                raise Exception('Insufficient concentration values found' +
                                'on component species, must specify ' +
                                str(n_spec + 1) + ' additional values')
            elif n_spec == 0:
                raise Exception('Concentration values found for all ' +
                                'component species, cannot apply specified ' +
                                'molar_density')
            else:  # n_spec == -1, so correct number of DoF
                # Find mole fraction of N-1 species
                mol_frac = 0.0
                density = self[molar_density]
                for conc in concentration:
                    element, quantity, component = conc.split('.')
                    self[element+'.mole_fraction.'+component] = self[conc]/density
                    mol_frac += self[element+'.mole_fraction.'+component]
                # Find mole fraction of Nth species using molar_density
                given_comps = [conc.split('.')[2] for conc in concentration]
                all_comps = self.settings['components']
                component = list(set(all_comps).difference(set(given_comps)))[0]
                self[element+'.mole_fraction.'+component] = 1 - mol_frac

    def set_mole_fraction(self, component, values=[]):
        r"""
        Specify mole fraction of each component in each pore

        Parameters
        ----------
        components : OpenPNM Phase object or name string
            The phase whose mole fraction is being specified

        values : array_like
            The mole fraction of ``component `` in each pore.  This array must
            be *Np*-long, with one value between 0 and 1 for each pore in the
            network.  If a scalar is received it is applied to all pores.

        """
        if type(component) == str:
            component = self.components[component]
        Pvals = np.array(values, ndmin=1)
        if component not in self.project:
            raise Exception(f"{component.name} doesn't belong to this project")
        else:
            if component.name not in self.settings['components']:
                self.settings['components'].append(component.name)
        if np.any(Pvals > 1.0) or np.any(Pvals < 0.0):
            logger.warning('Received Pvals contain mole fractions outside ' +
                           'the range of 0 to 1')
        if Pvals.size:
            self['pore.mole_fraction.' + component.name] = Pvals
        self._update_total_molfrac()

    def _get_comps(self):
        comps = {item: self.project[item] for item in self.settings['components']}
        return comps

    def _set_comps(self, components):
        if not isinstance(components, list):
            components = [components]
        self.settings['components'] = [val.name for val in components]

    components = property(fget=_get_comps, fset=_set_comps)

    def interleave_data(self, prop):
        r"""
        Gathers property values from component phases to build a single array

        If the requested ``prop`` is not on this Mixture, then a search is
        conducted on all associated components objects, and values from each
        are assembled into a single array.

        Parameters
        ----------
        prop : string
            The property to be retrieved

        Returns
        -------
        array : ND-array
            An array containing the specified property retrieved from each
            component phase and assembled based on the specified mixing rule

        """
        element = prop.split('.')[0]
        if element == 'pore':
            if np.any(self[element + '.mole_fraction.all'] != 1.0):
                self._update_total_molfrac()
                if np.any(self[element + '.mole_fraction.all'] != 1.0):
                    raise Exception('Mole fraction does not add to unity in all ' +
                                    element + 's')
        vals = np.zeros([self._count(element=element)], dtype=float)
        try:
            for comp in self.components.values():
                vals += comp[prop]*self[element+'.mole_fraction.'+comp.name]
        except KeyError:
            vals = super().interleave_data(prop)
        return vals

    def check_mixture_health(self):
        r"""
        Checks the "health" of the mixture

        Calculates the mole fraction of all species in each pore and returns
        an list of where values are too low or too high

        Returns
        -------
        health : dict
            A HealtDict object containing lists of locations where the mole
            fractions are not unity.  One value indiates locations that are
            too high, and another where they are too low.

        """
        h = HealthDict()
        h['mole_fraction_too_low'] = []
        h['mole_fraction_too_high'] = []
        self._update_total_molfrac()
        lo = np.where(self['pore.mole_fraction.all'] < 1.0)[0]
        hi = np.where(self['pore.mole_fraction.all'] > 1.0)[0]
        if len(lo) > 0:
            h['mole_fraction_too_low'] = lo
        if len(hi) > 0:
            h['mole_fraction_too_high'] = hi
        return h