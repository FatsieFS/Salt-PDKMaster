"""Generate coriolis setup file"""
# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from textwrap import dedent, indent
from itertools import product
from typing import Set, Tuple, Iterable, Optional, Callable, cast, overload

from ... import dispatch as _dsp
from ...typing  import GDSLayerSpecDict
from ...technology import (
    mask as _msk, net as _net, primitive as _prm, geometry as _geo, technology_ as _tch,
)
from ...design import cell as _cell, routinggauge as _rg, library as _lbry
from ...design.layout import layout_ as _laylay

__all__ = ["CoriolisExportSpec", "FileExporter"]


class CoriolisExportSpec:
    """This class allows to specify

    API Notes:
        * No backwards guarantees are given for this class yet. Future changes
          may break user code.
    """
    def __init__(self, *,
        globalnets: Iterable[str]=(),
        net_direction_cb: Optional[Callable[[str], str]]=None,
    ) -> None:
        self._globalnets = tuple(globalnets)
        self._net_direction_cb = net_direction_cb

    @property
    def globalnets(self) -> Tuple[str]:
        return self._globalnets
    @property
    def net_direction_cb(self) -> Optional[Callable[[str], str]]:
        return self._net_direction_cb


def _str_create_basic(name, mat, *,
    minsize=None, minspace=None, minarea=None, gds_layer=None, gds_datatype=None
):
    s = "createBL(\n"
    s += f"    tech, '{name}', BasicLayer.Material.{mat},\n"
    s_args = []
    if minsize is not None:
        s_args.append(f"size=u({minsize})")
    if minspace is not None:
        s_args.append(f"spacing=u({minspace})")
    if minarea is not None:
        s_args.append(f"area={minarea}")
    if gds_layer is not None:
        s_args.append(f"gds2Layer={gds_layer}")
    if gds_datatype is not None:
        s_args.append(f"gds2DataType={gds_datatype}")
    if s_args:
        s += "    " + ", ".join(s_args) + ",\n"
    s += ")\n"
    return s


def _str_create_via(via):
    assert isinstance(via, _prm.Via)

    def _str_bottomtop(bottom, top):
        s_via = f"{bottom.name}_{via.name}_{top.name}"
        return dedent(f"""
            # {bottom.name}<>{via.name}<>{top.name}
            createVia(
                tech, '{s_via}', '{bottom.name}', '{via.name}', '{top.name}',
                u({via.width}),
            )
        """[1:])

    return "".join(_str_bottomtop(bottom, top) for bottom, top in product(
        filter(lambda p: isinstance(p, _prm.MetalWire), via.bottom),
        filter(lambda p: isinstance(p, _prm.MetalWire), via.top),
    ))


def _args_gds_layer(prim: _prm.MaskPrimitiveT, *, gds_layers: GDSLayerSpecDict):
    mask = prim.mask
    if isinstance(mask, _msk.DesignMask):
        gds_layer = gds_layers.get(mask.name, None)
        if gds_layer is not None:
            if not isinstance(gds_layer, tuple):
                gds_layer = (gds_layer, 0)
            return {"gds_layer": gds_layer[0], "gds_datatype": gds_layer[1]}
        else:
            return {}
    else:
        return {}


class _LayerGenerator(_dsp.PrimitiveDispatcher):
    def __init__(self, *, tech: _tch.Technology, gds_layers: GDSLayerSpecDict):
        self.gds_layers = gds_layers
        # TODO: get the poly layers
        self.poly_layers = {
            gate.poly for gate in tech.primitives.__iter_type__(_prm.MOSFETGate)
        }
        self.via_conns = via_conns = cast(Set[_prm.PrimitiveT], set())
        for via in tech.primitives.__iter_type__(_prm.Via):
            via_conns.update(via.bottom)
            via_conns.update(via.top)
        self.blockages = {
            cast(_prm.BlockageAttrPrimitiveT, prim).blockage
            for prim in filter(lambda p: hasattr(p, "blockage"), tech.primitives)
        }

    def _Primitive(self, prim: _prm.PrimitiveT):
        raise NotImplementedError(
            f"layer code generation for '{prim.__class__.__name__}'"
        )

    def Marker(self, prim: _prm.Marker):
        type_ = "blockage" if prim in self.blockages else "other"
        return _str_create_basic(prim.name, type_, **_args_gds_layer(
            prim, gds_layers=self.gds_layers,
        ))

    def Auxiliary(self, prim):
        return _str_create_basic(prim.name, "other", **_args_gds_layer(
            prim, gds_layers=self.gds_layers,
        ))

    def ExtraProcess(self, prim: _prm.ExtraProcess):
        return _str_create_basic(prim.name, "other", **_args_gds_layer(
            prim, gds_layers=self.gds_layers,
        ))

    def Implant(self, prim: _prm.Implant):
        return _str_create_basic(
            prim.name,
            (
                f"{prim.type_.value}Implant"
                if prim.type_ in (_prm.nImpl, _prm.pImpl)
                else "other"
            ),
            minsize=prim.min_width, minspace=prim.min_space,
            minarea=prim.min_area,
            **_args_gds_layer(prim, gds_layers=self.gds_layers),
        )

    def Insulator(self, prim: _prm.Insulator):
        return _str_create_basic(prim.name, "other", **_args_gds_layer(
            prim, gds_layers=self.gds_layers,
        ))

    def Well(self, prim: _prm.Well):
        return _str_create_basic(
            prim.name, prim.type_.value+"Well",
            minsize=prim.min_width, minspace=prim.min_space,
            minarea=prim.min_area,
            **_args_gds_layer(prim, gds_layers=self.gds_layers),
        )

    def DeepWell(self, prim: _prm.DeepWell):
        # Treat it as a regular well
        return _str_create_basic(
            prim.name, prim.type_.value+"Well",
            minsize=prim.min_width, minspace=prim.min_space,
            minarea=prim.min_area,
            **_args_gds_layer(prim, gds_layers=self.gds_layers),
        )

    def WaferWire(self, prim: _prm.WaferWire):
        return _str_create_basic(
            prim.name, "active",
            minsize=prim.min_width, minspace=prim.min_space,
            minarea=prim.min_area,
            **_args_gds_layer(prim, gds_layers=self.gds_layers),
        )

    def GateWire(self, prim: _prm.GateWire):
        return _str_create_basic(
            prim.name, "poly",
            minsize=prim.min_width, minspace=prim.min_space,
            minarea=prim.min_area,
            **_args_gds_layer(prim, gds_layers=self.gds_layers),
        )

    def MetalWire(self, prim: _prm.MetalWire):
        return _str_create_basic(
            prim.name, "metal",
            minsize=prim.min_width, minspace=prim.min_space,
            minarea=prim.min_area,
            **_args_gds_layer(prim, gds_layers=self.gds_layers),
        )

    def Via(self, prim: _prm.Via, *, via_layer: bool=False):
        if via_layer:
            return _str_create_via(prim)
        else:
            return _str_create_basic(
                prim.name, "cut",
                minsize=prim.width, minspace=prim.min_space,
                **_args_gds_layer(prim, gds_layers=self.gds_layers),
            )

    def PadOpening(self, prim: _prm.PadOpening):
        return _str_create_basic(
            prim.name, "cut",
            minsize=prim.min_width, minspace=prim.min_space,
            minarea=prim.min_area,
            **_args_gds_layer(prim, gds_layers=self.gds_layers),
        )

    def Resistor(self, prim: _prm.Resistor):
        if len(prim.indicator) == 1:
            s_indicator = f"'{prim.indicator[0].name}'"
        else:
            s_indicator = str(tuple(ind.name for ind in prim.indicator))
        return (
            f"# ResistorLayer.create(tech, '{prim.name}', '{prim.wire.name}', "
            f"{s_indicator})\n"
        )

    def MIMCapacitor(self, prim: _prm.MIMCapacitor):
        return f"# MIMCAP '{prim.name}': '{prim.top}' over '{prim.bottom}'"

    def Diode(self, prim: _prm.Diode):
        if len(prim.indicator) == 1:
            s_indicator = f"'{prim.indicator[0].name}'"
        else:
            s_indicator = str(tuple(ind.name for ind in prim.indicator))
        return (
            f"# DiodeLayer.create(tech, '{prim.name}', '{prim.wire.name}', "
            f"{s_indicator})\n"
        )

    def MOSFETGate(self, prim: _prm.MOSFETGate):
        s_oxide = f", '{prim.oxide.name}'" if prim.oxide is not None else ""
        return (
            f"# GateLayer.create(tech, '{prim.name}', '{prim.active.name}', "
            f"'{prim.poly.name}'{s_oxide})\n"
        )

    def MOSFET(self, prim: _prm.MOSFET):
        impl_names = tuple(impl.name for impl in prim.implant)
        s_impl = f"'{impl_names[0]}'" if len(impl_names) == 1 else str(impl_names)
        s_well = f", '{prim.well.name}'" if prim.well is not None else ""
        return (
            f"# TransistorLayer.create(tech, '{prim.name}', '{prim.gate.name}', "
            f"{s_impl}{s_well})\n"
        )

    def Bipolar(self, prim: _prm.Bipolar):
        return f"# Not implemented: Bipolar '{prim.name}'"


