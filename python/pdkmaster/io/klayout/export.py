# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from textwrap import dedent
from itertools import product
from xml.etree import ElementTree as ET
from typing import Any, Tuple, List, Dict, Set, Iterable, Optional, Union, cast, overload

from pdkmaster.technology import property_ as _prp

from pdkmaster import _util, dispatch as _dsp
from pdkmaster.typing import GDSLayerSpecDict
from pdkmaster.technology import (
    property_ as _prp, rule as _rle, wafer_ as _wfr, mask as _msk, edge as _edg,
    geometry as _geo, primitive as _prm, net as _net, technology_ as _tch,
)
from pdkmaster.design import layout as _lay, cell as _cell, library as _lbry
from pdkmaster.design.layout import layout_ as _laylay
from pdkmaster.io.spice import SpicePrimParamsT, SpicePrimsParamSpec

import pya


__all__= ["FileExporter", "export2db"]


class _MaskConverter(_dsp.MaskDispatcher):
    def __init__(self, *, tech: _tch.Technology) -> None:
        super().__init__()

        self.tech = tech

    def __call__(self, mask: _msk.MaskT) -> str:
        return super().__call__(mask)

    @staticmethod
    def __legalized_maskname(name: str) -> str:
        if name[0] in "0123456789":
            name = "_" + name
        return name.replace(".", "_").replace(":", "__")

    def DesignMask(self, mask: _msk.DesignMask) -> str:
        return self.__legalized_maskname(mask.name)

    def _MaskAlias(self, mask: _msk._MaskAlias) -> str:
        return self.__legalized_maskname(mask.name)

    # Handled on higher level
    # def _PartsWith(self, pw: msk._PartsWith):
    #     ...

    def Join(self, join: _msk.Join) -> str:
        return f"({'+'.join(self(m) for m in join.masks)})"

    def Intersect(self, intersect: _msk.Intersect) -> str:
        return f"({'&'.join(self(m) for m in intersect.masks)})"

    def _MaskRemove(self, mr: _msk._MaskRemove):
        return f"({self(mr.from_)}-{self(mr.what)})"

    def _Wafer(self, wafer: _wfr._Wafer):
        # Size box to be sure it is big enough for substrate enclosure check
        assert wafer == _wfr._wafer_base
        bias = 0.0
        for act in self.tech.primitives.__iter_type__(_prm.WaferWire):
            for enc in (act.min_substrate_enclosure, act.min_substrate_enclosure_same_type):
                if enc is not None:
                    bias = max(bias, enc.max())

        return "extent" if bias < self.tech.grid/100 else f"extent.sized({bias:.6})"
_mask_conv: Any = None


class _EdgeConverter(_dsp.EdgeDispatcher):
    def __call__(self, edge: _edg.EdgeT) -> str:
        return super().__call__(edge)

    def MaskEdge(self, edge: _edg.MaskEdge) -> str:
        return f"{_mask_conv(edge.mask)}.edges"

    def _DualEdgeOperation(self, op: _edg._DualEdgeOperation) -> str:
        s_edge1 = self(op.edge1)
        if isinstance(op.edge2, _msk.MaskT):
            s_edge2 = _mask_conv(op.edge2)
        elif isinstance(op.edge2, _edg.EdgeT):
            s_edge2 = self(op.edge2)
        else: # pragma: no cover
            raise TypeError(f"[Internal error]Unexpected type for edge2 of {str(op)}")
        if op.operation == "interact_with":
            return f"{s_edge1}.interacting({s_edge2})"
        else: # pragma: no cover
            raise NotImplementedError(f"[Internal error]Operation: {op.operation}")

    def Join(self, join: _edg.Join) -> str:
        s_join = "+".join(
            _mask_conv(e) if isinstance(e, _msk.MaskT) else self(e)
            for e in join.edges
        )
        return f"({s_join})"

    def Intersect(self, intersect: _edg.Intersect) -> str:
        s_intersect = "&".join(
            _mask_conv(e) if isinstance(e, _msk.MaskT) else self(e)
            for e in intersect.edges
        )
        return f"({s_intersect})"
_edge_conv = _EdgeConverter()


def _str_designmask(mask: _msk.DesignMask, *, gds_layers: GDSLayerSpecDict):
    gds_layer = gds_layers[mask.name]
    if gds_layer is None:
        return ""
    if not isinstance(gds_layer, tuple):
        gds_layer = (gds_layer, 0)
    return f"{_mask_conv(mask)} = input{gds_layer}\n"


def _str_alias(mask: _msk._MaskAlias):
    return f"{_mask_conv(mask)} = {_mask_conv(mask.mask)}\n"


def _str_grid(mask: _msk.MaskT, grid: float):
    s_mask = _mask_conv(mask)
    return dedent(f"""
        {s_mask}.ongrid({grid}).output(
            "{s_mask} grid", "{s_mask} grid: {grid}µm"
        )
    """[1:])


