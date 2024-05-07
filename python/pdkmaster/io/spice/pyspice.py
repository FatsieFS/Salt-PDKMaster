# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
"""This module allows to convert PDKMaster based circuits into PySpice circuits.

Currently PDKMaster only supports to create circuits with primitives from the
technology and does not allow to also SPICE generic elements like a generic resistor
or capacitance. This means that these elements need to be added to the circuit after
they have been converted to PySpice.

This is planned to be tackled in
`#40 <https://gitlab.com/Chips4Makers/PDKMaster/-/issues/40>`_

API Notes:
    * This module is WIP and has no stable API; backwards compatibility may be
      broken at any time.

"""
from typing import Tuple, Dict, Iterable, Optional, Any

from PySpice.Spice.Netlist import Circuit, SubCircuit
from PySpice.Unit import u_µm, u_Ω

from ...typing import cast_MultiT
from .typing import CornerSpec
from .spice_ import SpicePrimsParamSpec
from ...technology import primitive as _prm
from ...design import circuit as _ckt


__all__ = ["PySpiceFactory"]


def _sanitize_name(name):
    return name.replace("(", "[").replace(")", "]")


class _SubCircuit(SubCircuit):
    def __init__(self, *,
        circuit: _ckt._Circuit, params: SpicePrimsParamSpec, lvs: bool,
    ):
        ports = tuple(_sanitize_name(port.name) for port in circuit.ports)
        name = _sanitize_name(circuit.name)

        super().__init__(name, *ports)
        self._circuit = circuit

        netlookup = {}
        for net in circuit.nets:
            lookup = {port: net for port in net.childports}
            double = tuple(filter(lambda n: n in netlookup, lookup))
            if double:
                doublenames = tuple(net.full_name for net in double)
                raise ValueError(
                    f"Ports {doublenames} are on more than one net in circuit "
                    f"{circuit.name}"
                )
            netlookup.update(lookup)

        for inst in circuit.instances:
            for port in inst.ports:
                try:
                    netlookup[port]
                except KeyError:
                    raise ValueError(
                        f"Port '{port.full_name}' not on any net in circuit "
                        f"'{name}'"
                    )

            if isinstance(inst, _ckt._PrimitiveInstance):
                assert isinstance(inst.prim, _prm.DevicePrimitiveT)
                prim_params = params[inst.prim]
                model: str = prim_params["model"]
                is_subcircuit: bool = prim_params["is_subcircuit"]

                if isinstance(inst.prim, _prm.MOSFET):
                    sgdb = []
                    for portname in (
                        "sourcedrain1", "gate", "sourcedrain2", "bulk",
                    ):
                        port = inst.ports[portname]
                        net = netlookup[port]
                        sgdb.append(_sanitize_name(net.name))
                    # TODO: support more instance parameters
                    if not is_subcircuit:
                        self.M(
                            inst.name, *sgdb, model=model,
                            l=u_µm(round(inst.params["l"],6)),
                            w=u_µm(round(inst.params["w"],6)),
                        )
                    else:
                        self.X(
                            inst.name, model, *sgdb,
                            l=u_µm(round(inst.params["l"],6)),
                            w=u_µm(round(inst.params["w"],6)),
                        )
                elif isinstance(inst.prim, _prm.Bipolar):
                    cbe = []
                    for portname in ("collector", "base", "emitter"):
                        port = inst.ports[portname]
                        net = netlookup[port]
                        cbe.append(_sanitize_name(net.name))
                    if not is_subcircuit:
                        self.Q(inst.name, *cbe, model=model)
                    else:
                        self.X(inst.name, model, *cbe)
                elif isinstance(inst.prim, _prm.Resistor):
                    sheetres = prim_params["sheetres"]
                    subcircuit_paramalias: Optional[Dict[str, str]] = prim_params["subcircuit_paramalias"]

                    has_model = model is not None
                    has_sheetres = sheetres is not None
                    assert (
                        has_model or has_sheetres
                    ), (
                        "Not implemented: Resistor without model or sheet resistance"
                    )

                    w = inst.params["width"]
                    l = inst.params["length"]
                    if (not has_model) or lvs:
                        assert sheetres is not None
                        self.R(
                            inst.name,
                            _sanitize_name(netlookup[inst.ports.port1].name),
                            _sanitize_name(netlookup[inst.ports.port2].name),
                            u_Ω(round(sheetres*l/w, 10)),
                        )
                    else:
                        assert has_model
                        if not is_subcircuit:
                            assert subcircuit_paramalias is None
                            assert sheetres is not None
                            self.SemiconductorResistor(
                                inst.name,
                                _sanitize_name(netlookup[inst.ports.port1].name),
                                _sanitize_name(netlookup[inst.ports.port2].name),
                                u_Ω(round(sheetres*l/w, 10)),
                                model=model, w=u_µm(round(w, 6)), l=u_µm(round(l, 6)),
                            )
                        else:
                            if subcircuit_paramalias is None:
                                subcircuit_paramalias = {"width": "w", "length": "l"}
                            model_args = {
                                subcircuit_paramalias["width"]: u_µm(round(w, 6)),
                                subcircuit_paramalias["length"]: u_µm(round(l, 6)),
                            }
                            self.X(
                                inst.name, model,
                                _sanitize_name(netlookup[inst.ports.port1].name),
                                _sanitize_name(netlookup[inst.ports.port2].name),
                                **model_args,
                            )
                elif isinstance(inst.prim, _prm.MIMCapacitor):
                    subcircuit_paramalias: Optional[Dict[str, str]] = prim_params["subcircuit_paramalias"]
                    if not is_subcircuit:
                        raise NotImplementedError("MIMCapacitor not a subcircuit")
                    if lvs:
                        raise NotImplementedError("MIMCapicator spice element for LVS")

                    w = inst.params["width"]
                    h = inst.params["height"]
                    if subcircuit_paramalias is None:
                        subcircuit_paramalias = {"width": "w", "height": "h"}
                    model_args = {
                        subcircuit_paramalias["width"]: u_µm(round(w, 6)),
                        subcircuit_paramalias["height"]: u_µm(round(h, 6)),
                    }
                    # TODO: Make port order configurable
                    self.X(
                        inst.name, model,
                        _sanitize_name(netlookup[inst.ports.top].name),
                        _sanitize_name(netlookup[inst.ports.bottom].name),
                        **model_args,
                    )
                elif isinstance(inst.prim, _prm.Diode):
                    subcircuit_paramalias: Optional[Dict[str, str]] = prim_params["subcircuit_paramalias"]
                    w = inst.params["width"]
                    h = inst.params["height"]
                    if not is_subcircuit:
                        assert subcircuit_paramalias is None
                        self.D(
                            inst.name,
                            _sanitize_name(netlookup[inst.ports.anode].name),
                            _sanitize_name(netlookup[inst.ports.cathode].name),
                            model=model, area=round(w*h, 6)*1e-12, pj=u_µm(round(2*(w + h), 6)),
                        )
                    else:
                        if subcircuit_paramalias is None:
                            subcircuit_paramalias = {"width": "w", "height": "h"}
                        model_args = {
                            subcircuit_paramalias["width"]: u_µm(round(w, 6)),
                            subcircuit_paramalias["height"]: u_µm(round(h, 6)),
                        }
                        self.X(
                            inst.name, model,
                            _sanitize_name(netlookup[inst.ports.anode].name),
                            _sanitize_name(netlookup[inst.ports.cathode].name),
                            **model_args,
                        )
            elif isinstance(inst, _ckt._CellInstance):
                pin_args = tuple()
                for port in inst.ports:
                    net = netlookup[port]
                    pin_args += (net.name,)
                pin_args = tuple(
                    _sanitize_name(netlookup[port].name) for port in inst.ports
                )
                self.X(inst.name, _sanitize_name(inst.circuit.name), *pin_args)
            else: # pragma: no cover
                raise AssertionError("Internal error")