class _AnalogGenerator(_dsp.PrimitiveDispatcher):
    def __init__(self, tech):
        self.tech = tech

    def _Primitive(self, prim: _prm.PrimitiveT):
        raise NotImplementedError(
            f"analog code generation for '{prim.__class__.__name__}'"
        )

    def _DesignMaskPrimitive(self, prim: _prm.DesignMaskPrimitiveT):
        s = ""
        if prim.grid is not None:
            s += f"('grid', '{prim.name}', {prim.grid}, Length, ''),\n"
        return s

    def _WidthSpacePrimitive(self, prim: _prm.WidthSpacePrimitiveT):
        s = f"('minWidth', '{prim.name}', {prim.min_width}, Length, ''),\n"
        s += f"('minSpacing', '{prim.name}', {prim.min_space}, Length, ''),\n"
        if isinstance(prim, _prm.DesignMaskPrimitiveT):
            s += self._DesignMaskPrimitive(prim)
        if prim.min_area is not None:
            s += f"('minArea', '{prim.name}', {prim.min_area}, Area, ''),\n"
        if prim.min_density is not None:
            s += f"('minDensity', '{prim.name}', {prim.min_density}, Unit, ''),\n"
        if prim.max_density is not None:
            s += f"('maxDensity', '{prim.name}', {prim.max_density}, Unit, ''),\n"
        return s

    # primitives handled by base classes of hierarchy:
    # Marker, Auxiliary, ExtraProcess, Implant, Insulator, GateWire, (Top)MetalWire

    def Base(self, prim: _prm.Base):
        return ""

    def Well(self, prim: _prm.Well):
        s = self._WidthSpacePrimitive(prim)
        if prim.min_space_samenet is not None:
            s += f"('minSpacingSameNet', '{prim.name}', {prim.min_space_samenet}, Length, ''),\n"
        return s

    def WaferWire(self, prim: _prm.WaferWire):
        s = self._WidthSpacePrimitive(prim)
        for i in range(len(prim.well)):
            well = prim.well[i]
            enc = prim.min_well_enclosure[i].spec
            s += (
                f"('minEnclosure', '{well.name}', '{prim.name}', {enc},"
                " Length|Asymmetric, ''),\n"
            )
        if prim.min_substrate_enclosure is not None:
            for well in self.tech.primitives.__iter_type__(_prm.Well):
                s += (
                    f"('minSpacing', '{well.name}', '{prim.name}', "
                    f" {prim.min_substrate_enclosure.spec}, Length|Asymmetric, ''),\n"
                )
        s += (
            f"# TODO for {prim.name}:\n"
            "#    allow_in_substrate, implant_abut, allow_contactless_implant, allow_well_crossing\n"
        )
        return s

    def Via(self, prim: _prm.Via):
        s = self._DesignMaskPrimitive(prim)
        s += f"('minWidth', '{prim.name}', {prim.width}, Length, ''),\n"
        s += f"('maxWidth', '{prim.name}', {prim.width}, Length, ''),\n"
        s += f"('minSpacing', '{prim.name}', {prim.min_space}, Length, ''),\n"
        for i in range(len(prim.bottom)):
            bottom = prim.bottom[i]
            enc = prim.min_bottom_enclosure[i].spec
            s += (
                f"('minEnclosure', '{bottom.name}', '{prim.name}', {enc}, "
                "Length|Asymmetric, ''),\n"
            )
        for i in range(len(prim.top)):
            top = prim.top[i]
            enc = prim.min_top_enclosure[i].spec
            s += (
                f"('minEnclosure', '{top.name}', '{prim.name}', {enc}, "
                "Length|Asymmetric, ''),\n"
            )
        return s

    def PadOpening(self, prim: _prm.PadOpening):
        s = self._WidthSpacePrimitive(prim)
        s += (
            f"('minEnclosure', '{prim.bottom.name}', '{prim.name}', "
            f"{prim.min_bottom_enclosure.spec}, Length|Asymmetric, ''),\n"
        )
        return s

    def Resistor(self, prim: _prm.Resistor):
        s = f"('minWidth', '{prim.name}', {prim.min_width}, Length, ''),\n"
        s += f"('minSpacing', '{prim.name}', {prim.min_space}, Length, ''),\n"
        for i in range(len(prim.indicator)):
            ind = prim.indicator[i]
            enc = prim.min_indicator_extension[i]
            s += (
                f"('minEnclosure', '{ind.name}', '{prim.wire.name}', {enc}, "
                "Length|Asymmetric, ''),\n"
            )
        s = indent(s, prefix="# ")
        return s

    def MIMCapacitor(self, prim: _prm.Diode):
        s = f"# ('minWidth', '{prim.name}', {prim.min_width}, Length, ''),\n"
        s += "# TODO: MIMCapacitor rules\n"

        return s

    def Diode(self, prim: _prm.Diode):
        s = f"('minWidth', '{prim.name}', {prim.min_width}, Length, ''),\n"
        for i in range(len(prim.indicator)):
            ind = prim.indicator[i]
            enc = prim.min_indicator_enclosure[i]
            s += (
                f"('minEnclosure', '{ind.name}', '{prim.wire.name}', {enc.spec}, "
                "Length|Asymmetric, ''),\n"
            )
        s = indent(s, prefix="# ")
        return s

    def MOSFETGate(self, prim: _prm.MOSFETGate):
        s = ""
        if prim.min_l is not None:
            s += f"# ('minTransistorL', '{prim.name}', {prim.min_l}, Length, ''),\n"
        if prim.min_w is not None:
            s += f"# ('minTransistorW', '{prim.name}', {prim.min_w}, Length, ''),\n"
        if prim.min_sd_width is not None:
            s += (
                f"# ('minGateExtension', '{prim.active.name}', '{prim.name}', "
                f"{prim.min_sd_width}, Length|Asymmetric, ''),\n"
            )
        if prim.min_polyactive_extension is not None:
            s += (
                f"# ('minGateExtension', '{prim.poly.name}', '{prim.name}', "
                f"{prim.min_polyactive_extension}, Length|Asymmetric, ''),\n"
            )
        if prim.min_gate_space is not None:
            s += (
                f"# ('minGateSpacing', '{prim.name}', {prim.min_gate_space}, "
                "Length, ''),\n"
            )
        if prim.contact is not None:
            s += (
                f"# ('minGateSpacing', '{prim.contact.name}', '{prim.name}', "
                f"{prim.min_contactgate_space}, Length|Asymmetric, ''),\n"
            )
        return s

    def MOSFET(self, prim: _prm.MOSFET):
        s = ""
        if prim.min_l is not None:
            s += f"# ('minTransistorL', '{prim.name}', {prim.min_l}, Length, ''),\n"
        if prim.min_w is not None:
            s += f"# ('minTransistorW', '{prim.name}', {prim.min_w}, Length, ''),\n"
        if prim.min_sd_width is not None:
            s += (
                f"# ('minGateExtension', '{prim.gate.active.name}', '{prim.name}', "
                f"{prim.min_sd_width}, Length|Asymmetric, ''),\n"
            )
        if prim.min_polyactive_extension is not None:
            s += (
                f"# ('minGateExtension', '{prim.gate.poly.name}', '{prim.name}', "
                f"{prim.min_polyactive_extension}, Length|Asymmetric, ''),\n"
            )
        for i in range(len(prim.implant)):
            impl = prim.implant[i]
            enc = prim.min_gateimplant_enclosure[i].spec
            s += (
                f"# ('minGateEnclosure', '{impl.name}', '{prim.name}', {enc}, "
                "Length|Asymmetric, ''),\n"
            )
        if prim.min_gate_space is not None:
            s += (
                f"# ('minGateSpacing', '{prim.name}', {prim.min_gate_space}, "
                "Length, ''),\n"
            )
        if prim.contact is not None:
            s += (
                f"# ('minGateSpacing', '{prim.contact.name}', '{prim.name}', "
                f"{prim.min_gate_space}, Length, ''),\n"
            )
        return s

    def Bipolar(self, prim: _prm.Bipolar):
        return f"# Not implemented: Bipolar '{prim.name}'\n"

    def MinWidth(self, prim: _prm.MinWidth):
        return f"# ('minWidth', '{prim.prim.name}', '{prim.min_width}', Length, ''),\n"

    def Spacing(self, prim: _prm.Spacing):
        from ...technology.primitive._derived import _DerivedPrimitive
        def comment_string(*, prim1: _prm.PrimitiveT, prim2: Optional[_prm.PrimitiveT]):
            if isinstance(prim1, _DerivedPrimitive) or isinstance(prim2, _DerivedPrimitive):
                return "# "
            else:
                return ""
        if prim.primitives2 is None:
            return "".join(
                f"{comment_string(prim1=prim1, prim2=None)}"
                f"('minSpacing', '{prim1.name}', {prim.min_space}, Length, ''),\n"
                for prim1 in prim.primitives1
            )
        else:
            return "".join(
                f"{comment_string(prim1=prim1, prim2=prim2)}"
                f"('minSpacing', '{prim1.name}', '{prim2.name}', {prim.min_space}, "
                "Length|Asymmetric, ''),\n"
                for prim1, prim2 in product(prim.primitives1, prim.primitives2)
            )

    def Enclosure(self, prim: _prm.Enclosure):
        return (
            f"('minEnclosure', '{prim.by.name}', '{prim.prim.name}', {prim.min_enclosure.spec}, "
            "Length|Asymmetric, ''),\n"
        )

    def NoOverlap(self, prim: _prm.NoOverlap):
        return f"# ('noOverlap', '{prim.prim1.name}', '{prim.prim2.name}'),\n"