class _RuleConverter(_dsp.RuleDispatcher):
    def __call__(self, rule: _rle.RuleT, *, allow_unimplented: bool=False) -> str:
        if allow_unimplented:
            try:
                s = super().__call__(rule)
            except NotImplementedError:
                s = "# Not supported\n"
        else:
            s = super().__call__(rule)

        return f"# {rule}\n{s}"

    def GreaterEqual(self, ge: _prp.Operators.GreaterEqual):
        left = ge.left
        right = ge.right
        if isinstance(left, _msk._MaskProperty):
            s_mask = _mask_conv(left.mask)
            prop = left.prop_name
            if prop in {"width", "space"}:
                return dedent(f"""
                    {s_mask}.{prop}({right}).output(
                        "{s_mask} {prop}", "{s_mask} minimum {prop}: {right}µm"
                    )
                """[1:])
            elif left.prop_name == "area":
                return dedent(f"""
                    {s_mask}.with_area(nil, {right}).output(
                        "{s_mask} area", "{s_mask} minimum area: {right}µm"
                    )
                """[1:])
            elif left.prop_name == "density":
                assert isinstance(right, float)
                return dedent(f"""
                    {s_mask}_mindens = polygon_layer
                    dens_check({s_mask}_mindens, {s_mask}, {right}, 1)
                    {s_mask}_mindens.output(
                        "{s_mask} density", "{s_mask} minimum density: {round(100*right)}%"
                    )
                """[1:])
        elif isinstance(left, _msk._DualMaskProperty):
            prop = left.prop_name
            if (
                (prop == "space")
                and (
                    isinstance(left.mask1, _msk._PartsWith)
                    or isinstance(left.mask2, _msk._PartsWith)
                )
            ):
                # Special code for handling width based spacing rules
                # Main objective if to support space tabels specified for primitives
                # Other application area are mainly untested
                if isinstance(left.mask1, _msk._PartsWith):
                    conds = left.mask1.condition
                    assert left.mask1.mask == left.mask2
                    s_mask = _mask_conv(left.mask1.mask)
                else:
                    assert isinstance(left.mask2, _msk._PartsWith)
                    conds = left.mask2.condition
                    assert left.mask2.mask == left.mask1
                    s_mask = _mask_conv(left.mask2.mask)

                width = None
                length = None
                for cond in conds:
                    assert isinstance(cond, _prp.Operators.GreaterEqual)
                    assert isinstance(cond.left, _msk._MaskProperty)
                    if cond.left.prop_name == "width":
                        width = cond.right
                    elif cond.left.prop_name == "length":
                        length = cond.right
                    else: # pragma: no cover
                        raise RuntimeError("Internal error")
                assert width is not None, "Internal error"
                if length is None:
                    return dedent(f"""
                        space4width_check({s_mask}, {width}, {right}).output(
                            "{s_mask} table spacing",
                            "Minimum {s_mask} spacing for {cond.right}µm width: {right}µm"
                        )
                    """[1:])
                else:
                    return dedent(f"""
                        space4width_check({s_mask}, {width}, {right}).output(
                            "[Warning]{s_mask} table spacing",
                            "Check minimum {s_mask} spacing for {width}µm width and {length}µm length: {right}µm"
                        )
                        space4widthlength_check({s_mask}, {width}, {length}, {right}).output(
                            "{s_mask} table spacing",
                            "Minimum {s_mask} spacing for {width}µm width and {length}µm length: {right}µm"
                        )
                    """[1:])

            s_mask1 = _mask_conv(left.mask1)
            s_mask2 = _mask_conv(left.mask2)
            if prop == "space":
                assert isinstance(left, _msk.Spacing)
                if not left.without_zero:
                    return dedent(f"""
                        {s_mask1}.separation({s_mask2}, {right}, square).output(
                            "{s_mask1}:{s_mask2} spacing",
                            "Minimum spacing between {s_mask1} and {s_mask2}: {right}µm"
                        )
                    """[1:])
                else: # without_zero
                    # Converting to polygons will remove zero width separation
                    return dedent(f"""
                        {s_mask1}.separation({s_mask2}, {right}, square).polygons.output(
                            "{s_mask1}:{s_mask2} spacing",
                            "Minimum spacing between {s_mask1} and {s_mask2}: {right}µm"
                        )
                    """[1:])
            elif prop == "extend_over":
                return dedent(f"""
                    extend_check({s_mask2}, {s_mask1}, {right}).output(
                        "{s_mask1}:{s_mask2} extension",
                        "Minimum extension of {s_mask1} of {s_mask2}: {right}µm"
                    )
                """[1:])
        elif isinstance(left, _msk._DualMaskEnclosureProperty):
            s_mask1 = _mask_conv(left.mask1)
            s_mask2 = _mask_conv(left.mask2)
            prop = left.prop_name
            if prop == "enclosed_by":
                # TODO: Proper typing for Property
                assert isinstance(right, _prp.Enclosure)
                if not right.is_assymetric:
                    return dedent(f"""
                        {s_mask2}.enclosing({s_mask1}, {right.first}).output(
                            "{s_mask2}:{s_mask1} enclosure",
                            "Minimum enclosure of {s_mask2} around {s_mask1}: {right.first}µm"
                        )
                    """[1:])
                else:
                    s_desc = (
                        f"Minimum enclosure of {s_mask2} around {s_mask1}: "
                        f"{right.min()}µm minimum, {right.max()}µm opposite"
                    )
                    return dedent(f"""
                        oppenc_check({s_mask1}, {s_mask2}, {right.min()}, {right.max()}).output(
                            "{s_mask2}:{s_mask1} asymmetric enclosure",
                            "{s_desc}"
                        )
                    """[1:])
        elif isinstance(left, _edg._EdgeProperty):
            s_edge = _edge_conv(left.edge)
            prop = left.prop_name
            if prop == "length":
                return dedent(f"""
                    {s_edge}.with_length(nil, {right}).output(
                        "{s_edge} length",
                        "Minimum length of {s_edge}: {right}µm"
                    )
                """[1:])
            elif prop == "space":
                return dedent(f"""
                    {s_edge}.space({right}).output(
                        "{s_edge} space",
                        "Minimum spacing between {s_edge}: {right}µm"
                    )
                """[1:])
        elif isinstance(left, _edg._DualEdgeProperty):
            s_edge1 = _edge_conv(left.edge1)
            s_edge2 = (
                _mask_conv(left.edge2)+".edges" if isinstance(left.edge2, _msk.MaskT)
                else _edge_conv(left.edge2)
            )
            prop = left.prop_name
            if prop == "enclosed_by":
                return dedent(f"""
                    {s_edge2}.enclosing({s_edge1}, {right}).output(
                        "{s_edge2}:{s_edge1} enclosure",
                        "Minimum enclosure of {s_edge2} around {s_edge1}: {right}µm"
                    )
                """[1:])

        raise NotImplementedError(f"GreateEqual rule '{ge}'") # pragma: no cover

    def Equal(self, eq: _prp.Operators.Equal) -> str:
        left = eq.left
        right = eq.right
        assert isinstance(right, left.value_type)
        if isinstance(left, _msk._MaskProperty):
            s_mask = _mask_conv(left.mask)
            prop = left.prop_name
            if prop == "width":
                return dedent(f"""
                    width_check({s_mask}, {right}).output(
                        "{s_mask} width", "{s_mask} width: {right}µm"
                    )
                """[1:])
            elif prop == "area":
                if round(right, 6) != 0.0:
                    raise ValueError("For area equal check value can only be 0.0")
                return f'{s_mask}.output("{s_mask} empty")\n'
        elif isinstance(left, _edg._EdgeProperty):
            s_edge = _edge_conv(left.edge)
            prop = left.prop_name
            if prop == "length":
                if round(right, 6) != 0.0:
                    raise ValueError("For length equal check value can only be 0.0")
                return f'{s_edge}.output("{s_edge} empty")\n'

        raise NotImplementedError(f"Equal rule '{eq}'") # pragma: no cover

    def SmallerEqual(self, se: _prp.Operators.SmallerEqual) -> str:
        left = se.left
        right = se.right
        if isinstance(left, _edg._EdgeProperty):
            s_edge = _edge_conv(left.edge)
            prop = left.prop_name
            if prop == "length":
                return dedent(f"""
                    {s_edge}.with_length({right}, nil).output(
                        "{s_edge} maximum length",
                        "Maximum length of {s_edge}: {right}µm"
                    )
                """[1:])

        raise NotImplementedError(f"SmallerEqual rule '{se}'") # pragma: no cover

    def _MaskAlias(self, alias: _msk._MaskAlias) -> str:
        return f"{_mask_conv(alias)} = {_mask_conv(alias.mask)}\n"

    def Connect(self, conn: _msk.Connect) -> str:
        return "".join(
            f"connect({_mask_conv(mask1)}, {_mask_conv(mask2)})\n"
            for mask1, mask2 in product(conn.mask1, conn.mask2)
        )
