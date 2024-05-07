"""Generate a pdkmaster technology file

This module is currently not used and likely does not produce usable results.
It is adviced to not use this module in it's current state; no support whatsoever
is given on this module.  
The module was originally used by the TSMC 0.18 PDKMaster PDK. This PDK is currently
not maintained and is not up to date with recent API chances. This module will need
to be updated if the TSMC 0.18 is updated.
"""
# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from textwrap import indent, dedent
from typing import Tuple, Optional

from ... import dispatch as _dsp
from ...technology import (
    property_ as _prp, primitive as _prm, mask as _msk, technology_ as _tch,
)
from ...design import circuit as _ckt, library as _lbry


__all__ = ["generate"]


def _str_prim(prim: _prm.PrimitiveT):
    return f"prims['{prim.name}']"


def _str_primtuple(t: Tuple[_prm.PrimitiveT, ...]):
    if len(t) == 0:
        return "tuple()"
    elif len(t) == 1:
        return _str_prim(t[0])
    else:
        return f"({', '.join(_str_prim(p) for p in t)})"


def _str_enclosure(enc: Optional[_prp.Enclosure]):
    return "None" if enc is None else f"Enclosure({enc.spec})"


def _str_enclosures(encs: Tuple[Optional[_prp.Enclosure], ...]):
    if len(encs) == 1:
        return f"({_str_enclosure(encs[0])},)"
    else:
        return f"({','.join(_str_enclosure(enc) for enc in encs)})"


