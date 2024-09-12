# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from typing import Iterable, Union, Optional, Any, cast, overload

from ...technology import (
    geometry as _geo, property_ as _prp, net as _net, primitive as _prm,
    technology_ as _tch,
)
from .. import circuit as _ckt

from .layout_ import _InstanceSubLayout, _SubLayouts, _Layout, LayoutT
# also imports at end of file to avoid circular import problems


__all__ = ["MOSFETInstSpec", "CircuitLayouterT"]


class MOSFETInstSpec: # pragma: no cover
    """Class that provided the spec for the string of transistors generation.

    Used by `_CircuitLayouter.transistors_layout()`

    Arguments:
        inst: the transistor instance to generate layout for in the string.
            A ValueError will be raised if it is not a MOSFET instance.
            The inst parameters like l, w, etc with determine the layout of the transistor.
        contact_left, contact_right: whether to place contacts left or right from the
            transistor. This value needs to be the same between two neighbours.

    API Notes:
        This class is deprecated and will be removed before v1.0.0. See also
        https://gitlab.com/Chips4Makers/PDKMaster/-/issues/25
    """
    def __init__(self, *,
        inst: _ckt._PrimitiveInstance,
        contact_left: Optional[_prm.Via], contact_right: Optional[_prm.Via],
    ):
        self._inst = inst
        self._contact_left = contact_left
        self._contact_right = contact_right

        if not isinstance(inst.prim, _prm.MOSFET):
            raise ValueError(f"inst is not a MOSFET instance")
        mosfet = inst.prim

        if contact_left is not None:
            if len(contact_left.top) != 1:
                raise NotImplementedError(
                    f"Multiple top layers for Via '{contact_left.name}'",
                )
        if contact_right is not None:
            if len(contact_right.top) != 1:
                raise NotImplementedError(
                    f"Multiple top layers for Via '{contact_right.name}'",
                )

    @property
    def inst(self) -> _ckt._PrimitiveInstance:
        return self._inst
    @property
    def contact_left(self) -> Optional[_prm.Via]:
        return self._contact_left
    @property
    def contact_right(self) -> Optional[_prm.Via]:
        return self._contact_right