_rule_conv = _RuleConverter()


def _str_lvsresistor(res: _prm.Resistor, *, params: SpicePrimParamsT):
    s = f"# {res.name}\n"

    s_res = _mask_conv(res.mask)
    s_conn = _mask_conv(res.wire.conn_mask)

    sheetres = params["sheetres"]
    model: Optional[str] = params.get("model", None)
    if sheetres is not None:
        eq = "RES" if model is None else model
        s += dedent(f"""
            extract_devices(resistor("{res.name}", {sheetres}), {{
                "R" => {s_res}, "C" => {s_conn},
            }})
            same_device_classes("{res.name}", "{eq}")
        """[1:])

    return s


def _str_lvsdiode(tech: _tch.Technology, diode: _prm.Diode, spice_params: SpicePrimParamsT):
    s = f"# {diode.name}\n"

    if diode.implant:
        is_n = any(impl.type_ == _prm.nImpl for impl in diode.implant)
    else:
        is_n = any(impl.type_ == _prm.pImpl for impl in diode.wire.implant)

    s_diode = _mask_conv(diode.mask)
    s_conn = _mask_conv(diode.wire.conn_mask)
    s_well = _mask_conv(
        diode.well.mask if diode.well is not None
        else tech.substrate_prim.mask
    )

    if is_n:
        s_p = s_well
        s_n = s_diode
        s_conn_port = "tC"
    else:
        s_n = s_well
        s_p = s_diode
        s_conn_port = "tA"

    s += dedent(f"""
        extract_devices(diode("{spice_params['model']}"), {{
            "P" => {s_p}, "N" => {s_n}, "{s_conn_port}" => {s_conn}
        }})
    """[1:])

    return s


def _str_lvsmosfet(tech: _tch.Technology, mosfet: _prm.MOSFET, spice_params: SpicePrimParamsT):
    s = f"# {mosfet.name}\n"

    s_sd = _mask_conv(mosfet.gate.active.conn_mask)
    s_gate = _mask_conv(mosfet.gate4mosfet.mask)
    s_bulk = _mask_conv(
        mosfet.well.mask if mosfet.well is not None
        else tech.substrate_prim.mask
    )
    s_poly = _mask_conv(mosfet.gate.poly.conn_mask)

    s += dedent(f"""
        extract_devices(mos4("{spice_params['model']}"), {{
            "SD" => {s_sd}, "G" => {s_gate}, "tG" => {s_poly}, "W" => {s_bulk},
        }})
    """[1:])

    return s