class _LibraryGenerator:
    def __init__(self, *, tech: _tch.Technology, spec: Optional[CoriolisExportSpec]):
        self.tech = tech
        self.spec = spec
        self.metals: Tuple[_prm.MetalWire, ...] = tuple(filter(
            lambda m: not isinstance(m, _prm.MIMTop),
            tech.primitives.__iter_type__(_prm.MetalWire),
        ))
        self.vias: Tuple[_prm.Via, ...] = tuple(tech.primitives.__iter_type__(_prm.Via))
        assert len(self.metals) == len(self.vias)
        self.pinmasks = pinmasks = {}
        for prim in tech.primitives:
            if hasattr(prim, "pin"):
                assert isinstance(prim, _prm.DesignMaskPrimitiveT)
                pinmasks[cast(_prm.PinAttrPrimitiveT, prim).pin.mask] = prim.mask

        self.metalsdir: Optional[Tuple[Optional[str], ...]] = None

    def __call__(self, lib: _lbry.Library, *, routinggauge: Optional[_rg.RoutingGauge]):
        def otherdir(dir_):
            return "vertical" if dir_ == "horizontal" else "horizontal"

        if isinstance(lib, _lbry.RoutingGaugeLibrary):
            assert routinggauge is None
            routinggauge = next(iter(lib._routinggauge))

        if routinggauge is not None:
            bottom_idx = self.metals.index(routinggauge.bottom)
            bottom_dir = routinggauge.bottom_direction
            self.metalsdir = tuple(
                None if i < (bottom_idx - 1)
                else bottom_dir if ((i - bottom_idx)%2) == 0
                else otherdir(bottom_dir) # This is also for bottom_idx - 1
                for i in range(len(self.metals))
            )


        s = "\n".join((
            self._s_head(), self._s_routing(lib), self._s_load(lib),
            self._s_setup(lib),
        ))

        self.metalsdir = None

        return s

    def _s_head(self):
        return dedent(f"""
            # Autogenerated file. Changes will be overwritten.

            try:
                import coriolis
            except ImportError:
                import CRL, Hurricane, Viewer, Cfg
                from Hurricane import (
                    Technology, DataBase, DbU, Library,
                    Layer, BasicLayer,
                    Cell, Net, Horizontal, Vertical, Rectilinear, Box, Point,
                    Instance, Transformation,
                    NetExternalComponents,
                )
                from helpers import u, l
                from helpers.technology import setEnclosures
                from helpers.overlay import CfgCache, UpdateSession
            else:
                from coriolis import CRL, Hurricane, Viewer, Cfg
                from coriolis.Hurricane import (
                    Technology, DataBase, DbU, Library,
                    Layer, BasicLayer,
                    Cell, Net, Horizontal, Vertical, Rectilinear, Box, Point,
                    Instance, Transformation,
                    NetExternalComponents,
                )
                from coriolis.helpers import u, l
                from coriolis.helpers.technology import setEnclosures
                from coriolis.helpers.overlay import CfgCache, UpdateSession

            __all__ = ["setup"]

            def createRL(tech, net, layer, coords):
                coords = [Point(u(x), u(y)) for x,y in coords]
                Rectilinear.create(net, tech.getLayer(layer), coords)
        """[1:])

    def _s_setup(self, lib):
        return dedent(f"""
            def setup():
                lib = _load()
                _routing()
                try:
                    from .{lib.name}_fix import fix
                except:
                    pass
                else:
                    fix(lib)

                return lib
        """[1:])

    def _s_routing(self, lib):
        s = dedent(f"""
            def _routing():
                af = CRL.AllianceFramework.get()
                db = DataBase.getDB()
                tech = db.getTechnology()

        """[1:])

        if isinstance(lib, _lbry.RoutingGaugeLibrary):
            s += indent(
                "\n".join(
                    (self._s_gauge(lib), self._s_pnr(lib), self._s_plugins())
                ),
                prefix="    ",
            )
        else:
            s += "    # No standard cell library\n    pass\n"

        return s

    def _s_gauge(self, lib):
        def s_cordir(dir_):
            return (
                "CRL.RoutingLayerGauge.Horizontal" if dir_ == "horizontal"
                else "CRL.RoutingLayerGauge.Vertical"
            )

        assert len(lib.routinggauge) == 1
        rg = lib.routinggauge[0]
        s = dedent(f"""
            rg = CRL.RoutingGauge.create('{lib.name}')
            rg.setSymbolic(False)
        """[1:])
        bottom_idx = self.metals.index(rg.bottom)
        top_idx = self.metals.index(rg.top)

        depth = 0
        mwidths = tuple(
            self.tech.computed.min_width(
                metal, up=True, down=True, min_enclosure=(i < bottom_idx),
            )
            for i, metal in enumerate(self.metals)
        )
        for i in range(max(bottom_idx - 1, 0), top_idx+1):
            assert self.metalsdir is not None
            routedir = self.metalsdir[i]
            assert routedir is not None
            s_usage = (
                "CRL.RoutingLayerGauge.PinOnly" if i < bottom_idx
                else "CRL.RoutingLayerGauge.Default"
            )

            metal = self.metals[i]
            mwidth = round(mwidths[i], 6)
            s += f"metal = tech.getLayer('{metal.name}')\n"
            mpwidth = round(
                self.tech.computed.min_width(
                    metal, up=False, down=True, min_enclosure=True
                ), 6,
            )
            if i >= bottom_idx:
                mpitch = round(
                    rg.pitches.get(
                        metal,
                        self.tech.computed.min_pitch(metal, up=True, down=True),
                    ),
                    6,
                )
                offset = rg.offsets.get(metal, 0.0)
            else:
                # For pin only layer take pitch/offset of two levels up
                altmetal = self.metals[i+2]
                mpitch = round(
                    rg.pitches.get(
                        altmetal,
                        self.tech.computed.min_pitch(altmetal, up=True, down=True),
                    ),
                    6,
                )
                offset = rg.offsets.get(altmetal, 0.0)
            s_pindir = s_cordir(routedir)
            dw = metal.min_space

            vwidth = None

            # Via below
            if i > 0:
                mwidth_below = mwidths[i - 1]
                via = self.vias[i]
                metal_idx = via.top.index(metal)
                enc = via.min_top_enclosure[metal_idx]
                metal2 = self.metals[i-1]
                via_name = f"{metal2.name}_{via.name}_{metal.name}"
                if routedir == "horizontal":
                    henc = max(enc.min(), 0.5*(mwidth_below - via.width))
                    venc = max(enc.max(), 0.5*(mwidth - via.width))
                else:
                    henc = max(enc.max(), 0.5*(mwidth - via.width))
                    venc = max(enc.min(), 0.5*(mwidth_below - via.width))
                s += dedent(f"""
                    via = tech.getLayer('{via_name}')
                    setEnclosures(via, metal, (u({henc:.6}), u({venc:.6})))
                """[1:])
                vwidth = via.width

            # Via above (only if it exists)
            if i < (len(self.vias) - 1):
                mwidth_above = mwidths[i + 1]
                via = self.vias[i + 1]
                metal_idx = via.bottom.index(metal)
                enc = via.min_bottom_enclosure[metal_idx]
                metal2 = self.metals[i+1]
                via_name = f"{metal.name}_{via.name}_{metal2.name}"
                if routedir == "horizontal":
                    henc = max(enc.max(), 0.5*(mwidth_above - via.width))
                    venc = max(enc.min(), 0.5*(mwidth - via.width))
                else:
                    henc = max(enc.min(), 0.5*(mwidth - via.width))
                    venc = max(enc.max(), 0.5*(mwidth_above - via.width))
                s += dedent(f"""
                    via = tech.getLayer('{via_name}')
                    setEnclosures(via, metal, (u({henc:.6}), u({venc:.6})))
                """[1:])
                vwidth = via.width

            assert vwidth is not None

            s += dedent(f"""
                rg.addLayerGauge(CRL.RoutingLayerGauge.create(
                    metal, {s_pindir}, {s_usage}, {depth}, 0.0,
                    u({offset:.6}), u({mpitch:.6}), u({mwidth:.6}), u({mpwidth:.6}), u({vwidth:.6}), u({dw:.6}),
                ))
            """[1:])

            depth += 1

        s += dedent(f"""
            af.addRoutingGauge(rg)
            af.setRoutingGauge('{lib.name}')

            cg = CRL.CellGauge.create(
                '{lib.name}', '{self.metals[1].name}',
                u({lib.pingrid_pitch}), u({lib.row_height}), u({lib.pingrid_pitch}),
            )
            af.addCellGauge(cg)
            af.setCellGauge('{lib.name}')
        """[1:])

        return s

    def _s_pnr(self, lib):
        topmetal = tuple(self.tech.primitives.__iter_type__(_prm.MetalWire))[-1]
        return dedent(f"""
            # Place & Route setup
            with CfgCache(priority=Cfg.Parameter.Priority.ConfigurationFile) as cfg:
                cfg.lefImport.minTerminalWidth = 0.0
                cfg.crlcore.groundName = 'vss'
                cfg.crlcore.powerName = 'vdd'
                cfg.etesian.aspectRatio = 1.00
                cfg.etesian.aspectRatio = [10, 1000]
                cfg.etesian.spaceMargin = 0.10
                cfg.etesian.uniformDensity = True
                cfg.etesian.routingDriven = False
                cfg.etesian.latchUpDistance = u(30.0 - 1.0)
                cfg.etesian.diodeName = 'diode_w1'
                cfg.etesian.antennaInsertThreshold = 0.50
                cfg.etesian.antennaMaxWL = u(250.0)
                cfg.etesian.feedNames = 'tie,decap_w0'
                cfg.etesian.cell.zero = 'zero_x1'
                cfg.etesian.cell.one = 'one_x1'
                cfg.etesian.bloat = 'disabled'
                cfg.etesian.effort = 2
                cfg.etesian.effort = (
                    ('Fast', 1),
                    ('Standard', 2),
                    ('High', 3 ),
                    ('Extreme', 4 ),
                )
                cfg.etesian.graphics = 2
                cfg.etesian.graphics = (
                    ('Show every step', 1),
                    ('Show lower bound', 2),
                    ('Show result only', 3),
                )
                cfg.anabatic.routingGauge = '{lib.name}'
                cfg.anabatic.globalLengthThreshold = 1450
                cfg.anabatic.saturateRatio = 0.90
                cfg.anabatic.saturateRp = 10
                cfg.anabatic.topRoutingLayer = '{topmetal.name}'
                cfg.anabatic.edgeLength = 48
                cfg.anabatic.edgeWidth = 8
                cfg.anabatic.edgeCostH = 9.0
                cfg.anabatic.edgeCostK = -10.0
                cfg.anabatic.edgeHInc = 1.0
                cfg.anabatic.edgeHScaling = 1.0
                cfg.anabatic.globalIterations = 10
                cfg.anabatic.globalIterations = [ 1, 100 ]
                cfg.anabatic.gcell.displayMode = 1
                cfg.anabatic.gcell.displayMode = (("Boundary", 1), ("Density", 2))
                cfg.katana.hTracksReservedLocal = 4
                cfg.katana.hTracksReservedLocal = [0, 20]
                cfg.katana.vTracksReservedLocal = 3
                cfg.katana.vTracksReservedLocal = [0, 20]
                cfg.katana.termSatReservedLocal = 8
                cfg.katana.termSatThreshold = 9
                cfg.katana.eventsLimit = 4000002
                cfg.katana.ripupCost = 3
                cfg.katana.ripupCost = [0, None]
                cfg.katana.strapRipupLimit = 16
                cfg.katana.strapRipupLimit = [1, None]
                cfg.katana.localRipupLimit = 9
                cfg.katana.localRipupLimit = [1, None]
                cfg.katana.globalRipupLimit = 5
                cfg.katana.globalRipupLimit = [1, None]
                cfg.katana.longGlobalRipupLimit = 5
                cfg.chip.padCoreSide = 'South'
        """[1:])

    def _s_plugins(self):
        return dedent(f"""
            # Plugins setup
            with CfgCache(priority=Cfg.Parameter.Priority.ConfigurationFile) as cfg:
                cfg.viewer.minimumSize = 500
                cfg.viewer.pixelThreshold = 10
                cfg.chip.block.rails.count = 5
                cfg.chip.block.rails.hWidth = u(2.68)
                cfg.chip.block.rails.vWidth = u(2.68)
                cfg.chip.block.rails.hSpacing = u(0.7)
                cfg.chip.block.rails.vSpacing = u(0.7)
                cfg.clockTree.minimumSide = l(600)
                cfg.clockTree.buffer = 'buf_x1'
                cfg.clockTree.placerEngine = 'Etesian'
                cfg.block.spareSide = 10
                cfg.spares.buffer = 'buf_x4'
                cfg.spares.maxSinks = 31
        """[1:])

    def _s_load(self, lib):
        s = dedent(f"""
            def _load():
                af = CRL.AllianceFramework.get()
                db = DataBase.getDB()
                tech = db.getTechnology()
                rootlib = db.getRootLibrary()

                lib = Library.create(rootlib, '{lib.name}')
        """)

        # Trigger layout generation
        for cell in lib.cells:
            l = cell.layout

        s += "    new_cells = {\n"
        s += "".join(
            f"        '{cell.name}': Cell.create(lib, '{cell.name}'),\n"
            for cell in lib.cells
        )
        s += "    }\n"

        s += indent(
            "".join(self._s_cell(lib, cell) for cell in lib.cells),
            prefix="    ",
        )

        s += indent(dedent("""
            af.wrapLibrary(lib, 0)

            return lib
        """), prefix="    ")

        return s

    def _s_cell(self, lib: _lbry.Library, cell: _cell.Cell):
        try:
            s = dedent(f"""
                cell = new_cells['{cell.name}']
                with UpdateSession():
            """)

            if hasattr(cell, "layout"):
                layout = cell.layout
                bnd = layout.boundary
                assert bnd is not None, f"Cell boundary needed for {cell.name}"

                pls = tuple(layout._sublayouts.__iter_type__(_laylay._MaskShapesSubLayout))
                def get_netname(sl: _laylay._MaskShapesSubLayout):
                    return "*" if sl.net is None else sl.net.name

                net_names = sorted({get_netname(sl) for sl in pls})

                s += (
                    "    cell.setAbutmentBox(Box(\n"
                    f"        u({bnd.left}), u({bnd.bottom}), u({bnd.right}), u({bnd.top}),\n"
                    "    ))\n"
                    "    nets = {\n"
                    + "\n".join(
                        f"        '{net_name}': Net.create(cell, '{net_name}'),"
                        for net_name in net_names
                    )
                    + "\n    }\n"
                )

                for sl in pls:
                    s += indent(
                        f"net = nets['{get_netname(sl)}']\n" +
                        "".join(self._s_shape(ms) for ms in sl.shapes),
                        prefix="    ",
                    )

                spec = self.spec
                if spec is not None:
                    ckt = cell.circuit

                    for net in ckt.ports:
                        if net.name in spec.globalnets:
                            s += f"    nets['{net.name}'].setGlobal(True)\n"
                    cb = spec.net_direction_cb
                    if cb is not None:
                        for net in ckt.ports:
                            net_name = net.name
                            t = cb(net_name)
                            if t == "supply":
                                s += (
                                    f"    nets['{net_name}'].setType(Net.Type.POWER)\n"
                                    f"    nets['{net_name}'].setDirection(Net.Direction.IN)\n"
                                )
                            elif t == "ground":
                                s += (
                                    f"    nets['{net_name}'].setType(Net.Type.GROUND)\n"
                                    f"    nets['{net_name}'].setDirection(Net.Direction.IN)\n"
                                )
                            elif t == "clock":
                                s += (
                                    f"    nets['{net_name}'].setType(Net.Type.CLOCK)\n"
                                    f"    nets['{net_name}'].setDirection(Net.Direction.IN)\n"
                                )
                            elif t == "in":
                                s += f"    nets['{net_name}'].setDirection(Net.Direction.IN)\n"
                            elif t == "out":
                                s += f"    nets['{net_name}'].setDirection(Net.Direction.OUT)\n"
                            else:
                                raise ValueError(
                                    f"wrong net_direction_cb return value '{t}'"
                                )
                        
                for sl in layout._sublayouts.__iter_type__(_laylay._InstanceSubLayout):
                    # Currently usage of af.getCell() may not work as intended when
                    # two libraries have a cell with the same name.
                    # TODO: support libraries with cells with same name properly
                    r = {
                        _geo.Rotation.R0: "ID",
                        _geo.Rotation.R90: "R1",
                        _geo.Rotation.R180: "R2",
                        _geo.Rotation.R270: "R3",
                        _geo.Rotation.MX: "MX",
                        _geo.Rotation.MX90: "XR",
                        _geo.Rotation.MY: "MY",
                        _geo.Rotation.MY90: "YR",
                    }[sl.rotation]
                    s += indent(
                        dedent(f"""
                            try:
                                subcell = new_cells['{sl.inst.cell.name}']
                            except:
                                subcell = af.getCell('{sl.inst.cell.name}', 0)
                            trans = Transformation(
                                u({sl.origin.x}), u({sl.origin.y}), Transformation.Orientation.{r},
                            )
                            Instance.create(
                                cell, '{sl.inst.name}', subcell, trans,
                                Instance.PlacementStatus.PLACED,
                            )
                        """[1:]),
                        prefix = "    "
                    )
            return s
        except NotImplementedError:
            return f"# Export failed for cell '{cell.name}'"

    def _s_shape(self, shape: _geo.MaskShape) -> str:
        metalmasks = tuple(metal.mask for metal in self.metals)

        mask = shape.mask
        s = ""

        for ps in shape.shape.pointsshapes:
            coords = tuple(ps.points)

            if mask in self.pinmasks:
                metalmask = self.pinmasks[mask]
                metalidx = metalmasks.index(metalmask)
                if len(coords) != 5:
                    raise NotImplementedError(
                        f"Non-rectangular pin with coords '{coords}'"
                    )
                xs = tuple(coord.x for coord in coords)
                ys = tuple(coord.y for coord in coords)
                left = min(xs)
                right = max(xs)
                bottom = round(min(ys), 6)
                top = round(max(ys), 6)
                width = round(right - left, 6)
                height = round(top - bottom, 6)

                routingdir = (
                    None if self.metalsdir is None
                    else self.metalsdir[metalidx]
                )
                if routingdir is None:
                    routingdir = (
                        "vertical" if height > width
                        else "horizontal"
                    )

                if routingdir == "vertical":
                    x = round(0.5*(left + right), 6)
                    s += dedent(f"""
                        Vertical.create(
                            net, tech.getLayer('{mask.name}'),
                            u({x}), u({width}), u({bottom}), u({top}),
                        )
                        pin = Vertical.create(
                            net, tech.getLayer('{metalmask.name}'),
                            u({x}), u({width}), u({bottom}), u({top}),
                        )
                        net.setExternal(True)
                        NetExternalComponents.setExternal(pin)
                    """[1:])
                else:
                    assert routingdir == "horizontal"
                    y = round(0.5*(bottom + top), 6)
                    s += dedent(f"""
                        Horizontal.create(
                            net, tech.getLayer('{mask.name}'),
                            u({y}), u({height}), u({left}), u({right}),
                        )
                        pin = Horizontal.create(
                            net, tech.getLayer('{metalmask.name}'),
                            u({y}), u({height}), u({left}), u({right}),
                        )
                        net.setExternal(True)
                        NetExternalComponents.setExternal(pin)
                    """[1:])

            else:
                s += dedent(f"""
                    createRL(
                        tech, net, '{mask.name}',
                        ({",".join(self._s_point(point) for point in coords)}),
                    )
                """[1:])

        return s

    def _s_point(self, point: _geo.Point):
        # TODO: put on grid
        x = round(point.x, 6)
        y = round(point.y, 6)

        return f"({x},{y})"


