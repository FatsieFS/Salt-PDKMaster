# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
"""This module contains support for direct SPICE input and output.
"""
from textwrap import dedent
from typing import Dict, Set, Union, Optional, Iterable, overload, Any

from ...typing import MultiT, cast_MultiT
from ...technology import primitive as _prm, technology_ as _tch
from ...design import circuit as _ckt, library as _lbry

from ._util import _sanitize_name


__all__ = ["SpicePrimParamsT", "SpicePrimsParamSpec", "SpiceNetlistFactory"]


SpicePrimParamsT = Dict[str, Any]
class SpicePrimsParamSpec(Dict[_prm.DevicePrimitiveT, SpicePrimParamsT]):
    """``SpicePrimsParamSpec`` is a structure to declare extra parameters related
    to ``DevicePrimitiveT`` object of a technology that are needed specifically
    to generate SPICE/PySpice circuits.

    This class is used by first generating an empty object and then adding
    SPICE parameters for primitives using the ``add_device_params()`` method.
    """
    def __init__(self) -> None:  # We don't support arguments during creatinn of the object
        return super().__init__()

    def __setitem__(self, __key: _prm.DevicePrimitiveT, __value: SpicePrimParamsT) -> None:
        raise TypeError(
            "One must use add_device_params() method to add element to"
            " a SpicePrimsParamSpec object",
        )

    @overload
    def add_device_params(self, *,
        prim: _prm.Resistor, model: Optional[str]=None, is_subcircuit: Optional[bool]=False,
        subcircuit_paramalias: Optional[Dict[str, str]]=None,
        sheetres: Optional[float]=None,
    ):
        ... # pragma: no cover
    @overload
    def add_device_params(self, *,
        prim: Union[_prm.MIMCapacitor, _prm.Diode], model: Optional[str]=None,
        is_subcircuit: Optional[bool]=True,
        subcircuit_paramalias: Optional[Dict[str, str]]=None,
    ):
        ... # pragma: no cover
    @overload
    def add_device_params(self, *,
        prim: _prm.MOSFET, model: Optional[str]=None,
        is_subcircuit: Optional[bool]=False,
    ):
        ... # pragma: no cover
    @overload
    def add_device_params(self, *,
        prim: _prm.Bipolar, model: Optional[str]=None, is_subcircuit: Optional[bool]=False,
    ):
        ... # pragma: no cover
    def add_device_params(self, *,
        prim: _prm.DevicePrimitiveT, model: Optional[str]=None,
        is_subcircuit: Optional[bool]=None,
        **params: Any,
    ):
        """The ``add_device_params()`` method is called at most once for each device
        primitive one wants to add params for. The params that can be specified depend
        on the device primitive type.

        Parameters:
            model:
                alternative model name for use in SPICE circuit.

                By default the name of the primitive is also used as the SPICE model
                name
            is_subcircuit:
                wether the model is a SPICE subcircuit or element

                Default is ``True`` for a ``MIMCapacitor`` and ``False`` for the other
                device primitives.
            subcircuit_paramalias (for ``Resistor``, ``MIMCapacitor`` and ``Diode``):
                alias for parameters for the subcircuit model.

                This value is a dict that specifies the alias for the parameters of the
                primitive. The keys the names of the parameter for the ``DevicePrimitiveT``
                the values the name of the parameter used by the SPICE subcircuit.

                Either no parameter has to be specified are all of them. It may not be
                specified when ``is_subcircuit`` is ``False``.

                Default values:

                * for ``Resistor``: ``{"width": "w", "length": "l"}``,
                * for ``MIMCapacitor``: ``{"width": "w", "height": "h"}``,
                * for ``Diode``: ``{"width": "w", "height": "h"}``,

            sheetres (for ``Resistor``):
               the sheet resistance for the ``Resistor`` primitive
        """
        if is_subcircuit is None:
            if isinstance(prim, _prm.MIMCapacitor):
                is_subcircuit = True
            else:
                is_subcircuit = False
        params["is_subcircuit"] = is_subcircuit

        if isinstance(prim, (_prm.Resistor, _prm.MIMCapacitor, _prm.Diode)):
            # handle subcircuit_paramalias parameter
            subcircuit_paramalias: Optional[Dict[str, str]] = params.get("subcircuit_paramalias", None)
            if subcircuit_paramalias is not None:
                if not is_subcircuit:
                    raise ValueError(
                        "subcircuit_paramalias specified with is_subcircuit `False`",
                    )
                keys = (
                    {"width", "length"} if isinstance(prim, _prm.Resistor)
                    else {"width", "height"}
                )
                if set(subcircuit_paramalias.keys()) != keys:
                    raise ValueError(
                        f"subcircuit_paramalias has to be None or a dict with keys {keys}"
                    )
            params["subcircuit_paramalias"] = subcircuit_paramalias

        if isinstance(prim, _prm.Resistor):
            # handle sheetres param
            params["sheetres"] = params.get("sheetres", None)

        if model is None:
            if isinstance(prim, _prm.Resistor):
                # For a Resistor primitive, model name may be None if sheetres is specified.
                if params["sheetres"] is None:
                    model = prim.name
                else:
                    if params["subcircuit_paramalias"] is not None:
                        raise TypeError(
                            "subcircuit_paramalias provided without a model for Resistor"
                            f" '{prim.name}'"
                        )
            else:
                # For other primitives use the primitive name as model name if it was not
                # specified
                model = prim.name
        params["model"] = model

        super().__setitem__(prim, params)