class FileExporter:
    def __init__(self, *,
        tech: _tch.Technology, export_name: Optional[str]=None,
        gds_layers: GDSLayerSpecDict, prims_spiceparams: SpicePrimsParamSpec,
    ):
        self.tech = tech
        self.export_name = tech.name if export_name is None else export_name
        self.gds_layers = gds_layers
        self.prims_spiceparams = prims_spiceparams

        global _mask_conv
        _mask_conv = _MaskConverter(tech=tech)

    def __call__(self, *, layerprops: Optional[str]=None):
        return {
            "drc": self._s_drc(),
            "ly_drc": self._ly_drc(),
            "extract": self._s_extract(),
            "ly_extract": self._ly_extract(),
            "lvs": self._s_lvs(),
            "ly_tech": self._ly_tech(layerprops=layerprops),
        }

    def _s_drc(self):
        s = dedent(f"""
            # Autogenerated file. Changes will be overwritten.

            source_file = ENV["SOURCE_FILE"]
            cell_name = ENV["CELL_NAME"]
            if cell_name.empty?
                source(source_file)
            else
                source(source_file, cell_name)
            end
            report("{self.export_name} DRC", ENV["REPORT_FILE"])

        """[1:])

        return s + self._s_drcrules()

    def _ly_drc(self):
        ly_drc = ET.Element("klayout-macro")
        ET.SubElement(ly_drc, "description")
        ET.SubElement(ly_drc, "version")
        ET.SubElement(ly_drc, "category").text = "drc"
        ET.SubElement(ly_drc, "prolog")
        ET.SubElement(ly_drc, "epilog")
        ET.SubElement(ly_drc, "doc")
        ET.SubElement(ly_drc, "autorun").text = "false"
        ET.SubElement(ly_drc, "autorun-early").text = "false"
        ET.SubElement(ly_drc, "shortcut")
        ET.SubElement(ly_drc, "show-in-menu").text = "true"
        ET.SubElement(ly_drc, "group-name").text = "drc_scripts"
        ET.SubElement(ly_drc, "menu-path").text = "tools_menu.drc.end"
        ET.SubElement(ly_drc, "interpreter").text = "dsl"
        ET.SubElement(ly_drc, "dsl-interpreter-name").text = "drc-dsl-xml"
        s = dedent(f"""
            # Autogenerated file. Changes will be overwritten.
            
            report("{self.export_name} DRC")

        """[1:]) + self._s_drcrules()
        ET.SubElement(ly_drc, "text").text = s
        
        return ly_drc

    def _s_drcrules(self):
        s = dedent(f"""
            def width_check(layer, w)
                small = layer.width(w).polygons
                big = layer.sized(-0.5*w).size(0.5*w)

                small | big
            end

            def space4width_check(layer, w, s)
                big = layer.sized(-0.5*w).size(0.5*w)
                big.edges.separation(layer.edges, s)
            end

            def space4widthlength_check(layer, w, l, s)
                big = layer.sized(-0.5*w).size(0.5*w)
                big.edges.separation(layer.edges, s).with_length(l + 1.dbu, nil)
            end

            def oppenc_check(inner, outer, min, max)
                toosmall = outer.enclosing(inner, min).second_edges

                smallenc = outer.enclosing(inner, max - 1.dbu, projection).second_edges
                # These edges may not touch each other
                touching = smallenc.width(1.dbu, angle_limit(100)).edges

                inner.interacting(toosmall + touching)
            end

            def extend_check(base, extend, e)
                extend.enclosing(base, e).first_edges.not_interacting(base)
            end

            def dens_check(output, input, min, max)
                tp = RBA::TilingProcessor::new

                tp.output("res", output.data)
                tp.input("input", input.data)
                tp.dbu = 1.dbu  # establish the real database unit
                tp.var("vmin", min)
                tp.var("vmax", max)

                tp.queue("_tile && (var d = to_f(input.area(_tile.bbox)) / to_f(_tile.bbox.area); (d < vmin || d > vmax) && _output(res, _tile.bbox))")
                tp.execute("Density check")
            end

            deep
        """[1:])

        s += "\n# Define layers\n"
        assert isinstance(self.tech.rules, _rle.Rules), "Internal error"
        dms = tuple(self.tech.rules.__iter_type__(_msk.DesignMask))
        s += "".join(_str_designmask(dm, gds_layers=self.gds_layers) for dm in dms)

        s += "\n# Grid check\n"
        gridrules = cast(Tuple[_prp.Operators.Equal, ...], tuple(filter(
                lambda rule: (
                    isinstance(rule, _prp.Operators.Equal)
                    and isinstance(rule.left, _msk._MaskProperty)
                    and (rule.left.prop_name == "grid")
                ),
                self.tech.rules,
            )
        ))
        gridspecs = {
            cast(_msk._MaskProperty, gridrule.left).mask: gridrule.right
            for gridrule in gridrules
        }
        globalgrid = gridspecs[_wfr._wafer_base]
        s += "".join(
            _str_grid(dm, cast(float, gridspecs.get(dm, globalgrid)))
            for dm in dms
        )

        s2, aliases = self._s_aliases()
        s += s2

        s += "\n# Connectivity\n"
        conns = tuple(self.tech.rules.__iter_type__(_msk.Connect))
        s += "".join(_rule_conv(conn) for conn in conns)

        s += "\n# DRC rules\n" + "".join(
            _rule_conv(rule) for rule in filter(
                lambda rule: rule not in dms + gridrules + conns + aliases,
                self.tech.rules
            )
        )

        return s

    def _s_extract(self):
        s = dedent(f"""
            # Autogenerated file. Changes will be overwritten

            source_file = ENV["SOURCE_FILE"]
            cell_name = ENV["CELL_NAME"]
            if cell_name.empty?
                source(source_file)
            else
                source(source_file, cell_name)
            end
            target_netlist(ENV["SPICE_FILE"], write_spice(true, true))

        """[1:])
        s += self._s_extractrules()

        return s

    def _ly_extract(self):
        ly_extract = ET.Element("klayout-macro")
        ET.SubElement(ly_extract, "description")
        ET.SubElement(ly_extract, "version")
        ET.SubElement(ly_extract, "category").text = "lvs"
        ET.SubElement(ly_extract, "prolog")
        ET.SubElement(ly_extract, "epilog")
        ET.SubElement(ly_extract, "doc")
        ET.SubElement(ly_extract, "autorun").text = "false"
        ET.SubElement(ly_extract, "autorun-early").text = "false"
        ET.SubElement(ly_extract, "shortcut")
        ET.SubElement(ly_extract, "show-in-menu").text = "true"
        ET.SubElement(ly_extract, "group-name").text = "lvs_scripts"
        ET.SubElement(ly_extract, "menu-path").text = "tools_menu.lvs.end"
        ET.SubElement(ly_extract, "interpreter").text = "dsl"
        ET.SubElement(ly_extract, "dsl-interpreter-name").text = "lvs-dsl-xml"
        s = dedent(f"""
            # Autogenerated file. Changes will be overwritten

            report_netlist

        """[1:])
        s += self._s_extractrules()
        ET.SubElement(ly_extract, "text").text = s
        
        return ly_extract

    def _s_lvs(self):
        s = dedent(f"""
            # Autogenerated file. Changes will be overwritten

            source_file = ENV["SOURCE_FILE"]
            cell_name = ENV["CELL_NAME"]
            if cell_name.empty?
                source(source_file)
            else
                source(source_file, cell_name)
            end
            schematic(ENV["SPICE_FILE"])
            report_lvs(ENV["REPORT_FILE"])

        """[1:])
        s += self._s_extractrules() + dedent(f"""
            align
            ok = compare
            if ok then
                print("LVS OK\\n")
            else
                abort "LVS Failed!"
            end
        """)

        return s

    def _s_extractrules(self):
        # TODO: bug report for failing LVS on hierarchical LVS and diodes
        s = "flat\n\n# Define layers\n"
        assert isinstance(self.tech.rules, _rle.Rules), "Internal error"
        dms = tuple(self.tech.rules.__iter_type__(_msk.DesignMask))
        s += "".join(_str_designmask(dm, gds_layers=self.gds_layers) for dm in dms)

        s += self._s_aliases()[0] # aliases is ignored

        s += "\n# Connectivity\n"
        conns = tuple(self.tech.rules.__iter_type__(_msk.Connect))
        s += "".join(_rule_conv(conn) for conn in conns)

        s += "\n# Resistors\n"
        resistors = tuple(self.tech.primitives.__iter_type__(_prm.Resistor))
        s += "".join(
            _str_lvsresistor(res, params=self.prims_spiceparams[res])
            for res in resistors
        )

        s += "\n# Diodes\n"
        diodes = tuple(self.tech.primitives.__iter_type__(_prm.Diode))
        s += "".join(
            _str_lvsdiode(self.tech, diode, self.prims_spiceparams[diode])
            for diode in diodes
        )

        s += "\n# Transistors\n"
        mosfets = tuple(self.tech.primitives.__iter_type__(_prm.MOSFET))
        s += "".join(
            _str_lvsmosfet(self.tech, mosfet, self.prims_spiceparams[mosfet])
            for mosfet in mosfets
        )

        s += "\nnetlist\n"

        return s

    def _ly_tech(self, *, layerprops: Optional[str]):
        lyt = ET.Element("technology")
        ET.SubElement(lyt, "name").text = self.export_name
        ET.SubElement(lyt, "description").text = (
            f"KLayout generated from {self.tech.name} PDKMaster technology"
        )
        ET.SubElement(lyt, "group")
        ET.SubElement(lyt, "dbu").text = f"{self.tech.dbu}"
        se = ET.SubElement(lyt, "layer-properties_file")
        if layerprops is not None:
            se.text = layerprops
        ET.SubElement(lyt, "add-other-layers").text = "true"
        ropts = ET.SubElement(lyt, "reader-options")
        roptscom = ET.SubElement(ropts, "common")
        ET.SubElement(roptscom, "create-other-layers").text = "true"
        def s_gds_layer(m: _msk.DesignMask):
            try:
                l = self.gds_layers[m.name]
            except KeyError: # pragma: no cover
                raise ValueError(
                    f"No gds_layer provided for mask '{m.name}'"
                )
            if l is None:
                return None
            elif isinstance(l, int):
                return f"{l}/0"
            else:
                assert isinstance(l, tuple)
                return f"{l[0]}/{l[1]}"
        s_map = ";".join(
            f"'{s_gds_layer(mask)} : {mask.name}'"
            for mask in self.tech.designmasks if s_gds_layer(mask) is not None
        )
        ET.SubElement(roptscom, "layer-map").text = f"layer_map({s_map})"
        ET.SubElement(lyt, "writer-options")
        ET.SubElement(lyt, "connectivity")

        return lyt

    def _s_aliases(self) -> Tuple[str, Tuple[_msk.MaskAliasT, ...]]:
        assert isinstance(self.tech.rules, _rle.Rules), "Internal error"

        # Help function to order mask aliases so that an alias is output before it is used in
        # another alias
        def _recurs_alias_order(mask: _msk.MaskT, added: Set[_msk._MaskAlias]) -> Iterable[_msk._MaskAlias]:
            for mask2 in mask.submasks:
                if (mask != mask2) and (mask2 not in added):
                    yield from _recurs_alias_order(mask2, added)
            if (mask not in added) and (isinstance(mask, _msk._MaskAlias)):
                added.add(mask)
                yield mask

        aliases = tuple(self.tech.rules.__iter_type__(_msk._MaskAlias))
        added: Set[_msk._MaskAlias] = set()
        s = "\n# Derived layers\n" + "".join(
            "".join(_rule_conv(alias2) for alias2 in _recurs_alias_order(alias, added))
            for alias in aliases
        )
        assert added == set(aliases), "Internal error"

        return s, aliases