class _PrimitiveGenerator(_dsp.PrimitiveDispatcher):
    def _Primitive(self, prim):
        return self._prim_object(prim)

    def MinWidth(self, prim):
        return self._prim_object(prim, add_name=False)

    def Spacing(self, prim):
        return self._prim_object(prim, add_name=False)

    def _prim_object(self, prim, add_name=True):
        class_name = prim.__class__.__name__.split(".")[-1]
        if add_name:
            s_name = f"name='{prim.name}'" if add_name else ""
        else:
            s_name = ""
        s_param = getattr(self, "_params_"+class_name, self._params_unhandled)(prim)
        if s_param:
            s_param = indent(s_param, prefix="    ")
            if s_name:
                s_name += ","
            return f"prims += {class_name}({s_name}\n{s_param})\n"
        else:
            return f"prims += {class_name}({s_name})\n"

    def _params_unhandled(self, prim): # pragma: no cover
        raise RuntimeError(f"Internal error: unhandled params for {prim.__class__.__name__}")

    def _params_designmask(self, prim: _prm.DesignMaskPrimitiveT):
        s = ""
        if prim.grid is not None:
            s += f"grid={prim.grid},"
        try:
            blockage: _prm.Marker = prim.blockage # type: ignore
        except AttributeError:
            pass
        else:
            if s:
                s += " "
            s += f"blockage={_str_prim(blockage)},"
        s += "\n"

        return s

    def _params_widthspace(self, prim: _prm.WidthSpacePrimitiveT):
        s = f"min_width={prim.min_width}, min_space={prim.min_space},\n"
        if prim.space_table is not None:
            s += "space_table=(\n"
            for row in prim.space_table:
                s += f"    {row},\n"
            s += "),\n"
        s += f"min_area={prim.min_area},\n"
        if prim.min_density is not None:
            s += f"min_density={prim.min_density},\n"
        if prim.max_density is not None:
            s += f"max_density={prim.max_density},\n"
        try:
            pin: _prm.Marker = prim.pin # type: ignore
        except AttributeError:
            pass
        else:
            s += f"pin={_str_prim(pin)},\n"

        return s

    def _params_widthspacedesignmask(self, prim: _prm.WidthSpaceDesignMaskPrimitiveT):
        return self._params_widthspace(prim) + self._params_designmask(prim)

    def _params_Base(self, prim: _prm.Base):
        lookup = {
            _prm.nBase: "nBase",
            _prm.pBase: "pBase",
            _prm.undopedBase: "undopedBase",
        }
        return f"type_={lookup[prim.type_]}"

    def _params_Marker(self, prim: _prm.Marker):
        return self._params_designmask(prim)

    def _params_SubstrateMarker(self, prim: _prm.SubstrateMarker):
        return self._params_Marker(prim)

    def _params_Auxiliary(self, prim: _prm.Auxiliary):
        return self._params_designmask(prim)

    def _params_ExtraProcess(self, prim: _prm.ExtraProcess):
        return self._params_widthspacedesignmask(prim)

    def _params_Implant(self, prim: _prm.Implant):
        s = f"type_='{prim.type_.value}',\n"
        s += self._params_widthspacedesignmask(prim)
        return s

    def _params_Well(self, prim: _prm.Well):
        if prim.min_space_samenet is not None:
            s = f"min_space_samenet={prim.min_space_samenet},\n"
        else:
            s = ""
        s += self._params_Implant(prim)
        return s

    def _params_DeepWell(self, prim: _prm.DeepWell):
        return (
            f"well={_str_prim(prim.well)},\n"
            f"min_well_overlap={prim.min_well_overlap},\n"
            f"min_well_enclosure={prim.min_well_enclosure},\n"
        ) + self._params_Implant(prim)

    def _params_Insulator(self, prim: _prm.Insulator):
        return self._params_widthspacedesignmask(prim)

    def _params_GateWire(self, prim: _prm.GateWire):
        return self._params_widthspacedesignmask(prim)

    def _params_MetalWire(self, prim: _prm.MetalWire):
        return self._params_widthspacedesignmask(prim)

    def _params_MIMTop(self, prim: _prm.MIMTop):
        return self._params_MetalWire(prim)

    def _params_TopMetalWire(self, prim: _prm.TopMetalWire):
        return self._params_MetalWire(prim)

    def _params_WaferWire(self, prim: _prm.WaferWire):
        s = f"allow_in_substrate={prim.allow_in_substrate},\n"
        s += f"implant={_str_primtuple(prim.implant)},\n"
        s += f"min_implant_enclosure={_str_enclosures(prim.min_implant_enclosure)},\n"
        s += f"implant_abut={_str_primtuple(prim.implant_abut)},\n"
        s += f"allow_contactless_implant={prim.allow_contactless_implant},\n"
        s += f"well={_str_primtuple(prim.well)},\n"
        s += "min_well_enclosure="+_str_enclosures(prim.min_well_enclosure)+",\n"
        if prim.min_substrate_enclosure is not None:
            s += (
                "min_substrate_enclosure="
                f"{_str_enclosure(prim.min_substrate_enclosure)},\n"
            )
        s += f"allow_well_crossing={prim.allow_well_crossing},\n"
        if prim.oxide:
            assert prim.min_oxide_enclosure is not None
            s += (
                f"oxide={_str_primtuple(prim.oxide)},\n"
                f"min_oxide_enclosure={_str_enclosures(prim.min_oxide_enclosure)},\n"
            )
        s += self._params_widthspacedesignmask(prim)
        return s

    def _params_Resistor(self, prim: _prm.Resistor):
        s = f"wire={_str_prim(prim.wire)}, indicator={_str_primtuple(prim.indicator)},\n"
        s += f"min_indicator_extension={prim.min_indicator_extension},\n"
        s += f"min_width={prim.min_width},\n"
        s += f"min_length={prim.min_length},\n"
        s += f"min_space={prim.min_space},\n"
        if prim.contact is not None:
            assert prim.min_contact_space is not None
            s += (
                f"contact={_str_prim(prim.contact)},"
                f" min_contact_space={prim.min_contact_space},\n"
            )
        if prim.implant is not None:
            s += (
                f"implant={_str_primtuple(prim.implant)}, "
                f", min_implant_enclosure={_str_enclosures(prim.min_implant_enclosure)},\n"
            )
        return s

    def _params_MIMCapacitor(self, prim: _prm.MIMCapacitor):
        return (
            f"bottom={_str_prim(prim.bottom)},\n"
            f"top={_str_prim(prim.top)},\n"
            f"via={_str_prim(prim.via)},\n"
            f"min_width={prim.min_width},\n"
            f"min_bottom_top_enclosure={_str_enclosure(prim.min_bottom_top_enclosure)},\n"
            f"min_bottomvia_space={prim.min_bottomvia_top_space},\n"
            f"min_top_via_enclosure={_str_enclosure(prim.min_top_via_enclosure)},\n"
            f"min_bottom_space={prim.min_bottom_space},\n"
            f"min_top2bottom_space={prim.min_top2bottom_space},\n"
        )

    def _params_Diode(self, prim: _prm.Diode):
        s = f"wire={_str_prim(prim.wire)}, indicator={_str_primtuple(prim.indicator)},\n"
        s += f"min_width={prim.min_width},\n"
        s += f"min_indicator_enclosure={_str_enclosures(prim.min_indicator_enclosure)},\n"
        s += f"implant={_str_primtuple(prim.implant)}"
        if prim.min_implant_enclosure is not None:
            s += f", min_implant_enclosure={_str_enclosures(prim.min_implant_enclosure)}"
        s += ",\n"
        if prim.well is not None:
            s += f"well={_str_prim(prim.well)}"
            if prim.min_well_enclosure is not None:
                s += f", min_well_enclosure={_str_enclosure(prim.min_well_enclosure)}"
            s += ",\n"
        return s

    def _params_Via(self, prim: _prm.Via):
        s = f"bottom={_str_primtuple(prim.bottom)},\n"
        s += f"top={_str_primtuple(prim.top)},\n"
        s += f"width={prim.width}, min_space={prim.min_space},\n"
        s += f"min_bottom_enclosure={_str_enclosures(prim.min_bottom_enclosure)},\n"
        s += f"min_top_enclosure={_str_enclosures(prim.min_top_enclosure)},\n"
        s += self._params_designmask(prim)
        return s

    def _params_PadOpening(self, prim: _prm.PadOpening):
        s = f"bottom={_str_prim(prim.bottom)},\n"
        s += f"min_bottom_enclosure={_str_enclosure(prim.min_bottom_enclosure)},\n"
        s += self._params_widthspacedesignmask(prim)
        return s

    def _params_MinWidth(self, prim: _prm.MinWidth):
        s = f"prim={_str_prim(prim.prim)},\n"
        s += f"min_width={prim.min_width},\n"
        return s

    def _params_Spacing(self, prim: _prm.Spacing):
        s = f"primitives1={_str_primtuple(prim.primitives1)},\n"
        if prim.primitives2 is not None:
            s += f"primitives2={_str_primtuple(prim.primitives2)},\n"
        s += f"min_space={prim.min_space},\n"
        return s

    def _params_Enclosure(self, prim: _prm.Enclosure):
        return dedent(f"""
            prim={_str_prim(prim.prim)}, by={_str_prim(prim.by)},
            min_enclosure={_str_enclosure(prim.min_enclosure)},
        """[1:])

    def _params_NoOverlap(self, prim: _prm.NoOverlap):
        return f"prim1={_str_prim(prim.prim1)}, prim2={_str_prim(prim.prim2)},\n"

    def _params_MOSFETGate(self, prim: _prm.MOSFETGate):
        s = f"active={_str_prim(prim.active)}, poly={_str_prim(prim.poly)},\n"
        if prim.oxide is not None:
            s += f"oxide={_str_prim(prim.oxide)},\n"
        if prim.min_gateoxide_enclosure is not None:
            s += (
                "min_gateoxide_enclosure="
                f"{_str_enclosure(prim.min_gateoxide_enclosure)},\n"
            )
        if prim.inside is not None:
            s += f"inside={_str_primtuple(prim.inside)},\n"
        if prim.min_gateinside_enclosure is not None:
            s += (
                "min_gateinside_enclosure="
                f"{_str_enclosures(prim.min_gateinside_enclosure)},\n"
            )
        if prim.min_l is not None:
            s += f"min_l={prim.min_l},\n"
        if prim.min_w is not None:
            s += f"min_w={prim.min_w},\n"
        if prim.min_sd_width is not None:
            s += f"min_sd_width={prim.min_sd_width},\n"
        if prim.min_polyactive_extension is not None:
            s += f"min_polyactive_extension={prim.min_polyactive_extension},\n"
        if prim.min_gate_space is not None:
            s += f"min_gate_space={prim.min_gate_space},\n"
        if prim.contact is not None:
            s += f"contact={_str_prim(prim.contact)}, min_contactgate_space={prim.min_contactgate_space},\n"
        return s

    def _params_MOSFET(self, prim: _prm.MOSFET):
        s = f"gate={_str_prim(prim.gate)},\n"
        if prim.implant is not None:
            s += f"implant={_str_primtuple(prim.implant)},\n"
        if prim.well is not None:
            s += f"well={_str_prim(prim.well)},\n"
        if prim.min_l is not None:
            s += f"min_l={prim.min_l},\n"
        if prim.min_w is not None:
            s += f"min_w={prim.min_w},\n"
        if prim.min_sd_width is not None:
            s += f"min_sd_width={prim.min_sd_width},\n"
        if prim.min_polyactive_extension is not None:
            s += f"min_polyactive_extension={prim.min_polyactive_extension},\n"
        s += (
            "min_gateimplant_enclosure="
            f"{_str_enclosures(prim.min_gateimplant_enclosure)},\n"
        )
        if prim.min_gate_space is not None:
            s += f"min_gate_space={prim.min_gate_space},\n"
        if prim.contact is not None:
            s += f"contact={_str_prim(prim.contact)}, min_contactgate_space={prim.min_contactgate_space},\n"
        return s

    def _params_Bipolar(self, prim: _prm.Bipolar):
        s = f""