class _CircuitLayouter: # pragma: no cover
    """_CircuitLayouter is deprecated class and undocumented.

    see https://gitlab.com/Chips4Makers/PDKMaster/-/issues/25 for development of
    replacement.

    API Notes:
        This class is deprecated and user code will fail in future.
    """
    def __init__(self, *,
        fab: "LayoutFactory", circuit: _ckt._Circuit, boundary: Optional[_geo._Rectangular]
    ):
        self.fab = fab
        self.circuit = circuit

        self.layout = l = fab.new_layout()
        l.boundary = boundary

    @property
    def tech(self) -> _tch.Technology:
        return self.circuit.fab.tech

    def inst_layout(self, *,
        inst: _ckt._Instance, layoutname: Optional[str]=None,
        rotation: _geo.Rotation=_geo.Rotation.R0,
        **layout_inst_params: Any,
    ) -> LayoutT:
        if isinstance(inst, _ckt._PrimitiveInstance):
            notfound = []
            portnets = {}
            for port in inst.ports:
                try:
                    net = self.circuit.net_lookup(port=port)
                except ValueError:
                    notfound.append(port.name)
                else:
                    portnets[port.name] = net
            if len(notfound) > 0:
                raise ValueError(
                    f"Unconnected port(s) {notfound}"
                    f" for inst '{inst.name}' of primitive '{inst.prim.name}'"
                )
            l = self.fab.layout_primitive(
                prim=inst.prim, portnets=portnets,
                **inst.params, **layout_inst_params,
            )
            if rotation != _geo.Rotation.R0:
                l.rotate(rotation=rotation)
            return l
        elif isinstance(inst, _ckt._CellInstance):
            # TODO: propoer checking of nets for instance
            layout = None
            if layoutname is None:
                try:
                    circuitname = cast(Any, inst).circuitname
                    layout = inst.cell._layouts[circuitname].layout
                except:
                    layout = inst.cell.layout
                else:
                    layoutname = circuitname
            else:
                if not isinstance(layoutname, str):
                    raise TypeError(
                        "layoutname has to be 'None' or a string, not of type"
                        f" '{type(layoutname)}'"
                    )
                layout = inst.cell._layouts[layoutname].layout

            bb = None if layout.boundary is None else rotation*layout.boundary
            return _Layout(
                fab=self.fab,
                sublayouts=_SubLayouts(_InstanceSubLayout(
                    inst=inst, origin=_geo.origin, layoutname=layoutname,
                    rotation=rotation,
                )),
                boundary=bb,
            )
        else:
            raise AssertionError("Internal error")

    def wire_layout(self, *,
        net: _ckt._CircuitNet, wire: _prm.PrimitiveT, **wire_params,
    ) -> LayoutT:
        if net not in self.circuit.nets:
            raise ValueError(
                f"net '{net.name}' is not a net of circuit '{self.circuit.name}'"
            )
        if not (
            hasattr(wire, "ports")
            and (len(wire.ports) == 1)
            and (wire.ports[0].name == "conn")
        ):
            raise TypeError(
                f"Wire '{wire.name}' does not have exactly one port named 'conn'"
            )

        return self.fab.layout_primitive(
            wire, portnets={"conn": net}, **wire_params,
        )

    def transistors_layout(self, *,
        trans_specs: Iterable[MOSFETInstSpec]
    ) -> LayoutT:
        """This method allows to generate a string of transistors.

        Arguments:
            trans_specs: the list of the spec for the transistors to generate. A
                `MOSFETInstSpec` object needs to be provided for each transistor of the
                striog. For more information refer to the `MOSFETInstSpec` reference.
                Some compatibility checks are done on the specification between the right
                specifation of a spec and the left specification of the next. Currently it
                is checked that whether to generata a contact is the same and if the active
                layer between the two transistors is the same.

        Results:
            The string of transistor according to the provided specs from left to right.
        """
        specs = tuple(trans_specs)

        # Check consistency of the specification
        for i, spec in enumerate(specs[:-1]):
            next_spec = specs[i+1]
            mosfet = cast(_prm.MOSFET, spec.inst.prim)
            next_mosfet = cast(_prm.MOSFET, next_spec.inst.prim)

            if spec.contact_right != next_spec.contact_left:
                raise ValueError(
                    f"Contact specification mismatch between transistor spec {i} and {i+1}",
                )
            if mosfet.gate.active != next_mosfet.gate.active:
                raise ValueError(
                    f"Active specification mismatch between transistor spec {i} and {i+1}",
                )

        # Create the layout

        layout = self.fab.new_layout()
        x = 0.0

        spec = None
        mosfet = None
        active = None
        oxide = None
        ox_enc = None
        bottom_enc = ()
        well_args = {}
        for i, spec in enumerate(specs):
            prev_spec = specs[i - 1] if (i > 0) else None
            next_spec = specs[i + 1] if (i < (len(specs) - 1)) else None
            mosfet = cast(_prm.MOSFET, spec.inst.prim)
            gate = mosfet.gate
            active = gate.active
            oxide = gate.oxide

            # First generate, so the port net checks are run now.
            l_trans = self.inst_layout(inst=spec.inst)

            # For contacts also draw implant around bottom,
            # extend top and bottom enclosure to use the gate enclosure
            def comb_enc(impl):
                assert active is not None,"Internal error"
                assert mosfet is not None, "Internal error"

                idx = active.implant.index(impl)
                min_enc = active.min_implant_enclosure[idx]
                idx = mosfet.implant.index(impl)
                gate_enc = mosfet.min_gateimplant_enclosure[idx]
                if (gate_enc.second + _geo.epsilon) > min_enc.max():
                    return _prp.Enclosure((min_enc.min(), gate_enc.second))
                else:
                    return _prp.Enclosure((min_enc.max(), gate_enc.second))

            bottom_enc = tuple(comb_enc(impl) for impl in mosfet.implant)

            if oxide is None:
                ox_enc = None
            else:
                idx = active.oxide.index(oxide)
                ox_enc = gate.min_gateoxide_enclosure
                min_enc = active.min_oxide_enclosure[idx]
                if ox_enc is None:
                    ox_enc = min_enc
                elif min_enc is not None:
                    ox_enc = _prp.Enclosure((min_enc.min(), ox_enc.second))

            # Draw left sd
            if spec.contact_left is not None:
                w = spec.inst.params["w"]
                if prev_spec is not None:
                    w = min(w, prev_spec.inst.params["w"])
                if mosfet.well is None:
                    well_args = {}
                else:
                    well_args = {
                        "bottom_well": mosfet.well,
                        "well_net": spec.inst.ports["bulk"],
                    }
                l = self.wire_layout(
                    wire=spec.contact_left,
                    net=self.circuit.net_lookup(port=spec.inst.ports["sourcedrain1"]),
                    bottom_height=w, bottom=active,
                    bottom_implant=mosfet.implant, bottom_implant_enclosure=bottom_enc,
                    bottom_oxide=oxide, bottom_oxide_enclosure=ox_enc,
                    **well_args,
                ).moved(dxy=_geo.Point(x=x, y=0.0))
                layout += l

                spc = cast(_prm.MOSFET, spec.inst.prim).computed.min_contactgate_space
                x += (
                    0.5*spec.contact_left.width + spc + 0.5*spec.inst.params["l"]
                )
            else:
                gate_space = cast(_prm.MOSFET, spec.inst.prim).computed.min_gate_space
                if prev_spec is not None:
                    gate_space = max(
                        gate_space,
                        cast(_prm.MOSFET, prev_spec.inst.prim).computed.min_gate_space,
                    )
                x += 0.5*gate_space + 0.5*spec.inst.params["l"]

            # Remember trans position
            l_trans.move(dxy=_geo.Point(x=x, y=0.0))
            layout += l_trans

            if spec.contact_right is not None:
                spc = cast(_prm.MOSFET, spec.inst.prim).computed.min_contactgate_space
                x += (
                    0.5*spec.inst.params["l"] + spc + 0.5*spec.contact_right.width
                )
            else:
                gate_space = cast(_prm.MOSFET, spec.inst.prim).computed.min_gate_space
                if next_spec is not None:
                    gate_space = max(
                        gate_space,
                        cast(_prm.MOSFET, next_spec.inst.prim).computed.min_gate_space,
                    )
                x += 0.5*spec.inst.params["l"] + 0.5*gate_space
        assert spec is not None
        assert mosfet is not None
        assert active is not None

        # Draw last contact if needed
        # spec and other variables are already set from last run of previous for loop
        if spec.contact_right is not None:
            l = self.wire_layout(
                wire=spec.contact_right,
                net=self.circuit.net_lookup(port=spec.inst.ports["sourcedrain2"]),
                bottom_height=spec.inst.params["w"], bottom=active,
                bottom_implant=mosfet.implant, bottom_implant_enclosure=bottom_enc,
                bottom_oxide=oxide, bottom_oxide_enclosure=ox_enc,
                **well_args,
            ).moved(dxy=_geo.Point(x=x, y=0.0))
            layout += l

        return layout

    @overload
    def place(self, object_: _ckt._Instance, *,
        origin: _geo.Point, x: None=None, y: None=None,
        layoutname: Optional[str]=None, rotation: _geo.Rotation=_geo.Rotation.R0,
        **layout_params: Any,
    ) -> LayoutT:
        ...
    @overload
    def place(self, object_: _ckt._Instance, *,
        origin: None=None, x: float=0.0, y: float=0.0,
        layoutname: Optional[str]=None, rotation: _geo.Rotation=_geo.Rotation.R0,
        **layout_params: Any,
    ) -> LayoutT:
        ...
    @overload
    def place(self, object_: LayoutT, *,
        origin: _geo.Point, x: None=None, y: None=None,
        layoutname: Optional[str]=None, rotation: _geo.Rotation=_geo.Rotation.R0,
    ) -> LayoutT:
        ...
    @overload
    def place(self, object_: LayoutT, *,
        origin: None=None, x: float=0.0, y: float=0.0,
        layoutname: Optional[str]=None, rotation: _geo.Rotation=_geo.Rotation.R0,
    ) -> LayoutT:
        ...
    def place(self, object_, *,
        origin=None, x: Optional[float]=None, y: Optional[float]=None,
        layoutname: Optional[str]=None, rotation: _geo.Rotation=_geo.Rotation.R0,
        **layout_params,
    ) -> LayoutT:
        # Translate possible x/y specification to origin
        if origin is None:
            if x is None:
                x = 0.0
            if y is None:
                y = 0.0
            origin = _geo.Point(x=x, y=y)

        if isinstance(object_, _ckt._Instance):
            inst = object_
            if inst not in self.circuit.instances:
                raise ValueError(
                    f"inst '{inst.name}' is not part of circuit '{self.circuit.name}'"
                )

            if isinstance(inst, _ckt._PrimitiveInstance):
                def _portnets():
                    for net in self.circuit.nets:
                        for port in net.childports:
                            if (inst == port.inst):
                                yield (port.name, net)
                portnets = dict(_portnets())
                portnames = set(inst.ports.keys())
                portnetnames = set(portnets.keys())
                if not (portnames == portnetnames):
                    raise ValueError(
                        f"Unconnected port(s) {portnames - portnetnames}"
                        f" for inst '{inst.name}' of primitive '{inst.prim.name}'"
                    )
                return self.layout.add_primitive(
                    prim=inst.prim, origin=origin, rotation=rotation,
                    portnets=portnets, **inst.params, **layout_params,
                )
            elif isinstance(inst, _ckt._CellInstance):
                assert len(layout_params) == 0
                # TODO: propoer checking of nets for instance
                if (
                    (layoutname is None)
                    and inst.circuitname is not None
                    and (inst.circuitname in inst.cell._layouts.keys())
                ):
                    layoutname = inst.circuitname
                sl = _InstanceSubLayout(
                    inst=inst, origin=origin, layoutname=layoutname, rotation=rotation,
                )
                self.layout += sl

                return _Layout(
                    fab=self.fab, sublayouts=_SubLayouts(sl), boundary=sl.boundary,
                )
            else:
                raise RuntimeError("Internal error: unsupported instance type")
        elif isinstance(object_, LayoutT):
            layout = object_.rotated(rotation=rotation).moved(dxy=origin)
            self.layout += layout
            return layout
        else:
            raise AssertionError("Internal error")

    @overload
    def add_wire(self, *,
        net: _net.NetT, wire: _prm.ConductorT, shape: Optional[_geo._Shape]=None,
        origin: _geo.Point, x: None=None, y: None=None,
        **wire_params,
    ) -> LayoutT:
        ...
    @overload
    def add_wire(self, *,
        net: _net.NetT, wire: _prm.ConductorT, shape: Optional[_geo._Shape]=None,
        origin: None=None, x: Optional[float]=None, y: Optional[float]=None,
        **wire_params,
    ) -> LayoutT:
        ...
    def add_wire(self, *,
        net: _net.NetT, wire: _prm.ConductorT, shape: Optional[_geo._Shape]=None,
        origin: Optional[_geo.Point]=None, x: Optional[float]=None, y: Optional[float]=None,
        **wire_params,
    ) -> LayoutT:
        if net not in self.circuit.nets:
            raise ValueError(
                f"net '{net.name}' is not a net of circuit '{self.circuit.name}'"
            )

        if origin is None:
            if x is None:
                x = 0.0
            if y is None:
                y = 0.0
            origin = _geo.Point(x=x, y=y)

        if isinstance(wire, _prm.Via):
            if shape is not None:
                raise ValueError(
                    "shape paramter may not be provided for a Via object"
                )
            return self._add_viawire(net=net, via=wire, origin=origin, **wire_params)

        layout = self.layout

        if (shape is None) or isinstance(shape, _geo.Rect):
            if shape is not None:
                # TODO: Add support in _PrimitiveLayouter for shape argument,
                # e.g. non-rectangular shapes
                origin += shape.center
                wire_params.update({
                    "width": shape.width, "height": shape.height,
                })
            return layout.add_primitive(
                portnets={"conn": net}, prim=wire, origin=origin,
                **wire_params,
            )
        else: # (shape is not None) and not a Rect
            pin = wire_params.pop("pin", None)
            if len(wire_params) != 0:
                raise TypeError(
                    f"params {wire_params.keys()} not supported for shape not of type 'Rect'",
                )
            l = self.fab.new_layout()
            layout.add_shape(net=net, layer=wire, shape=shape)
            l.add_shape(net=net, layer=wire, shape=shape)
            if pin is not None:
                layout.add_shape(net=net, layer=pin, shape=shape)
                l.add_shape(net=net, layer=pin, shape=shape)
            return l

    def _add_viawire(self, *,
        net: _net.NetT, via: _prm.Via, origin: _geo.Point, **via_params,
    ) -> LayoutT:
        # For a Via allow to specify bottom and/or top edges
        has_rows = "rows" in via_params
        has_columns = "columns" in via_params

        def pop_param(name: str, type_: type, *, keep: bool=False):
            if keep:
                param = via_params.get(name, None)
            else:
                param = via_params.pop(name, None)
            return cast(Optional[type_], param)

        # Get bottom paramter specification
        bottom_left = pop_param("bottom_left", float)
        bottom_bottom = pop_param("bottom_bottom", float)
        bottom_right = pop_param("bottom_right", float)
        bottom_top = pop_param("bottom_top", float)
        has_bottomedge = (
            (bottom_left is not None) or (bottom_bottom is not None)
            or (bottom_right is not None) or (bottom_top is not None)
        )

        bottom_shape = pop_param("bottom_shape", _geo._Shape)
        if bottom_shape is not None:
            if has_bottomedge:
                raise ValueError(
                    "Both bottom_shape and at least one of bottom_left, bottom_bottom"
                    ", bottom_rigth or bottom_top specified"
                )
            if not isinstance(bottom_shape, _geo.Rect):
                raise NotImplementedError(
                    f"bottom_shape not a 'Rect' but of type '{type(bottom_shape)}'"
                )

            bottom_left = bottom_shape.left
            bottom_bottom = bottom_shape.bottom
            bottom_right = bottom_shape.right
            bottom_top = bottom_shape.top
            has_bottomedge = True
        bottom_extra = pop_param(
            "bottom_extra", Iterable[_prm.DesignMaskPrimitiveT], keep=True,
        )
        if bottom_extra is None:
            bottom_extra = ()

        bottom = pop_param("bottom", _prm.ViaBottom, keep=True)
        if bottom is None:
            bottom = via.bottom[0]
        assert not isinstance(bottom, _prm.Resistor), "Unimplemented"

        bottom_enc = pop_param(
            "bottom_enclosure", Union[str, float, _prp.Enclosure], keep=True,
        )
        if isinstance(bottom_enc, float):
            bottom_enc = _prp.Enclosure(bottom_enc)
        if (bottom_enc is None) or isinstance(bottom_enc, str):
            idx = via.bottom.index(bottom)
            enc = via.min_bottom_enclosure[idx]
            if bottom_enc is None:
                bottom_enc = enc
            elif bottom_enc == "wide":
                bottom_enc = enc.wide()
            else:
                assert bottom_enc == "tall"
                bottom_enc = enc.tall()
        bottom_henc = bottom_enc.first
        bottom_venc = bottom_enc.second

        # Get bottom paramter specification
        top = pop_param("top", _prm.ViaBottom, keep=True)
        if top is None:
            top = via.top[0]
        assert not isinstance(top, _prm.Resistor), "Unimplemented"

        top_left = pop_param("top_left", float)
        top_bottom = pop_param("top_bottom", float)
        top_right = pop_param("top_right", float)
        top_top = pop_param("top_top", float)
        has_topedge = (
            (top_left is not None) or (top_bottom is not None)
            or (top_right is not None) or (top_top is not None)
        )

        top_shape = pop_param("top_shape", _geo._Shape)
        if top_shape is not None:
            if has_topedge:
                raise ValueError(
                    "Both top_shape and at least one of top_left, top_bottom"
                    ", top_rigth or top_top specified"
                )
            if not isinstance(top_shape, _geo.Rect):
                raise NotImplementedError(
                    f"top_shape not a 'Rect' but of type '{type(top_shape)}'"
                )

            top_left = top_shape.left
            top_bottom = top_shape.bottom
            top_right = top_shape.right
            top_top = top_shape.top
            has_topedge = True
        top_extra = pop_param(
            "top_extra", Iterable[_prm.DesignMaskPrimitiveT], keep=True,
        )
        if top_extra is None:
            top_extra = ()

        top_enc = pop_param(
            "top_enclosure", Union[str, float, _prp.Enclosure], keep=True,
        )
        if isinstance(top_enc, float):
            top_enc = _prp.Enclosure(top_enc)
        if (top_enc is None) or isinstance(top_enc, str):
            idx = via.top.index(top)
            enc = via.min_top_enclosure[idx]
            if top_enc is None:
                top_enc = enc
            elif top_enc == "wide":
                top_enc = enc.wide()
            else:
                assert top_enc == "tall"
                top_enc = enc.tall()
        top_henc = top_enc.first
        top_venc = top_enc.second

        if has_bottomedge or has_topedge:
            width = via.width
            space = pop_param("space", float, keep=True)
            if space is None:
                space = via.min_space
            pitch = width + space

            # Compute number of rows/columns and placement
            if bottom_left is not None:
                if top_left is not None:
                    via_left = max(bottom_left + bottom_henc, top_left + top_henc)
                else:
                    via_left = bottom_left + bottom_henc
            else:
                if top_left is not None:
                    via_left = top_left + top_henc
                else:
                    via_left = None
            if bottom_bottom is not None:
                if top_bottom is not None:
                    via_bottom = max(bottom_bottom + bottom_venc, top_bottom + top_venc)
                else:
                    via_bottom = bottom_bottom + bottom_venc
            else:
                if top_bottom is not None:
                    via_bottom = top_bottom + top_venc
                else:
                    via_bottom = None
            if bottom_right is not None:
                if top_right is not None:
                    via_right = min(bottom_right - bottom_henc, top_right - top_henc)
                else:
                    via_right = bottom_right - bottom_henc
            else:
                if top_right is not None:
                    via_right = top_right - top_henc
                else:
                    via_right = None
            if bottom_top is not None:
                if top_top is not None:
                    via_top = min(bottom_top - bottom_venc, top_top - top_venc)
                else:
                    via_top = bottom_top - bottom_venc
            else:
                if top_top is not None:
                    via_top = top_top - top_venc
                else:
                    via_top = None

            if (via_left is None) != (via_right is None):
                raise NotImplementedError(
                    "left or right edge specification of Via but not both"
                )
            if (via_bottom is None) != (via_top is None):
                raise NotImplementedError(
                    "bottom or top edge specification of Via but not both"
                )

            via_x = 0.0
            if (via_left is not None) and (via_right is not None):
                if has_columns:
                    raise ValueError(
                        "Via left/right edge together with columns specifcation"
                    )
                w = self.tech.on_grid(via_right - via_left, mult=2)
                columns = int((w - width)/pitch) + 1
                if columns < 1:
                    raise ValueError("Not enough width for fitting one column")
                via_x = self.tech.on_grid((via_left + via_right)/2.0)
                via_params["columns"] = columns

            via_y = 0.0
            if (via_bottom is not None) and (via_top is not None):
                if has_rows:
                    raise ValueError(
                        "Via bottom/top edge together with rows specifcation"
                    )
                h = self.tech.on_grid(via_top - via_bottom, mult=2)
                rows = int((h - width)/pitch) + 1
                if rows < 1:
                    raise ValueError("Not enough height for fitting one row")
                via_y =  self.tech.on_grid((via_bottom + via_top)/2.0)
                via_params["rows"] = rows

            origin += _geo.Point(x=via_x, y=via_y)

        via_lay = self.fab.layout_primitive(
            portnets={"conn": net}, prim=via, **via_params,
        )
        via_lay.move(dxy=origin)

        draw = False
        shape = via_lay.bounds(mask=top.mask)
        if top_left is not None:
            shape = _geo.Rect.from_rect(rect=shape, left=top_left)
            draw = True
        if top_bottom is not None:
            shape = _geo.Rect.from_rect(rect=shape, bottom=top_bottom)
            draw = True
        if top_right is not None:
            shape = _geo.Rect.from_rect(rect=shape, right=top_right)
            draw = True
        if top_top is not None:
            shape = _geo.Rect.from_rect(rect=shape, top=top_top)
            draw = True
        if draw:
            for l in (top, *top_extra):
                via_lay.add_shape(layer=l, net=net, shape=shape)
        self.layout += via_lay

        draw = False
        shape = via_lay.bounds(mask=bottom.mask)
        if bottom_left is not None:
            shape = _geo.Rect.from_rect(rect=shape, left=bottom_left)
            draw = True
        if bottom_bottom is not None:
            shape = _geo.Rect.from_rect(rect=shape, bottom=bottom_bottom)
            draw = True
        if bottom_right is not None:
            shape = _geo.Rect.from_rect(rect=shape, right=bottom_right)
            draw = True
        if bottom_top is not None:
            shape = _geo.Rect.from_rect(rect=shape, top=bottom_top)
            draw = True
        if draw:
            kwargs = {}
            if (
                ("bottom_implant" in via_params)
                and (via_params["bottom_implant"] is not None)
            ):
                kwargs["implant"] = via_params["bottom_implant"]
            if "bottom_implant_enclosure" in via_params:
                kwargs["implant_enclosure"] = via_params["bottom_implant_enclosure"]
            if "bottom_well" in via_params:
                kwargs["well"] = via_params["bottom_well"]
                kwargs["well_net"] = via_params["well_net"]
            l = self.add_wire(
                wire=bottom, net=net, shape=shape, extra=bottom_extra,
                **kwargs,
            )
            via_lay += l

        return via_lay

    def add_portless(self, *,
        prim: _prm.DesignMaskPrimitiveT, shape: Optional[_geo._Shape]=None, **prim_params,
    ):
        if len(prim.ports) > 0:
            raise ValueError(
                f"prim '{prim.name}' should not have any port"
            )

        if shape is None:
            return self.layout.add_primitive(prim=prim, **prim_params)
        else:
            if len(prim_params) != 0:
                raise ValueError(
                    f"Parameters '{tuple(prim_params.keys())}' not supported for shape not 'None'",
                )
            self.layout.add_shape(layer=prim, net=None, shape=shape)
CircuitLayouterT = _CircuitLayouter


# import at end of file to avoid circular import problems
from .factory_ import LayoutFactory