class _ShapeExporter(_dsp.ShapeDispatcher):
    """Converts a _geo,_Shape object to KLayout database object"""
    def __init__(self, *, export_fullshape: bool):
        self._mps_exported: Optional[Set[_geo.MultiPartShape]]
        self._mps_exported = set() if export_fullshape else None

    def _pointsshapes(self, shape: _geo._Shape) -> Iterable[Any]:
        # Helper to convert the individual pointsshapes
        for pointshape in shape.pointsshapes:
            conv = self(pointshape)
            assert not _util.is_iterable(conv), "Internal error: unsupported"
            yield conv

    def _Shape(self, shape: _geo._Shape): # pragma: no cover
        raise ValueError(f"Unsupported object of type {shape.__class__.__name__}")

    def Point(self, point: _geo.Point) -> pya.DPoint:
        return pya.DPoint(point.x, point.y)

    def Line(self, line: _geo.Line) -> pya.DPath:
        # We represent a Line by a path with zero width
        points = (self.Point(line.point1), self.Point(line.point2))
        return pya.DPath(points, 0.0)

    def Polygon(self, polygon: _geo.Polygon, **_) -> pya.DSimplePolygon:
        # In PDKMaster polygon needs last point to be same as first point;
        # in klayout this is not the case.
        points = tuple(self.Point(point) for point in tuple(polygon.points)[:-1])
        return pya.DSimplePolygon(points)

    def Rect(self, rect: _geo.Rect) -> pya.DBox:
        return pya.DBox(rect.left, rect.bottom, rect.right, rect.top)

    def RectRing(self, rs: _geo.RectRing) -> Iterable[Any]:
        # TODO: Can repetition information be retained in KLayout ?
        return self._pointsshapes(rs)

    def Label(self, label: _geo.Label) -> pya.DText:
        return pya.DText(label.text, label.origin.x, label.origin.y)

    def MultiPartShape(self, mps: _geo.MultiPartShape):
        if self._mps_exported is None:
            return self(mps.fullshape)
        else:
            if mps in self._mps_exported:
                return None
            else:
                self._mps_exported.add(mps)
                return self(mps.fullshape)

    def MultiPartShape__Part(self, part: _geo.MultiPartShape._Part):
        if self._mps_exported is None:
            return self(part.partshape)
        else:
            return self(part.multipartshape)

    def MultiShape(self, ms: _geo.MultiShape) -> Iterable[Any]:
        for shape in ms.shapes:
            conv = self(shape)
            if _util.is_iterable(conv):
                yield from conv
            else:
                yield conv

    def RepeatedShape(self, rs: _geo.RepeatedShape) -> Iterable[Any]:
        # TODO: Can repetition information be retained in KLayout ?
        return self._pointsshapes(rs)

    # TODO: Does KLayout allow more efficient array representation
    # ArrayShape -> RepeatedShape