class _Circuit(Circuit):
    def __init__(self, *,
        fab: "PySpiceFactory", corner: CornerSpec, top: _ckt._Circuit,
        subckts: Optional[Iterable[_ckt._Circuit]], title: Optional[str], gnd: Optional[str],
    ):
        if title is None:
            title = f"{top.name} testbench"
        super().__init__(title)

        corner = cast_MultiT(corner)
        invalid = tuple(filter(lambda c: c not in fab.corners, corner))
        if invalid:
            raise ValueError(f"Invalid corners(s) {invalid}")
        for c in corner:
            try:
                conflicts = fab.conflicts[c]
            except KeyError:
                pass
            else:
                for c2 in conflicts:
                    if c2 in corner:
                        raise ValueError(
                            f"Corner '{c}' conflicts with corner '{c2}'"
                        )
            self.lib(fab.libfile, c)

        self._fab = fab
        self._corner = corner

        if subckts is None:
            scan = [top]
            scanned = []

            while scan:
                circuit = scan.pop()
                try:
                    # If it is in the scanned list put the circuit at the end
                    scanned.remove(circuit)
                except ValueError:
                    # If it is not in the scanned list, add subcircuits in the scan list
                    for inst in circuit.instances.__iter_type__(_ckt._CellInstance):
                        circuit2 = inst.cell.circuit
                        try:
                            scan.remove(circuit2)
                        except ValueError:
                            pass
                        scan.append(circuit2)
                scanned.append(circuit)
            scanned.reverse()
            subckts = scanned
        psubckts = tuple(
            fab.new_pyspicesubcircuit(circuit=c) for c in (*subckts, top)
        )
        for subckt in psubckts:
            self.subcircuit(subckt)
        self.X(
            "top", top.name,
            *(self.gnd if node==gnd else node for node in psubckts[-1]._external_nodes),
        )

    # Stop pylance from deriving types from PySpice code
    def simulator(self, *args, **kwargs) -> Any: # pragma: no cover
        return super().simulator(*args, **kwargs)