class PDKMasterGenerator:
    def __call__(self, obj):
        if isinstance(obj, _tch.Technology):
            return self._gen_tech(obj)
        elif isinstance(obj, _ckt._Circuit):
            return self._gen_ckt(obj)
        elif isinstance(obj, _lbry.Library):
            return self._gen_lib(obj)
        else:
            raise TypeError("obj has to be of type 'Technology' or '_Circuit'")

    def _gen_header(self, tech: _tch.Technology):
        s = "# Autogenerated file. Changes will be overwritten.\n\n"

        class_name = tech.__class__.__name__
        s += (
            f"from {tech.__class__.__module__} import {class_name}\n"
            f"tech = {class_name}()\n"
        )

        s += "\n"

        return s

    def _gen_tech(self, tech):
        s = dedent(f"""
            # Autogenerated file. Changes will be overwritten.

            from pdkmaster.technology.primitive import *
            from pdkmaster.technology.property_ import Enclosure
            from pdkmaster.technology.technology_ import Technology
            from pdkmaster.design.layout import LayoutFactory
            from pdkmaster.design.circuit import CircuitFactory

            __all__ = [
                "technology", "tech",
                "layoutfab", "layout_factory",
                "cktfab", "circuit_factory",
            ]

            class {tech.name}(Technology):
                name = "{tech.name}"
                grid = {tech.grid}

                def _init(self):
                    prims = self._primitives

        """[1:])
        gen = _PrimitiveGenerator()
        s += indent(
            "".join(gen(prim) for prim in tech.primitives),
            prefix="        "
        )
        s += dedent(f"""

            technology = tech = {tech.name}()
            cktfab = circuit_factory = CircuitFactory(tech)
            layoutfab = layout_factory = LayoutFactory(tech)
        """[1:])

        return s

    def _gen_ckt(self, circuit, *, lib=None, header=True):
        s = ""
        if header:
            s += self._gen_header(circuit.fab.tech)

            s += dedent(f"""
                __all__ = ["circuit", "ckt"]

                circuit = ckt = cktfab.new_circuit("{circuit.name}")

            """)

        for net in circuit.nets:
            external = net in circuit.ports
            s += f"ckt.new_net('{net.name}', external={external})\n"
        s += "\n"

        for inst in circuit.instances:
            if isinstance(inst, _ckt._PrimitiveInstance):
                primname = inst.prim.name
                s += f"ckt.instantiate(tech.primitives['{primname}'], name='{inst.name}',\n"
                for param in inst.prim.params:
                    s += f"    {param.name}={inst.params[param.name]!r},\n"
                s += ")\n"
            elif isinstance(inst, _ckt._CellInstance):
                if lib is None:
                    raise ValueError(
                        "Can't export single Circuit with Cell instances outside library export"
                    )
                elif inst.cell not in lib.cells:
                    raise ValueError(
                        "Can't export Circuit with inter-library cell instance(s)"
                    )

                cellname = inst.cell.name
                s += (
                    f"ckt.instantiate(self.cells['{cellname}'].circuit"
                    f", name='{inst.name}'"
                    f", circuitname={inst.circuitname}"
                )
                s += ")\n"
            else: # pragma: no cover
                raise AssertionError("Internal error: unsupported instance class")

        s += "\n"

        for net in circuit.nets:
            if len(net.childports) > 0:
                s += f"ckt.nets['{net.name}'].childports += (\n"
                for port in net.childports:
                    inst = port.inst
                    s += (
                        f"    ckt.instances['{inst.name}'].ports['{port.name}'],\n"
                    )
                s += ")\n"

        return s

    def _gen_lib(self, library, header=True):
        s = ""
        if header:
            s += dedent("""
                # Autogenerated file. Changes will be overwritten.

                from pdkmaster.design.library import Library
                from pdkmaster.technology.property_ import Enclosure

            """[1:])

            s += self._gen_header(library.tech)

            s += dedent("""
                __all__ = ["library", "lib"]

                library = lib = Library(tech, cktfab, layoutfab)
            """)

        for cell in library.sorted_cells:
            s += dedent(f"""

                # cell: {cell.name}
                cell = lib.new_cell(name='{cell.name}')
            """)
            for circuit in cell._circuits:
                s += f"ckt = cell.new_circuit('{circuit.name}')\n"
                s += self._gen_ckt(circuit, lib=library, header=False)

        # if cell.layouts:
        #     raise NotImplementedError("Library cells export with layout")

        return s


generate = PDKMasterGenerator()