class _MaskLayerDict(Dict[_msk.DesignMask, int]):
    def __init__(self, *, layout: pya.Layout, gds_layers: GDSLayerSpecDict):
        self._layout = layout
        self._gds_layers = gds_layers

    def __getitem__(self, mask: _msk.DesignMask) -> int:
        if mask not in self:
            layer = self._gds_layers[mask.name]
            if isinstance(layer, tuple):
                layer, datatype = layer
            else:
                datatype = 0
            assert layer is not None
            self[mask] = self._layout.layer(layer, datatype, mask.name)
        return super().__getitem__(mask)


_rotation_to_rot_mirr: Dict[_geo.Rotation, Tuple[int, bool]] = {
    _geo.Rotation.No: (0, False),
    _geo.Rotation.R90: (1, False),
    _geo.Rotation.R180: (2, False),
    _geo.Rotation.R270: (3, False),
    _geo.Rotation.MX: (0, True),
    _geo.Rotation.MX90:(1, True),
    _geo.Rotation.MY: (2, True),
    _geo.Rotation.MY90: (3, True),
}


class _LayoutExporter:
    def __init__(self):
        self._clear()

    def _clear(self):
        self.layout = None
        self.layerdict = None
        self.textlayerdict = None
        self.cell_lookup: Dict[str, Tuple[Optional[_cell.Cell], pya.Cell]] = {}
        self.cells_todo: Set[_cell.Cell] = set()
        self.cells_done: Set[_cell.Cell] = set()
        self.cell = None
        self.shapeexporter = None
        self.pinmasks: Optional[Tuple[_msk.MaskT, ...]] = None

    def __call__(self, *,
        obj: Union[_geo.MaskShape, _geo.MaskShapes, _lay.LayoutT, _lbry.Library],
        pya_layout: Optional[pya.Layout]=None,
        gds_layers: GDSLayerSpecDict,
        textgds_layers: Optional[GDSLayerSpecDict]=None,
        cell_name: Optional[str], pya_cell: Optional[pya.Cell],
        merge: bool, add_pin_label: bool, dbu: float=0.001,
    ) -> pya.Layout:
        if pya_layout is None:
            pya_layout = pya.Layout() if pya_cell is None else pya_cell.layout()
        self.layout = pya_layout
        pya_layout.dbu = dbu
        self.layerdict = _MaskLayerDict(layout=pya_layout, gds_layers=gds_layers)
        if textgds_layers is not None:
            self.textlayerdict = _MaskLayerDict(layout=pya_layout, gds_layers=textgds_layers)
        self.shapeexporter = _ShapeExporter(export_fullshape=True)

        if isinstance(obj, _lbry.Library):
            # A cell will be created in add() function below for each cell of the library
            if cell_name is not None:
                raise TypeError("cell_name may not be specified when exporting a library")
            if pya_cell is not None:
                raise TypeError("pya_cell may not be specified when exporting a library")
        else:
            if cell_name is None:
                cell_name = "anon"
            if pya_cell is None:
                pya_cell = self._create_layout(cell_name)
            else:
                self.cell_lookup[cell_name] = (None, pya_cell)
            self.cell = pya_cell

        # Define local function to allow recursive calling
        self._add(obj, add_pin_label=add_pin_label, net=None)
        while len(self.cells_todo) > 0:
            cell = self.cells_todo.pop()
            self.cells_done.add(cell)
            self.cell = self.cell_lookup[cell.name][1]
            # Don't reuse ShapeExporter between cells, otherwise MultiPartShapes
            # can be wrongly marked as written when they are not.
            self.shapeexporter = _ShapeExporter(export_fullshape=True)
            self._add(cell.layout, add_pin_label=add_pin_label, net=None)

        if merge:
            for cell in pya_layout.each_cell():
                for layer_idx in self.layerdict.values():
                    # https://www.klayout.de/forum/discussion/697/merge-all-shapes-of-a-certain-layer-of-a-cell
                    old_shapes = cell.shapes(layer_idx)
                    region = pya.Region(old_shapes)
                    region.merge()

                    new_shapes = pya.Shapes()
                    new_shapes.insert(region)
                    # Copy texts over to avoid they are lost
                    for shape in old_shapes.each():
                        if shape.is_text():
                            new_shapes.insert(shape)

                    cell.shapes(layer_idx).assign(new_shapes)

        self._clear()
        return pya_layout

    def _create_layout(self, name: str):
        assert self.layout is not None
        assert len(self.cell_lookup) == 0
        cell = self.layout.create_cell(name)
        self.cell_lookup[name] = (None, cell)

        return cell

    def _register_cell(self, cell: _cell.Cell):
        assert self.layout is not None
        assert self.cell_lookup is not None

        name = cell.name
        if name in self.cell_lookup:
            # Check if no two cells from different libraries with the same name are used
            if self.cell_lookup[name][0] != cell: # pragma: no cover
                raise ValueError(
                    "Export of hierarchy with two cells from different libraries with same name not supported"
                )
        else:
            self.cell_lookup[name] = (cell, self.layout.create_cell(name))
            if cell not in self.cells_done:
                self.cells_todo.add(cell)
        return self.cell_lookup[name][1]

    def _add(self,
        o: Union[_geo.MaskShape, _geo.MaskShapes, _lay.LayoutT, _cell.Cell, _lbry.Library],
        add_pin_label: bool, net: Optional[_net.NetT],
    ) -> None:
        assert self.shapeexporter is not None
        if isinstance(o, _geo.MaskShape):
            assert (self.cell is not None) and (self.layerdict is not None)
            layer = self.layerdict[o.mask]
            shapes = self.cell.shapes(layer)
            exp = self.shapeexporter(o.shape)
            if _util.is_iterable(exp):
                for s in exp:
                    # s is None if MultiPartShape is already added
                    if s is not None:
                        shapes.insert(s)
            else:
                # exp is None if MultiPartShape has already been converted
                if exp is not None:
                    shapes.insert(exp)
            if add_pin_label:
                assert self.pinmasks is not None
                if o.mask in self.pinmasks:
                    if self.textlayerdict is None:
                        text_shapes = shapes
                    else:
                        try:
                            layer = self.textlayerdict[o.mask]
                        except:
                            text_shapes = shapes
                        else:
                            text_shapes = self.cell.shapes(layer)
                    assert net is not None
                    for ps in o.shape.pointsshapes:
                        if isinstance(ps, _geo.Rect):
                            point = ps.center
                        else:
                            point = _util.get_first_of(ps.points)
                        text_shapes.insert(pya.DText(net.name, point.x, point.y))
        elif isinstance(o, _geo.MaskShapes):
            for ms in o:
                self._add(ms, add_pin_label=add_pin_label, net=net)
        elif isinstance(o, _lay.LayoutT):
            prims = o.fab.tech.primitives
            pinmasks: List[_msk.DesignMask] = []
            for prim in prims:
                try:
                    pin: _prm.Marker = prim.pin # type: ignore
                except AttributeError:
                    pass
                else:
                    pinmasks.append(pin.mask)
            self.pinmasks = tuple(pinmasks)
            for sl in o._sublayouts:
                if isinstance(sl, _laylay._MaskShapesSubLayout):
                    self._add(sl.shapes, add_pin_label=add_pin_label, net=sl.net)
                elif isinstance(sl, _laylay._InstanceSubLayout):
                    assert self.cell is not None
                    instcell = self._register_cell(sl.inst.cell)
                    rot, mirr = _rotation_to_rot_mirr[sl.rotation]
                    dtrans = pya.DTrans(rot, mirr, sl.origin.x, sl.origin.y)
                    self.cell.insert(pya.DCellInstArray(instcell.cell_index(), dtrans))
                else: # pragma: no cover
                    raise RuntimeError(
                        "Internal error: unsupported",
                    )
        elif isinstance(o, _cell.Cell):
            assert net is None
            # Register cell to be exported
            self._register_cell(o)
            # Make use of self.cell after this an error
            self.cell = None
        elif isinstance(o, _lbry.Library):
            # Initialize list of cells to tape-out, each of the cells will be
            # added in a loop below this function.
            assert net is None
            self.cells_todo.update(o.cells)
            # Register all cells to be exported
            for lbrycell in o.cells:
                self._register_cell(lbrycell)
            # Make use of self.cell after this an error
            self.cell = None
        else:
            raise TypeError(f"No support for exporting a '{type(o)}' object")