class _TechnologyGenerator:
    def __call__(self, *, tech: _tch.Technology, gds_layers: GDSLayerSpecDict):
        self.tech = tech
        self.gds_layers = gds_layers

        return "\n".join((
            self._s_head(), self._s_analog(), self._s_technology(),
            self._s_display(), self._s_setup(),
        ))

    def _s_head(self):
        return dedent(f"""
            # Autogenerated file. Changes will be overwritten.

            try:
                import coriolis
            except ImportError:
                import CRL, Hurricane, Viewer, Cfg
                from Hurricane import (
                    Technology, DataBase, DbU, Library,
                    Layer, BasicLayer,
                    Cell, Net, Horizontal, Vertical, Rectilinear, Box, Point,
                    NetExternalComponents,
                )
                from common.colors import toRGB
                from common.patterns import toHexa
                from helpers import u
                from helpers.technology import createBL, createVia
                from helpers.overlay import CfgCache
                from helpers.analogtechno import Length, Area, Unit, Asymmetric, loadAnalogTechno
            else:
                from coriolis import CRL, Hurricane, Viewer, Cfg
                from coriolis.Hurricane import (
                    Technology, DataBase, DbU, Library,
                    Layer, BasicLayer,
                    Cell, Net, Horizontal, Vertical, Rectilinear, Box, Point,
                    NetExternalComponents,
                )
                from coriolis.technos.common.colors import toRGB
                from coriolis.technos.common.patterns import toHexa
                from coriolis.helpers import u
                from coriolis.helpers.technology import createBL, createVia
                from coriolis.helpers.overlay import CfgCache
                from coriolis.helpers.analogtechno import Length, Area, Unit, Asymmetric, loadAnalogTechno

            __all__ = ["analogTechnologyTable", "setup"]
        """[1:])

    def _s_setup(self):
        return dedent(f"""
            def setup():
                _setup_techno()
                _setup_display()
                loadAnalogTechno(analogTechnologyTable, __file__)
                try:
                    from .techno_fix import fix
                except:
                    pass
                else:
                    fix()
        """[1:])

    def _s_technology(self):
        gen = _LayerGenerator(tech=self.tech, gds_layers=self.gds_layers)

        # Take smallest transistor length as lambda
        lambda_ = min(
            trans.computed.min_l
            for trans in self.tech.primitives.__iter_type__(_prm.MOSFET)
        )

        assert (self.tech.grid % 1e-6) < 1e-9, "Unsupported grid"

        s_head = dedent(f"""
            def _setup_techno():
                db = DataBase.create()
                CRL.System.get()

                tech = Technology.create(db, '{self.tech.name}')

                DbU.setPrecision(2)
                DbU.setPhysicalsPerGrid({self.tech.grid}, DbU.UnitPowerMicro)
                with CfgCache(priority=Cfg.Parameter.Priority.ConfigurationFile) as cfg:
                    cfg.gdsDriver.metricDbu = {1e-6*self.tech.dbu}
                    cfg.gdsDriver.dbuPerUu = {self.tech.dbu}
                DbU.setGridsPerLambda({round(lambda_/self.tech.grid)})
                DbU.setSymbolicSnapGridStep(DbU.fromGrid(1.0))
                DbU.setPolygonStep(DbU.fromGrid(1.0))
                DbU.setStringMode(DbU.StringModePhysical, DbU.UnitPowerMicro)

        """[1:])

        s_prims = ""
        written_prims = set()
        vias = tuple(self.tech.primitives.__iter_type__(_prm.Via))

        for prim in self.tech.primitives:
            # Some primitives are handled later or don't need to be handled
            if isinstance(prim, (
                # Handled by Via
                _prm.WaferWire, _prm.GateWire, _prm.MetalWire,
                # Handled later
                _prm.Resistor, _prm.MIMCapacitor, _prm.Diode,
                _prm.MOSFETGate, _prm.MOSFET, _prm.Bipolar,
                # Not exported
                _prm.Base, _prm.RulePrimitiveT,
            )):
                continue

            # We have to make sure via layers are defined in between top and bottom
            # metal layers
            if isinstance(prim, _prm.Via):
                for prim2 in prim.bottom:
                    s_prims += gen(prim2)
                    written_prims.add(prim2)

            # Do not generate layer for Auxiliary layers to avoid having too many
            # layer definitions. Still mark the layer as written.
            # if not isinstance(prim, prm.Auxiliary):
                # s_prims += gen(prim)
            s_prims += gen(prim)
            written_prims.add(prim)

            # For top via also do the top layers
            if isinstance(prim, _prm.Via) and prim == vias[-1]:
                for prim2 in prim.top:
                    s_prims += gen(prim2)
                    written_prims.add(prim2)

        # Check if all basic layers were included
        unhandled_masks = (
            {prim.name for prim in written_prims}
            - {mask.name for mask in self.tech.designmasks}
        )
        if unhandled_masks:
            raise NotImplementedError(
                f"Layer generation for masks {unhandled_masks} not implemented",
            )

        s_prims += "\n# ViaLayers\n"
        for via in vias:
            s_prims += gen(via, via_layer=True)

        s_prims += "\n# Blockages\n"
        for prim in filter(lambda p: hasattr(p, "blockage"), self.tech.primitives):
            s_prims += dedent(f"""
                tech.getLayer('{prim.name}').setBlockageLayer(
                    tech.getLayer('{cast(_prm.BlockageAttrPrimitiveT, prim).blockage.name}')
                )
            """[1:])

        s_prims += "\n# Coriolis internal layers\n"
        for name, mat in (
            ("text.cell", "other"),
            ("text.instance", "other"),
            ("SPL1", "other"),
            ("AutoLayer", "other"),
            ("gmetalh", "metal"),
            ("gcontact", "cut"),
            ("gmetalv", "metal"),
        ):
            s_prims += _str_create_basic(name, mat)

        s_prims += "\n# Resistors\n"
        for prim in self.tech.primitives.__iter_type__(_prm.Resistor):
            assert prim not in written_prims
            s_prims += gen(prim)
            written_prims.add(prim)

        s_prims += "\n# Capacitors\n"
        for prim in self.tech.primitives.__iter_type__(_prm.MIMCapacitor):
            assert prim not in written_prims
            s_prims += gen(prim)
            written_prims.add(prim)

        s_prims += "\n# Transistors\n"
        for prim in self.tech.primitives.__iter_type__((_prm.MOSFETGate, _prm.MOSFET)):
            assert prim not in written_prims
            s_prims += gen(prim)
            written_prims.add(prim)

        s_prims += "\n# Bipolars\n"
        for prim in self.tech.primitives.__iter_type__(_prm.Bipolar):
            assert prim not in written_prims
            s_prims += gen(prim)
            written_prims.add(prim)

        return s_head + indent(s_prims, prefix="    ")

    def _s_analog(self):
        gen = _AnalogGenerator(self.tech)

        s = dedent(f"""
            analogTechnologyTable = (
                ('Header', '{self.tech.name}', DbU.UnitPowerMicro, 'alpha'),
                ('PhysicalGrid', {self.tech.grid}, Length, ''),

            """[1:]
        )
        s += indent(
            "".join(gen(prim) for prim in self.tech.primitives),
            prefix="    ",
        )
        s += ")\n"

        return s

    def _s_display(self):
        s = dedent("""
            def _setup_display():
                # ----------------------------------------------------------------------
                # Style: Alliance.Classic [black]

                threshold = 0.2 if Viewer.Graphics.isHighDpi() else 0.1

                style = Viewer.DisplayStyle( 'Alliance.Classic [black]' )
                style.setDescription( 'Alliance Classic Look - black background' )
                style.setDarkening  ( Viewer.DisplayStyle.HSVr(1.0, 3.0, 2.5) )

                # Viewer.
                style.addDrawingStyle( group='Viewer', name='fallback'      , color=toRGB('Gray238'    ), border=1, pattern='55AA55AA55AA55AA' )
                style.addDrawingStyle( group='Viewer', name='background'    , color=toRGB('Gray50'     ), border=1 )
                style.addDrawingStyle( group='Viewer', name='foreground'    , color=toRGB('White'      ), border=1 )
                style.addDrawingStyle( group='Viewer', name='rubber'        , color=toRGB('192,0,192'  ), border=4, threshold=0.02 )
                style.addDrawingStyle( group='Viewer', name='phantom'       , color=toRGB('Seashell4'  ), border=1 )
                style.addDrawingStyle( group='Viewer', name='boundaries'    , color=toRGB('wheat1'     ), border=2, pattern='0000000000000000', threshold=0 )
                style.addDrawingStyle( group='Viewer', name='marker'        , color=toRGB('80,250,80'  ), border=1 )
                style.addDrawingStyle( group='Viewer', name='selectionDraw' , color=toRGB('White'      ), border=1 )
                style.addDrawingStyle( group='Viewer', name='selectionFill' , color=toRGB('White'      ), border=1 )
                style.addDrawingStyle( group='Viewer', name='grid'          , color=toRGB('White'      ), border=1, threshold=2.0 )
                style.addDrawingStyle( group='Viewer', name='spot'          , color=toRGB('White'      ), border=2, threshold=6.0 )
                style.addDrawingStyle( group='Viewer', name='ghost'         , color=toRGB('White'      ), border=1 )
                style.addDrawingStyle( group='Viewer', name='text.ruler'    , color=toRGB('White'      ), border=1, threshold=  0.0 )
                style.addDrawingStyle( group='Viewer', name='text.instance' , color=toRGB('White'      ), border=1, threshold=400.0 )
                style.addDrawingStyle( group='Viewer', name='text.reference', color=toRGB('White'      ), border=1, threshold=200.0 )
                style.addDrawingStyle( group='Viewer', name='undef'         , color=toRGB('Violet'     ), border=0, pattern='2244118822441188' )
        """[1:])

        clrs = ("Blue", "Aqua", "LightPink", "Green", "Yellow", "Violet", "Red")

        s += "\n    # Active Layers.\n"
        for prim in self.tech.primitives.__iter_type__(_prm.Well):
            rgb = "Tan" if prim.type_ == _prm.nImpl else "LightYellow"
            s += (
                f"    style.addDrawingStyle(group='Active Layers', name='{prim.name}'"
                f", color=toRGB('{rgb}'), pattern=toHexa('urgo.8'), border=1"
                ", threshold=threshold)\n"
            )
        for prim in filter(
            lambda p: not isinstance(p, _prm.Well),
            self.tech.primitives.__iter_type__(_prm.Implant),
        ):
            rgb = "LawnGreen" if prim.type_ == _prm.nImpl else "Yellow"
            s += (
                f"    style.addDrawingStyle(group='Active Layers', name='{prim.name}'"
                f", color=toRGB('{rgb}'), pattern=toHexa('antihash0.8'), border=1"
                ", threshold=threshold)\n"
            )
        for prim in self.tech.primitives.__iter_type__(_prm.WaferWire):
            s += (
                f"    style.addDrawingStyle(group='Active Layers', name='{prim.name}'"
                ", color=toRGB('White'), pattern=toHexa('antihash0.8'), border=1"
                ", threshold=threshold)\n"
            )
            if hasattr(prim, "pin"):
                s += (
                    "    style.addDrawingStyle(group='Active Layers'"
                    f", name='{prim.pin.name}', color=toRGB('White')"
                    ", pattern=toHexa('antihash0.8'), border=2"
                    ", threshold=threshold)\n"
                )
        for i, prim in enumerate(self.tech.primitives.__iter_type__(_prm.GateWire)):
            rgb = "Red" if i == 0 else "Orange"
            s += (
                f"    style.addDrawingStyle(group='Active Layers', name='{prim.name}'"
                f", color=toRGB('{rgb}'), pattern=toHexa('antihash0.8'), border=1"
                ", threshold=threshold)\n"
            )
            if hasattr(prim, "pin"):
                s += (
                    "    style.addDrawingStyle(group='Active Layers'"
                    f", name='{prim.pin.name}', color=toRGB('{rgb}')"
                    ", pattern=toHexa('antihash0.8'), border=2"
                    ", threshold=threshold)\n"
                )

        s += "\n    # Routing Layers.\n"
        for i, prim in enumerate(self.tech.primitives.__iter_type__(_prm.MetalWire)):
            rgb = clrs[i%len(clrs)]
            hexa = "slash.8" if i == 0 else "poids4.8"
            s += (
                f"    style.addDrawingStyle(group='Routing Layers', name='{prim.name}'"
                f", color=toRGB('{rgb}'), pattern=toHexa('{hexa}'), border=1"
                ", threshold=threshold)\n"
            )
            if hasattr(prim, "pin"):
                s += (
                    f"    style.addDrawingStyle(group='Routing Layers'"
                    f", name='{prim.pin.name}', color=toRGB('{rgb}'), pattern=toHexa('{hexa}')"
                    ", border=2, threshold=threshold)\n"
                )

        s += "\n    # Cuts (VIA holes).\n"
        for i, prim in enumerate(
            self.tech.primitives.__iter_type__((_prm.Via, _prm.PadOpening)),
        ):
            rgb = clrs[i%len(clrs)] if i > 0 else "0,150,150"
            s += (
                f"    style.addDrawingStyle(group='Cuts (VIA holes', name='{prim.name}'"
                f", color=toRGB('{rgb}'), threshold=threshold)\n"
            )

        s += "\n    # Blockages.\n"
        blockages = {
            cast(_prm.BlockageAttrPrimitiveT, prim).blockage
            for prim in filter(lambda p: hasattr(p, "blockage"), self.tech.primitives)
        }
        for i, prim in enumerate(filter(
            lambda p: p in blockages, self.tech.primitives.__iter_type__(_prm.Marker)
        )):
            rgb = clrs[i%len(clrs)]
            hexa = "slash.8" if i == 0 else "poids4.8"
            s += (
                f"    style.addDrawingStyle(group='Blockages', name='{prim.name}'"
                f", color=toRGB('{rgb}'), pattern=toHexa('{hexa}')"
                ", border=4, threshold=threshold)\n"
            )

        s += indent(dedent("""

            # Knick & Kite.
            style.addDrawingStyle( group='Knik & Kite', name='SPL1'           , color=toRGB('Red'        ) )
            style.addDrawingStyle( group='Knik & Kite', name='AutoLayer'      , color=toRGB('Magenta'    ) )
            style.addDrawingStyle( group='Knik & Kite', name='gmetalh'        , color=toRGB('128,255,200'), pattern=toHexa('antislash2.32'    ), border=1 )
            style.addDrawingStyle( group='Knik & Kite', name='gmetalv'        , color=toRGB('200,200,255'), pattern=toHexa('light_antihash1.8'), border=1 )
            style.addDrawingStyle( group='Knik & Kite', name='gcontact'       , color=toRGB('255,255,190'),                                      border=1 )
            style.addDrawingStyle( group='Knik & Kite', name='Anabatic::Edge' , color=toRGB('255,255,190'), pattern='0000000000000000'         , border=4, threshold=0.02 )
            style.addDrawingStyle( group='Knik & Kite', name='Anabatic::GCell', color=toRGB('255,255,190'), pattern='0000000000000000'         , border=2, threshold=threshold )

            Viewer.Graphics.addStyle( style )

            # ----------------------------------------------------------------------
            # Style: Alliance.Classic [white].

            style = Viewer.DisplayStyle( 'Alliance.Classic [white]' )
            style.inheritFrom( 'Alliance.Classic [black]' )
            style.setDescription( 'Alliance Classic Look - white background' )
            style.setDarkening  ( Viewer.DisplayStyle.HSVr(1.0, 3.0, 2.5) )

            style.addDrawingStyle( group='Viewer', name='background', color=toRGB('White'), border=1 )
            style.addDrawingStyle( group='Viewer', name='foreground', color=toRGB('Black'), border=1 )
            style.addDrawingStyle( group='Viewer', name='boundaries', color=toRGB('Black'), border=1, pattern='0000000000000000' )
            Viewer.Graphics.addStyle( style )

            Viewer.Graphics.setStyle( 'Alliance.Classic [black]' )
        """[1:]), prefix="    ")

        return s