# Use cases to support:
# * SPICE netlist export as a view for a library
# * SPICE netlist as input for a ngspice simulator
class SpiceNetlistFactory:
    """This class allow to generate a SPICE netlist from a PDKMaster circuit.

    Currently this support syntax support by original spice simulator and thus also by
    ngspice
    """
    def __init__(self, params: SpicePrimsParamSpec):
        self._params = params

    @property
    def params(self) -> SpicePrimsParamSpec:
        return self._params

    def export_circuit(self, circuit: _ckt.CircuitT, *, use_semiconres: bool=True) -> str:
        "Convert a circuit to a SPICE netlist with a single .subckt section"
        return "\n".join(
            self._export_circuit_lines(circuit=circuit, use_semiconres=use_semiconres),
        ) + "\n"

    def _export_circuit_lines(self, circuit: _ckt.CircuitT, *,
        use_semiconres: bool,
    ) -> Iterable[str]:
        params = self.params
        name = _sanitize_name(circuit.name)

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

        portnames = tuple(_sanitize_name(port.name) for port in circuit.ports)
        yield f".subckt {name} {' '.join(portnames)}"

        for inst in circuit.instances:
            inst_name = _sanitize_name(inst.name)

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
                    first = "X" if is_subcircuit else "M"
                    # TODO: support more instance parameters
                    l = inst.params["l"]*1e-6
                    w = inst.params["w"]*1e-6
                    yield f"{first}{inst_name} {' '.join(sgdb)} {model} l={l:.4g} w={w:.4g}"
                elif isinstance(inst.prim, _prm.Bipolar):
                    first = "X" if is_subcircuit else "Q"
                    cbe = []
                    for portname in ("collector", "base", "emitter"):
                        port = inst.ports[portname]
                        net = netlookup[port]
                        cbe.append(_sanitize_name(net.name))
                    yield f"{first}{inst_name} {' '.join(cbe)} {model}"
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

                    w = inst.params["width"]*1e-6
                    l = inst.params["length"]*1e-6
                    port1 = _sanitize_name(netlookup[inst.ports.port1].name)
                    port2 = _sanitize_name(netlookup[inst.ports.port2].name)
                    if not has_model:
                        assert sheetres is not None
                        r = sheetres*l/w
                        yield f"R{inst_name} {port1} {port2} {r:.10e}"
                    else:
                        assert has_model
                        if not is_subcircuit:
                            assert subcircuit_paramalias is None
                            assert sheetres is not None
                            r = sheetres*l/w
                            if use_semiconres:
                                yield f"R{inst_name} {port1} {port2} {r:.10e} {model} l={l:.4g} w={w:.4g}"
                            else:
                                yield f"R{inst_name} {port1} {port2} {r:.10e}"
                        else:
                            if subcircuit_paramalias is None:
                                subcircuit_paramalias = {"width": "w", "length": "l"}
                            lparam = subcircuit_paramalias["length"]
                            wparam = subcircuit_paramalias["width"]
                            yield f"X{inst_name} {port1} {port2} {model} {lparam}={l:.4g} {wparam}={w:.4g}"
                elif isinstance(inst.prim, _prm.MIMCapacitor):
                    subcircuit_paramalias: Optional[Dict[str, str]] = prim_params["subcircuit_paramalias"]
                    if not is_subcircuit:
                        raise NotImplementedError("MIMCapacitor not a subcircuit")

                    w = inst.params["width"]*1e-6
                    h = inst.params["height"]*1e-6
                    if subcircuit_paramalias is None:
                        subcircuit_paramalias = {"width": "w", "height": "h"}
                    wparam = subcircuit_paramalias["width"]
                    hparam = subcircuit_paramalias["height"]
                    # TODO: Make port order configurable
                    port1 = _sanitize_name(netlookup[inst.ports.top].name)
                    port2 = _sanitize_name(netlookup[inst.ports.bottom].name)
                    yield f"X{inst_name} {port1} {port2} {model} {wparam}={w:.4g} {hparam}={h:.4g}"
                elif isinstance(inst.prim, _prm.Diode):
                    subcircuit_paramalias: Optional[Dict[str, str]] = prim_params["subcircuit_paramalias"]
                    w = inst.params["width"]*1e-6
                    h = inst.params["height"]*1e-6
                    an = _sanitize_name(netlookup[inst.ports.anode].name)
                    cat = _sanitize_name(netlookup[inst.ports.cathode].name)
                    if not is_subcircuit:
                        assert subcircuit_paramalias is None
                        yield f"D{inst_name} {an} {cat} {model} area={w*h:.6g} pj={2*(w+h):.4g}"
                    else:
                        if subcircuit_paramalias is None:
                            subcircuit_paramalias = {"width": "w", "height": "h"}
                        wparam = subcircuit_paramalias["width"]
                        hparam = subcircuit_paramalias["height"]
                        yield f"X{inst_name} {an} {cat} {model} {wparam}={w:.4g} {hparam}={h:.4g}"
            elif isinstance(inst, _ckt._CellInstance):
                port_nets = tuple(
                    _sanitize_name(netlookup[port].name) for port in inst.ports
                )
                yield f"X{inst_name} {' '.join(port_nets)} {_sanitize_name(inst.circuit.name)}"
            else: # pragma: no cover
                raise AssertionError("Internal error")

        yield f".ends {name}"

    def export_circuits(self, circuits: MultiT[_ckt.CircuitT], *,
        add_subcircuits: bool=True, use_semiconres: bool=True,
    ) -> str:
        added = set()

        s = ""
        for ckt in cast_MultiT(circuits):
            if ckt not in added:
                if s:
                    s += "\n"
                s += "\n".join(self._export_circuits_recurs(
                    ckt, add_subcircuits=add_subcircuits, use_semiconres=use_semiconres,
                    added=added,
                ))

        return s

    def _export_circuits_recurs(self, circuit: _ckt.CircuitT, *,
        add_subcircuits: bool, use_semiconres: bool,
        added: Set[_ckt.CircuitT],
    ) -> Iterable[str]:
        if add_subcircuits:
            for inst in circuit.instances.__iter_type__(_ckt._CellInstance):
                ckt2 = inst.cell.circuit
                if ckt2 not in added:
                    yield from self._export_circuits_recurs(ckt2,
                        add_subcircuits=add_subcircuits, use_semiconres=use_semiconres,
                        added=added,
                    )

        yield self.export_circuit(circuit, use_semiconres=use_semiconres)
        added.add(circuit)

    def _export_subcircuits(self) -> Iterable[str]:
        for prim, params in self.params.items():
            is_subckt = params.get("is_subcircuit", False)
            if is_subckt:
                model_name = params.get("model", prim.name)
                if isinstance(prim, _prm.Resistor):
                    sheetres = params["sheetres"]
                    pres = f"{model_name}_res"
                    yield dedent(f"""\
                        .subckt {model_name} n1 n2 l=1e-6 w=1e-6
                        .param {pres}={{l*{sheetres}/w}}
                        Rres n1 n2 r={{{pres}}} {model_name} l=l w=w
                        .ends {model_name}
                    """)
                elif isinstance(prim, _prm.Diode):
                    alias = params.get("subcircuit_paramalias")
                    if alias is None:
                        alias = dict(width="width", height="height")
                    w_name = alias["width"]
                    h_name = alias["height"]
                    min_wh = round(prim.min_width, 6)
                    yield dedent(f"""\
                        .subckt {model_name} an cat params: {w_name}={min_wh}e-6 {h_name}={min_wh}e-6
                        Ddio an cat {model_name} a=({w_name}*{h_name}) p=(2*({w_name} + {h_name}))
                        .ends {model_name}
                    """)
                elif isinstance(prim, _prm.MOSFET):
                    min_l = round(prim.computed.min_l, 6)
                    min_w = round(prim.computed.min_w, 6)
                    yield dedent(f"""\
                        .subckt {model_name} s g d b params: l={min_l}e-6 w={min_w}e-6
                        Mtrans s g d b {model_name} l=l w=w
                        .ends {model_name}
                    """)

    def export_library(self, lib: _lbry.Library, *,
        header: str="", use_semiconres: bool=True, incl_dummysubcircuits: bool=False,
    ) -> str:
        if not incl_dummysubcircuits:
            s_subckts = ""
        else:
            s_subckts = (
                "\n* Device subcircuits\n*\n"
                + "\n".join(self._export_subcircuits())
                + "\n* Library cells\n*\n"
            )
        s_ckts = self.export_circuits(
            (cell.circuit for cell in lib.cells),
            add_subcircuits=True, use_semiconres=use_semiconres,
        )
        return (
            f"* {lib.name}\n"
            f"{header}\n"
            f"{s_subckts}{s_ckts}\n"
        )