@overload
def export2db(
    obj: _geo._Shape, *,
    pya_layout: Optional[pya.Layout]=None,
    export_fullshape: Optional[bool]=None,
    add_pin_label: bool=False,
    gds_layers: None=None,
    textgds_layers: None=None,
    cell_name: Optional[str]=None, pya_cell: Optional[pya.Cell]=None,
    merge: bool=False,
) -> Any:
    ... # pragma: no cover
@overload
def export2db(
    obj: Union[_geo.MaskShape, _geo.MaskShapes, _lay.LayoutT, _lbry.Library], *,
    pya_layout: Optional[pya.Layout]=None,
    export_fullshape: None=None,
    add_pin_label: bool=False,
    gds_layers: GDSLayerSpecDict,
    textgds_layers: Optional[GDSLayerSpecDict]=None,
    cell_name: Optional[str]=None, pya_cell: Optional[pya.Cell]=None,
    merge: bool=False,
) -> pya.Layout:
    ... # pragma: no cover
def export2db(
    obj: Union[_geo._Shape, _geo.MaskShape, _geo.MaskShapes, _lay.LayoutT, _lbry.Library], *,
    pya_layout: Optional[pya.Layout]=None,
    export_fullshape: Optional[bool]=None, add_pin_label: bool=False,
    gds_layers: Optional[GDSLayerSpecDict]=None,
    textgds_layers: Optional[GDSLayerSpecDict]=None,
    cell_name: Optional[str]=None, pya_cell: Optional[pya.Cell]=None,
    merge: bool=False,
):
    """This function allows to export PDKMaster geometry/layout objects
    to a klayout Layout object

    Arguments:
        obj: This is the object to export. There are two different call types.
            1) a _Shape geometry object without mask provided
            2) a MaskShape geometry or an object that contains maskshapes.
        pya_layout: Optional existing KLayout layout to use for export.
            If not specified a fresh layout will be created.
        export_fullshape: only to be specified when obj is a _Shape object.
            If `True` the full MultiPartShape shape will be exported when a
            MultiPartShape._Part object is met. It defaults to `False`
        add_pin_label: If `True` a label will exported on top of layers that are pin
            layers of one of the technology's MetalWire primitives.
        gds_layers: Has to be specified when `obj` is a MaskShape or a collection of them
            and should not be provided otherwise.
            It contains the lookup table to get the corresponding KLayout layer information
            for PDKMaster _DesignMask objects.
        textgds_layers: Optional for when `obj` is a MaskShape.
            It's an extra lookup table for the layer to generate text for pins in.
            If no value is found or textgds_layers is not specified the layer from
            gds_layers will be used.
        cell_name: Only to be provided when `obj` is a MaskShape or a collection of them but
            not a Library.
            If specified the name of the cell in which the MaskShape(s) will be exported.
            By default 'anon' will be used.
        pya_cell: Optional KLayout cell to export shapes into.
            May not be specified when exporting a library.
            If not specified otherwise, a cell with name given by cell_name will be created.
        merge: Wether to merge the exported shapes or not.

    Returns:
        An equivalent KLayout database object if obj is a _Shape geometry or a KLayout
        Layout object when obj is a MaskShape or a collection of MaskShapes. If obj is
        a Library a Cell will be added for each _Cell in the Library. If there are
        cell instances in the PDKMaster _Layout object these cells will also be exported
        to the output KLayout Layout object as a cell even if it is from another PDKMaster
        Library. An exception will be generated when two instances need to be exported to
        the same cell name but in a different Library.
    """
    # TODO: Provide facility to also export netlist information

    if isinstance(obj, _geo._Shape):
        assert (gds_layers is None) and (cell_name is None) and (not add_pin_label)
        if export_fullshape is None:
            export_fullshape = False
        _exporter = _ShapeExporter(export_fullshape=export_fullshape)
        return _exporter(obj)
    else:
        assert (export_fullshape is None) and (gds_layers is not None)
        return _LayoutExporter()(
            obj=obj, pya_layout=pya_layout, gds_layers=gds_layers, textgds_layers=textgds_layers,
            cell_name=cell_name, pya_cell=pya_cell, merge=merge, add_pin_label=add_pin_label,
        )