class FileExporter:
    def __init__(self, *,
        tech: _tch.Technology, gds_layers: GDSLayerSpecDict,
        spec: Optional[CoriolisExportSpec]=None
    ):
        self._tech = tech
        self._gds_layers = gds_layers
        self._spec = spec

    @property
    def tech(self) -> _tch.Technology:
        return self._tech
    @property
    def gds_layers(self) -> GDSLayerSpecDict:
        return self._gds_layers
    @property
    def spec(self) -> Optional[CoriolisExportSpec]:
        return self._spec

    @overload
    def __call__(self,
        obj: None, *, routinggauge: None=None,
    ) -> str:
        ...
    @overload
    def __call__(self,
        obj: _lbry.RoutingGaugeLibrary, *, routinggauge: None=None,
    ) -> str:
        ...
    @overload
    def __call__(self,
        obj: _lbry.Library, *, routinggauge: Optional[_rg.RoutingGauge]=None,
    ) -> str:
        ...
    def __call__(self,
        obj: Optional[_lbry.Library]=None, *, routinggauge: Optional[_rg.RoutingGauge]=None,
    ) -> str:
        if obj is None:
            s = self._s_tech()
        elif isinstance(obj, _lbry.Library):
            s = self._s_lib(obj, routinggauge=routinggauge)
        else:
            raise TypeError("object has to be None or of type 'Library'")

        return s

    def _s_tech(self):
        gen = _TechnologyGenerator()
        return gen(tech=self.tech, gds_layers=self.gds_layers)

    def _s_lib(self, lib: _lbry.Library, *, routinggauge: Optional[_rg.RoutingGauge]):
        gen = _LibraryGenerator(tech=self.tech, spec=self.spec)
        return gen(lib, routinggauge=routinggauge)