class PySpiceFactory:
    """The ``PySpiceFactory`` allows to convert ``_Circuit`` objects generated
    through ``CircuitFactory`` object to ``PySpice`` circuits and sub circuits.

    Typically the PDK provider will also provide a ``PySpiceFactory`` object that
    allows to convert to ``PySpice`` objects that use the SPICE
    simulation files provided by the PDK.

    Parameters:
        libfile: the full path to the SPICE lib file to include in the generated SPICE
            objects
        corners: A list of valid corners for this lib file.
        conflicts: For a given corner it gives the conrers with which it conflicts,
            e.g. if you have:

                ``"typ": ("ff", "ss"),``

            as an element in the dict it means that you can't specify ``"typ"`` corner
            with the ``"ff"`` and ``"ss"`` corner.
        prims_params: extra parameters for the models of ``DevicePrimitiveT`` object.
            See ``SpicePrimsParamSpec`` for more information.

    API Notes:
        * The API of ``PySpiceFactory`` is in flux and no backwards compatiblity
          guarantees are given at this moment.
    """
    def __init__(self, *,
        libfile: str, corners: Iterable[str], conflicts: Dict[str, Tuple[str, ...]],
        prims_params: SpicePrimsParamSpec,
    ):
        s = (
            "conflicts has to be a dict where the element value is a list of corners\n"
            "that conflict with the key"
        )
        for key, value in conflicts.items():
            if (key not in corners) or any(c not in corners for c in value):
                raise ValueError(s)

        self.libfile = libfile
        self.corners = set(corners)
        self.conflicts = conflicts
        self.prims_params = prims_params

    def new_pyspicecircuit(self, *,
        corner: CornerSpec, top: _ckt._Circuit,
        subckts: Optional[Iterable[_ckt._Circuit]]=None, title: Optional[str]=None,
        gnd: Optional[str]=None,
    ):
        """This method converts a PDKMaster ``_Circuit`` object to a PySpice
        ``Circuit`` object.

        The returned object type is actually a cubclass of the PySpice `Circuit` class.

        Parameters:
            corner: The corner(s) valid for the Circuit.
                This needs to be a valid corner as specified during ``PySpiceFactory``
                init.
            top: The top circuit for the generated PySpice ``Circuit`` object.
                The top circuit will be included in the PySpice ``Circuit`` as a
                subcircuit and then instantiated as `Xtop`. For each of the pins
                a net in the SPICE top level will be generated with the same name.
            subckts: An optional list of subcircuits.
                These will be included in the generated object as PySpice subcircuits.
                If not provided a list will be generated hierarchically from the given
                top Circuit.
            title: An optional title to set in the generated PySpice object.
            gnd: An optional name of the ground net name in the circuit.
        """
        return _Circuit(
            fab=self, corner=corner, top=top, subckts=subckts, title=title,
            gnd=gnd,
        )

    def new_pyspicesubcircuit(self, *, circuit: _ckt._Circuit, lvs: bool=False):
        """This method convert a PDKMaster ``_Circuit`` object to a PySpice
        ``SubCircuit`` object.

        The returned object type is actually a subclass of the PySpice ``SubCircuit``
        class.

        Parameters:
            circuit: The circuit to make a PySpice ``Circuit`` for.
            lvs: wether to generate a subcircuit for (klayout) based.
                lvs generated circuit may use other device primitive in the generated
                netlists than the other ones that are mainly to be used in simulation.
        """
        return _SubCircuit(circuit=circuit, params=self.prims_params, lvs=lvs)
