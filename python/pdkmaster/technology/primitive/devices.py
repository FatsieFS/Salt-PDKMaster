# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from enum import Enum
from typing import List, Tuple, Dict, Iterable, Union, Optional, Any, cast
from warnings import warn

from ... import _util
from ...typing import (
    MultiT, cast_MultiT, cast_MultiT_n,
    OptMultiT, cast_OptMultiT, cast_OptMultiT_n,
)

from .. import (
    property_ as _prp, rule as _rle, geometry as _geo,
    mask as _msk, edge as _edg, wafer_ as _wfr, technology_ as _tch,
)

from ._core import (
    _Primitive, _PrimitiveNet, _MaskPrimitive, MaskPrimitiveT,
    _WidthSpacePrimitive,
)
from ._param import _PrimParam
from ._derived import _Intersect, _Alias
from .layers import Marker, ExtraProcess, Insulator, Implant, adjImpl
from .conductors import Well,  WaferWire, GateWire, MetalWire, MIMTop, Via


__all__ = [
    "DevicePrimitiveT", "DeviceParamT", "DeviceParamsT",
    "ResistorWireT", "ResistorIndicatorT", "Resistor",
    "DiodeIndicatorT", "Diode",
    "CapacitorT", "MIMCapacitor",
    "MOSFETGate", "MOSFET", "Bipolar", "BipolarTypeT", "npnBipolar", "pnpBipolar",
]


class _DevicePrimitive(_Primitive):
    """This is a base class to indicate that the primitive is a device
    primitive. A device is a primitive that can be instantiated in a
    circuit and thus has a certain electrical characterics that typically
    can be simulated.
    """
    def __init__(self, *, name: str, **params):
        super().__init__(name=name, **params)
        self.params: "DeviceParamsT"
        self.params = _DeviceParams()

    def cast_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            param.name: param.cast(params.pop(param.name, None))
            for param in self.params
        }
DevicePrimitiveT = _DevicePrimitive


class _DeviceParam(_PrimParam):
    def __init__(self, *,
        primitive: _DevicePrimitive, name: str, allow_none=False, default=None,
    ):
        super().__init__(
            primitive=primitive, name=name, allow_none=allow_none, default=default,
        )
        self._primitive: _DevicePrimitive
DeviceParamT = _DeviceParam


class _DeviceParams(_util.ExtendedListStrMapping[_DeviceParam]):
    pass
DeviceParamsT = _DeviceParams


ResistorWireT = Union[WaferWire, GateWire, MetalWire]
ResistorIndicatorT = Union[Marker, ExtraProcess]
class Resistor(_DevicePrimitive, _MaskPrimitive):
    """Resistor is a primitive that represent a resistor device.
    The resistor itself is not drawn by defined by the overlap
    of other drawn layers.

    Attributes:
        mask: the resulting mask with the shape of the mask. It is
            the overlapping part of the base wire with all the
            indicators
    Arguments:
        wire: the base wire used to make a resistor device.
            It has to be a `WaferWire`, a `Gatewire` or a `MetalWire`
        contact: optional Via layer used to connect the base wire.
        min_contact_space: the minimum of the contact to the overlap
            of the base wire and all the indicator layers.
        indicator: list of indicator layers for the Resistor. Only the
            overlapping area of all the indicator layers will be seen as
            the Resistor device.
            For am indicator of type ExtraProcess it is assumed that this
            extra process does influence the resulting resistance as with
            a Marker type it does not and is thus just a recognition layer.
        min_indicator_extension: minimum required extension of the indicator
            shapes over the base wire. If only one value is given it will
            be used for all the indicators.
        implant: optional implant layer for the resistor. This allows to
            have different sheet resistance and models for wire with
            different implants. If wire is a WaferWire the implant
            layer has to be a valid implant for that waferwire.
    """
    def __init__(self, *, name: str,
        wire: ResistorWireT,
        min_width: Optional[float]=None, min_length: Optional[float]=None,
        min_space: Optional[float]=None,
        contact: Optional[Via], min_contact_space: Optional[float]=None,
        indicator: MultiT[ResistorIndicatorT],
        min_indicator_extension: MultiT[float],
        implant: MultiT[Implant]=(),
        min_implant_enclosure: MultiT[_prp.Enclosure]=(),
        **super_args,
    ):
        # If both model and sheetres are specified, sheetres will be used for
        # LVS circuit generation in pyspice export.
        self.wire = wire

        if min_width is None:
            min_width = wire.min_width
        elif min_width < wire.min_width:
            raise ValueError("min_width may not be smaller than base wire min_width")
        self.min_width = min_width

        if min_length is None:
            min_length = wire.min_width
        elif min_length < wire.min_width:
            raise ValueError("min_length may not be smaller than base wire min_width")
        self.min_length = min_length

        if min_space is None:
            min_space = wire.min_space
        elif min_space < wire.min_space:
            raise ValueError("min_space may not be smaller than base wire min_space")
        self.min_space = min_space

        self.indicator = indicator = cast_MultiT(indicator)
        self.min_indicator_extension = min_indicator_extension = cast_MultiT_n(
            _util.i2f_recursive(min_indicator_extension), n=len(indicator),
        )

        implant = cast_MultiT(implant)
        for impl in implant:
            if isinstance(impl, Well):
                raise TypeError(
                    f"Resistor implant may not be Well '{impl.name}'",
                )
            if isinstance(wire, WaferWire):
                if impl not in wire.implant:
                    raise ValueError(
                        f"implant '{impl.name}' is not valid for waferwire '{wire.name}'"
                    )
            elif not isinstance(wire, GateWire):
                raise ValueError(
                    f"Resistor {name}: "
                    "implant may only be provided for a wire of type "
                    "'WaferWire' or 'GateWire'"
                )
        self.implant = implant
        min_implant_enclosure = cast_MultiT_n(min_implant_enclosure, n=len(implant))
        self.min_implant_enclosure = min_implant_enclosure

        prims = (wire, *indicator, *implant)
        mask = _msk.Intersect(prim.mask for prim in prims).alias(f"resistor:{name}")

        super().__init__(name=name, mask=mask, **super_args)

        self.ports += (
            _PrimitiveNet(prim=self, name=name)
            for name in ("port1", "port2")
        )

        if contact is not None:
            if wire not in (contact.bottom + contact.top):
                raise ValueError(
                    f"wire {wire.name} does not connect to via {contact.name}"
                )
            if min_contact_space is None:
                raise TypeError(
                    "min_contact_space not given when contact is given"
                )
        elif min_contact_space is not None:
            raise TypeError(
                "min_contact_space has to be 'None' if no contact layer is given"
            )
        self.contact = contact
        self.min_contact_space = min_contact_space

        self.params += (
            _DeviceParam(primitive=self, name="width", default=min_width),
            _DeviceParam(primitive=self, name="length", default=min_width),
        )

    def _generate_rules(self, *,
        tech: _tch.Technology,
    ) -> Iterable[_rle.RuleT]:
        # Do not generate the default width/space rules.
        yield from _Primitive._generate_rules(self, tech=tech)

        # TODO: Can we provide proper type for self.mask ?
        yield cast(_msk.DesignMask, self.mask)
        indicator_all_mask = _msk.Intersect(
            (p.mask for p in self.indicator),
        ).alias(f"indicators:resistor:{self.name}")
        self.conn_mask = resistorbody_mask = _msk.Intersect((
            self.mask, indicator_all_mask,
        )).alias(f"body:resistor:{self.name}")

        yield indicator_all_mask
        yield resistorbody_mask

        wire_edge = _edg.MaskEdge(self.wire.mask)
        indicator_all_edge = _edg.MaskEdge(indicator_all_mask)
        resistorbody_edge = _edg.MaskEdge(resistorbody_mask)

        if self.min_space > (self.wire.min_space + _geo.epsilon):
            yield self.mask.space >= self.min_space

        if self.min_width > (self.wire.min_width + _geo.epsilon):
            width_edge = _edg.Intersect((resistorbody_edge, indicator_all_edge))
            yield width_edge.length >= self.min_width

        if self.min_length > (self.wire.min_width + _geo.epsilon):
            length_edge = _edg.Intersect((resistorbody_edge, wire_edge))
            yield length_edge.length >= self.min_length

        for i, ind in enumerate(self.indicator):
            ext = self.min_indicator_extension[i]
            mask = ind.mask.remove(self.wire.mask)
            yield mask.width >= ext

        for i, implant in enumerate(self.implant):
            enc = self.min_implant_enclosure[i]
            yield self.mask.enclosed_by(implant.mask) >= enc


class _Capacitor(_DevicePrimitive):
    """This is a abstract base class for all capacitor types.
    It needs to be subclassed.
    """
    pass
CapacitorT = _Capacitor


class MIMCapacitor(_Capacitor, _MaskPrimitive):
    """`MIMCapactor` represents the so-called Metal-Insulator-Metal
    type of capacitor.
    Currently it specifically tackles the MIM capacitor made with
    a dieletric on top of a MetalWire with on top of that an
    intermediate metal layer.

    Arguments:
        name: the name of the MIMCapacitor
        bottom: the bottom layer of the MIM capacitor
        top: the top layer of the MIM capacitor
        via: the Via layer contacting both the bottom and top layer
            of the MIM capacitor
        min_bottom_top_enclosure: min required enclosure of the top
            layer by the bottom layer
        min_bottomvia_top_space: min space from a via contacting the bottom
            layer to the top layers
        min_top_via_enclosure: min enclosure of a via contacting the top
            layer by the top layer.
        min_bottom_space: minimum space from a shape that is used as the
            bottom of a MIM capacitor to any other shape on the bottom
            MetalWire layer.
        min_top2bottom_space: minimum space from the top layer to any shape
            on the bottom MetalWire that is not the bottom plate of the
            same capacitor.
    """
    def __init__(self, *, name: str,
        bottom: MetalWire, top: MIMTop, via: Via,
        min_width: Optional[float]=None,
        min_bottom_top_enclosure: _prp.Enclosure, min_bottomvia_top_space: float,
        min_top_via_enclosure: _prp.Enclosure,
        min_bottom_space: Optional[float], min_top2bottom_space: Optional[float],
        **super_args,
    ):
        if not bottom in via.bottom:
            raise ValueError(
                f"MIMCapacitor '{name}':"
                f" bottom '{bottom.name}' is not a bottom layer for via '{via.name}'"
            )
        if not top in via.bottom:
            raise ValueError(
                f"MIMCapacitor '{name}':"
                f" top '{top.name}' is not a bottom layer for via '{via.name}'"
            )

        if min_width is None:
            min_width = top.min_width
        elif min_width < top.min_width:
            raise ValueError("min_width may not be smaller than MIMTop min_width")
        self.min_width = min_width

        self.bottom = bottom
        self.top = top
        self.via = via

        self.min_bottom_top_enclosure = min_bottom_top_enclosure
        self.min_bottomvia_top_space = min_bottomvia_top_space
        self.min_top_via_enclosure = min_top_via_enclosure
        self.min_bottom_space = min_bottom_space
        self.min_top2bottom_space = min_top2bottom_space

        mask = top.mask.alias(f"mimcap:{name}")

        super().__init__(name=name, mask=mask, **super_args)

        self.ports += (
            _PrimitiveNet(prim=self, name=name)
            for name in ("bottom", "top")
        )

        self.params += (
            _DeviceParam(primitive=self, name="width", default=self.min_width),
            _DeviceParam(primitive=self, name="height", default=self.min_width),
        )

    def _generate_rules(self, *,
        tech: _tch.Technology,
    ) -> Iterable[_rle.RuleT]:
        yield from super()._generate_rules(tech=tech)

        # TODO: MIMCapacitor rules


DiodeIndicatorT = Union[Marker, ExtraProcess]
class Diode(_DevicePrimitive, _MaskPrimitive):
    """`Diode` represent a diode device made up of a WaferWire object.
    A diode device needs a pn-junction which does need to be achieved by
    implants.

    Arguments:
        name: name for the diode
        wire: the base layer for the diode
        min_width: minimum width of the diode.
            The minimum width of the wire layer is taken as default value.
        indicator: list of indicator layers for the Diode. Only the
            overlapping area of all the indicator layers will be seen as
            the Resistor device. At least one indicator layer has to be given;
            diodes without indicators are considered to be parasitic devices.
            Both ExtraProcess and Marker are valid indicator layers.
        min_indicator_extension: minimum required enclosure of the base wire
            by the indicator. If only one value is given it will
            be used for all the indicators.
        implant: the implant layer of the WaferWire forming the diode.
            The implant layer has to be a valid implant layer for the
            base WaferWire primitive.
        min_implant_enclosure: the optional minimum required enclosure
            of the base wire by the implant. If not provided the one specified
            for the base wire will be used as default.
        well: optional well to place the diode in. This well has to be of
            opposite type of the implant layer. If no well is specified
            the diode is in the substrate. So then the base wire must be
            allowed to be placed in the substrate and the technology
            substrate type has to be the opposite of the implant of
            the diode.
        min_well_enclosure: optional minimum required enclosure of the
            base wire by the well. If no well is specified no
            min_well_enclosure may be specified either. If a well is
            specified but no min_well_enclosure the minimum well enclosure
            from the base WaferWire will be used.
    """
    def __init__(self, *, name: str,
        wire: WaferWire, min_width: Optional[float]=None,
        indicator: MultiT[DiodeIndicatorT], min_indicator_enclosure: MultiT[_prp.Enclosure],
        implant: MultiT[Implant], min_implant_enclosure: MultiT[_prp.Enclosure]=(),
        well: Optional[Well]=None, min_well_enclosure: Optional[_prp.Enclosure]=None,
        **super_args,
    ):
        self.wire = wire

        if min_width is None:
            min_width = wire.min_width
        elif min_width < wire.min_width:
            raise ValueError("min_width may not be smaller than base wire min_width")
        self.min_width = min_width

        self.indicator = indicator = cast_MultiT(indicator)
        if not indicator:
            raise ValueError(f"No indicator(s) given for Diode `{name}`")

        self.min_indicator_enclosure = min_indicator_enclosure = cast_MultiT_n(
            min_indicator_enclosure, n=len(indicator),
        )

        self.implant = implant = cast_MultiT(implant)
        for impl in implant:
            if isinstance(impl, Well):
                raise TypeError(f"implant '{impl.name}' is a well")
            if impl not in wire.implant:
                raise ValueError(
                    f"implant '{impl.name}' is not valid for waferwire '{wire.name}'"
                )
        if implant and not min_implant_enclosure:
            def get_enc(impl: Implant) -> _prp.Enclosure:
                idx = wire.implant.index(impl)
                return wire.min_implant_enclosure[idx]
            min_implant_enclosure = tuple(get_enc(impl) for impl in implant)
        min_implant_enclosure = cast_MultiT_n(min_implant_enclosure, n=len(implant))
        self.min_implant_enclosure = min_implant_enclosure

        if "mask" in super_args:
            raise TypeError("Diode got an unexpected keyword argument 'mask'")
        else:
            super_args["mask"] = _msk.Intersect(
                prim.mask for prim in (wire, *indicator, *implant)
            ).alias(f"diode:{name}")

        super().__init__(name=name, **super_args)

        self.ports += (
            _PrimitiveNet(prim=self, name=name)
            for name in ("anode", "cathode")
        )

        if well is None:
            if not wire.allow_in_substrate:
                raise TypeError(f"wire '{wire.name}' has to be in a well")
            # TODO: check types of substrate and implant
            if min_well_enclosure is not None:
                raise TypeError("min_well_enclosure given without a well")
        else:
            if well not in wire.well:
                raise ValueError(
                    f"well '{well.name}' is not a valid well for wire '{wire.name}'"
                )
            for impl in implant:
                if well.type_ == impl.type_:
                    raise ValueError(
                        f"type of implant '{impl.name}' may not be the same as"
                        " type of well '{well.name}' for a diode"
                    )
        self.well = well
        self.min_well_enclosure = min_well_enclosure

        self.params += (
            _DeviceParam(primitive=self, name="width", default=self.min_width),
            _DeviceParam(primitive=self, name="height", default=self.min_width),
        )

    @property
    def designmasks(self) -> Iterable[_msk.DesignMask]:
        yield from self.wire.designmasks
        for impl in self.implant:
            yield from impl.designmasks
        if self.well is not None:
            yield from self.well.designmasks
        yield from super().designmasks

    def _generate_rules(self, *,
        tech: _tch.Technology,
    ) -> Iterable[_rle.RuleT]:
        # Do not generate the default width/space rules.
        yield from _Primitive._generate_rules(self, tech=tech)

        # TODO: Can we provide proper type for self.mask ?
        yield cast(_msk._MaskAlias, self.mask)
        if self.min_width > self.wire.min_width:
            yield self.mask.width >= self.min_width
        for i, ind in enumerate(self.indicator):
            enc = self.min_indicator_enclosure[i]
            yield self.wire.mask.enclosed_by(ind.mask) >= enc
        if self.min_implant_enclosure is not None:
            for i, impl in enumerate(self.implant):
                idx = self.implant.index(impl)
                enc = self.min_implant_enclosure[idx]
                yield self.mask.enclosed_by(impl.mask) >= enc


class MOSFETGate(_WidthSpacePrimitive):
    """MOSFETGate is a primitive representing the gate of a MOSFET transistor.
    A self-aligned process is assumed for the MOSFET so the gate is basically
    the area where a gate layer crosses the active layer. A dielectric layer
    in between the two layers is forming the gate capacitor the is part of the
    basic principles of how a MOSFET device funtions.
    The gate has a seaparte primitive as it often is common between different
    MOSFET devices (e.g. nmos and pmos or multi-Vt devices) with common rules.

    Arguments:
        name: optional name for the gate.
            If not specified a unique name based on the layers is given
        active: the bottom layer for the gate.
            The part of the active layer under the gate layer is acting as the
            channel of the MOSFET.
        poly: the top layer of gate.
        oxide: optionally an oxide layer can be given to have gate for different
            types of devices.
            If not specified it means to default oxide layer of the process is
            present to form the
        min_gateoxide_enclosure: optional minimum required enclosure of the gate
            by the oxide layer
        inside: optional marker layers for the gate.
            This allows to specify alternative rules for a device that is
            physically processed the same as another device.
            Example use is the marking of ESD devices with own rules but
            being physically the same device as the other higher voltage
            devices.
        min_gateinside_enclosure: optional minimum required enclosure of the gate
            by the inside layer. If 1 value is specified it is used for all the
            inside layers.
        min_l: optional minimum l specification valid for all MOSFET devices
            using this gate.
            If not specified the minimum poly layer width will be used as
            the minimum l.
        max_l: optional maximum l specification valid for all MOSFET devices
            using this gate.
            If not specified not maximum l is enforced.
        min_w: optional minimum w specification valid for all MOSFET devices
            using this gate.
            If not specified the minimum active layer width will be used as
            the minimum w.
        max_w: optional minimum w specification valid for all MOSFET devices
            using this gate.
            If not specified not maximum w is enforced.
        min_sd_width: optional minimum extension of the active layer over
            the gate.
        min_polyactive_extension: optional minimum extension of the poly layer
            over the gate.
        min_gate_space: optional minimum spacing between two gates sharing
            the same active wire
        contact: optional contact layer for this device; this is needed to
            allow to specify the minimum contact to gate spacing.
        min_contactgate_space: optional common specification of minimum contact
            to gate spacing
    """
    class _ComputedProps:
        def __init__(self, gate: "MOSFETGate"):
            self.gate = gate

        @property
        def min_l(self) -> float:
            min_l = self.gate.min_l
            if min_l is None:
                min_l = self.gate.poly.min_width
            return min_l

        @property
        def min_w(self) -> float:
            min_w = self.gate.min_w
            if min_w is None:
                min_w = self.gate.active.min_width
            return min_w

        @property
        def min_gate_space(self) -> float:
            s = self.gate.min_gate_space
            if s is None:
                s = self.gate.poly.min_space
            return s

        @property
        def min_sd_width(self) -> Optional[float]:
            return self.gate.min_sd_width

        @property
        def min_polyactive_extension(self) -> Optional[float]:
            return self.gate.min_polyactive_extension

    @property
    def computed(self):
        """the computed property allows to get values for parameters that
        were not specified during object init.
        For example assume that `gate` is MOSFETGate object that did not
        specify `min_l`. Then `gate.min_l` is `None` and `gate.computed.min_l`
        is equal to `gate.poly.min_width`.
        This separation is done to server different use cases. When looking
        at DRC rules `gate.min_l` being `None` indicated no extra rule
        needs to be generated for this gate. For layout it is easier to use
        `gate.computed.min_l` to derive the dimension of the device to be
        drawn.
        """
        return MOSFETGate._ComputedProps(self)

    def __init__(self, *, name: Optional[str]=None,
        active: WaferWire, poly: GateWire,
        oxide: Optional[Insulator]=None,
        min_gateoxide_enclosure: Optional[_prp.Enclosure]=None,
        inside: OptMultiT[Marker]=None,
        min_gateinside_enclosure: OptMultiT[_prp.Enclosure]=None,
        min_l: Optional[float]=None, max_l: Optional[float]=None,
        min_w: Optional[float]=None, max_w: Optional[float]=None,
        min_sd_width: Optional[float]=None,
        min_polyactive_extension: Optional[float]=None,
        min_gate_space: Optional[float]=None,
        contact: Optional[Via]=None,
        min_contactgate_space: Optional[float]=None,
    ):
        self.active = active
        self.poly = poly

        prims = (poly, active)
        if oxide is not None:
            if oxide not in active.oxide:
                raise ValueError(
                    f"oxide '{oxide.name}' is not valid for active '{active.name}'"
                )
            prims += (oxide,)
        elif min_gateoxide_enclosure is not None:
            raise TypeError("min_gateoxide_enclosure provided without an oxide")
        self.oxide = oxide
        self.min_gateoxide_enclosure = min_gateoxide_enclosure

        inside = cast_OptMultiT(inside)
        if inside is not None:
            prims += inside
            min_gateinside_enclosure = cast_OptMultiT_n(
                min_gateinside_enclosure, n=len(inside),
            )
        elif min_gateinside_enclosure is not None:
            raise TypeError("min_gateinside_enclosure provided without inside provided")
        self.inside = inside
        self.min_gateinside_enclosure = min_gateinside_enclosure

        if name is None:
            name = "gate({})".format(",".join(prim.name for prim in prims))
            gatename = "gate:" + "+".join(prim.name for prim in prims)
        else:
            gatename = f"gate:{name}"

        if min_l is not None:
            self.min_l = min_l
        else:
            # local use only
            min_l = poly.min_width
            self.min_l = None
        self.max_l = max_l

        if min_w is not None:
            self.min_w = min_w
        else:
            # local use only
            min_w = active.min_width
            self.min_w = None
        self.max_w = max_w

        self.min_sd_width = min_sd_width

        self.min_polyactive_extension = min_polyactive_extension

        if min_gate_space is not None:
            self.min_gate_space = min_gate_space
        else:
            # Local use only
            min_gate_space = poly.min_space
            self.min_gate_space = None

        if min_contactgate_space is not None:
            if contact is None:
                raise TypeError(
                    "min_contactgate_space given without contact layer"
                )
        elif contact is not None:
            raise TypeError(
                "contact layer provided without min_contactgate_space specification"
            )
        self.contact = contact
        self.min_contactgate_space = min_contactgate_space

        mask = _msk.Intersect(prim.mask for prim in prims).alias(gatename)
        super().__init__(
            name=name, mask=mask,
            min_width=min(min_l, min_w), min_space=min_gate_space,
        )

    def _generate_rules(self, *,
        tech: _tch.Technology,
    ) -> Iterable[_rle.RuleT]:
        active_mask = self.active.mask
        poly_mask = self.poly.conn_mask

        # Update mask if it has no oxide
        extra_masks = tuple()
        if self.oxide is None:
            extra_masks += tuple(
                cast(Any, gate).oxide.mask for gate in filter(
                    lambda prim: (
                        isinstance(prim, MOSFETGate)
                        and prim.active == self.active
                        and prim.poly == self.poly
                        and (prim.oxide is not None)
                    ), tech.primitives,
                )
            )
        if self.inside is None:
            def get_key(gate: "MOSFETGate"):
                if gate.oxide is not None:
                    return frozenset((gate.active, gate.poly, gate.oxide))
                else:
                    return frozenset((gate.active, gate.poly))

            for gate in filter(
                lambda prim: (
                    isinstance(prim, MOSFETGate)
                    and (get_key(prim) == get_key(self))
                    and prim.inside is not None
                ), tech.primitives,
            ):
                extra_masks += tuple(inside.mask for inside in cast(Any, gate).inside)
        masks = (active_mask, poly_mask)
        if self.oxide is not None:
            masks += (self.oxide.mask,)
        if self.inside is not None:
            masks += tuple(inside.mask for inside in self.inside)
        if extra_masks:
            masks += (_wfr.wafer.remove(extra_masks),)
        # Keep the alias but change the mask of the alias
        cast(_msk._MaskAlias, self.mask).mask = _msk.Intersect(masks)
        mask = self.mask

        mask_used = False
        rules: List[_rle.RuleT] = []
        if self.min_l is not None:
            rules.append(
                _edg.Intersect(
                    (_edg.MaskEdge(active_mask), _edg.MaskEdge(self.mask))
                ).length >= self.min_l,
            )
        if self.max_l is not None:
            rules.append(
                _edg.Intersect(
                    (_edg.MaskEdge(active_mask), _edg.MaskEdge(self.mask))
                ).length <= self.max_l,
            )
        if self.min_w is not None:
            rules.append(
                _edg.Intersect(
                    (_edg.MaskEdge(poly_mask), _edg.MaskEdge(self.mask))
                ).length >= self.min_w,
            )
        if self.max_w is not None:
            rules.append(
                _edg.Intersect(
                    (_edg.MaskEdge(poly_mask), _edg.MaskEdge(self.mask))
                ).length <= self.max_w,
            )
        if self.min_sd_width is not None:
            rules.append(active_mask.extend_over(mask) >= self.min_sd_width)
            mask_used = True
        if self.min_polyactive_extension is not None:
            rules.append(
                poly_mask.extend_over(mask) >= self.min_polyactive_extension,
            )
            mask_used = True
        if self.min_gate_space is not None:
            edge_on_act = _edg.Intersect(edges=(
                _edg.MaskEdge(mask=mask), _edg.MaskEdge(self.poly.mask),
            ))
            rules.append(edge_on_act.space >= self.min_gate_space)
            mask_used = True
        if self.min_contactgate_space is not None:
            assert self.contact is not None
            rules.append(
                _msk.Spacing(mask, self.contact.mask) >= self.min_contactgate_space,
            )
            mask_used = True

        if mask_used:
            # This rule has to be put before the other rules that use the alias
            yield cast(_rle.RuleT, mask)
        yield from _MaskPrimitive._generate_rules(self, tech=tech, gen_mask=False)
        yield from rules


class MOSFET(_DevicePrimitive):
    """MOSFET is a primitive representing a MOSFET transistor.

    MOS stands for metal-oxide-semiconductor; see
    https://en.wikipedia.org/wiki/MOSFET for explanation of a MOSFET device.

    Arguments:
        name: name for the gate.
        gate: the `MOSFETGate` object for this device
        implant: implant layers for this device
            If no n or p type implant is given for the MOSFET the type of the
            is considered the opposite of the well/substrate the device is in.
            It is not allowed to have mosfets with and without n/p type implants
            in the same well or in the substrate.
        well: optional well in which this MOSFET needs to be located.
            If gate.active can't be put in substrate well has to be
            specified. If specified the well has to be valid for
            gate.active and the implant type has to be opposite to the
            implant types.
        min_l: optional minimum l specification for the MOSFET device
            If not specified the min_l of the gate will be used, which
            in turn could be the gate poly layer minimum width.
        max_l: optional maximum l specification for the MOSFET device
            If not specified the max_l of the gate will be used. If neither
            is specified no maximum l is enforced.
        min_w: optional minimum w specification valid the MOSFET device
            If not specified the min_w of the gate will be used, which
            in turn could be the gate active layer minimum width.
        max_w: optional maximum w specification valid the MOSFET device
            If not specified the max_w of the gate will be used. If neither
            is specified no maximum w is enforced.
        min_sd_width: optional minimum extension of the active layer over
            the gate.
            If not specified the value from the gate will be used.
            This value has to be specified either here or for the gate.
        min_polyactive_extension: optional minimum extension of the poly layer
            over the gate.
            If not specified the value from the gate will be used.
            This value has to be specified either here or for the gate.
        min_gateimplant_enclosure: minimum enclosure of the transistor gate
            by the implantation layers. If more than one implantation layer
            is specified either a common enclosure can be specified or an
            value for each implant layer.
        min_gate_space: optional minimum spacing between two gates sharing
            the same active wire
            If not specified the value from the gate will be used.
            This value has to be specified either here or for the gate.
        contact: optional contact layer for this device; this is needed to
            allow to specify the minimum contact to gate spacing.
            If not specified the value from the gate will be used.
        min_contactgate_space: optional common specification of minimum contact
            to gate spacing
            If not specified the value from the gate will be used.
            If neither the gate nor here contact is specified this parameter may
            not be specified either. Otherwise here and/or the gate have to
            speicify a value.
    """
    class _ComputedProps:
        def __init__(self, mosfet: "MOSFET"):
            self.mosfet = mosfet

        def _lookup(self, name: str, allow_none: bool):
            mosfet = self.mosfet
            v = getattr(mosfet, name)
            if v is None:
                v = getattr(mosfet.gate.computed, name, None)
            if v is None:
                v = getattr(mosfet.gate, name, None)
            if not allow_none:
                assert v is not None, "needed attribute"
            return v

        @property
        def min_l(self) -> float:
            return cast(float, self._lookup("min_l", False))

        @property
        def max_l(self) -> float:
            return cast(float, self._lookup("max_l", True))

        @property
        def min_w(self) -> float:
            return cast(float, self._lookup("min_w", False))

        @property
        def max_w(self) -> float:
            return cast(float, self._lookup("max_w", True))

        @property
        def min_sd_width(self) -> float:
            return cast(float, self._lookup("min_sd_width", False))

        @property
        def min_polyactive_extension(self) -> float:
            return cast(float, self._lookup("min_polyactive_extension", False))

        @property
        def min_gate_space(self) -> float:
            return cast(float, self._lookup("min_gate_space", False))

        @property
        def contact(self) -> Optional[Via]:
            return cast(Optional[Via], self._lookup("contact", True))

        @property
        def min_contactgate_space(self) -> float:
            return cast(float, self._lookup("min_contactgate_space", False))

    @property
    def computed(self):
        """the computed property allows to get values for parameters that
        were not specified during object init.
        For example assume that `nmos` is MOSFET object that did not
        specify `min_l`. Then `nmos.min_l` is `None` and `nmos.computed.min_l`
        is equal to `nmos.gate.computed.min_l`, which can then
        refer further to `nmos.gate.poly.min_width`.
        This separation is done to server different use cases. When looking
        at DRC rules `gate.min_l` being `None` indicated no extra rule
        needs to be generated for this gate. For layout it is easier to use
        `gate.computed.min_l` to derive the dimension of the device to be
        drawn.
        """
        return MOSFET._ComputedProps(self)

    def __init__(self, *, name: str,
        gate: MOSFETGate, implant: MultiT[Implant],
        well: Optional[Well]=None,
        min_l: Optional[float]=None, max_l: Optional[float]=None,
        min_w: Optional[float]=None, max_w: Optional[float]=None,
        min_sd_width: Optional[float]=None,
        min_polyactive_extension: Optional[float]=None,
        min_gateimplant_enclosure: MultiT[_prp.Enclosure],
        min_gate_space: Optional[float]=None,
        contact: Optional[Via]=None,
        min_contactgate_space: Optional[float]=None,
    ):
        super().__init__(name=name)

        implant = cast_MultiT(implant)
        type_ = None
        for impl in implant:
            if impl.type_ != adjImpl:
                if type_ is None:
                    type_ = impl.type_
                elif type_ != impl.type_:
                    raise ValueError(
                        "both n and p type implants for same MOSFET are not allowed"
                    )
        wrong = tuple(filter(
            lambda impl: impl not in gate.active.implant,
            implant
        ))
        if wrong:
            names = tuple(impl.name for impl in wrong)
            raise ValueError(
                f"implants {names} not valid for gate.active '{gate.active.name}'"
            )

        if well is None:
            if not gate.active.allow_in_substrate:
                raise ValueError(
                    f"well needed as gate active '{gate.active.name}'"
                    " can't be put in substrate"
                )
        else:
            if well not in gate.active.well:
                raise ValueError(
                    f"well '{well.name}' not valid for gate.active '{gate.active.name}'"
                )
            if type_ == well.type_:
                raise ValueError("well and implant(s) have to be of different type")

        self.gate = gate
        self.implant = implant
        self.well = well

        if min_l is not None:
            if min_l <= gate.computed.min_l:
                raise ValueError("min_l has to be bigger than gate min_l if not 'None'")
        self.min_l = min_l
        self.max_l = max_l

        if min_w is not None:
            if min_w <= gate.computed.min_w:
                raise ValueError("min_w has to be bigger than gate min_w if not 'None'")
        self.min_w = min_w
        self.max_w = max_w

        if (min_sd_width is None) and (gate.min_sd_width is None):
            raise ValueError(
                "min_sd_width neither provided for the transistor gate or the transistor",
            )
        self.min_sd_width = min_sd_width

        if (min_polyactive_extension is None) and (gate.min_polyactive_extension is None):
            raise ValueError(
                "min_polyactive_extension neither provided for the transistor gate"
                " or the transistor",
            )
        self.min_polyactive_extension = min_polyactive_extension

        self.min_gateimplant_enclosure = min_gateimplant_enclosure = cast_MultiT_n(
            min_gateimplant_enclosure, n=len(implant),
        )

        self.min_gate_space = min_gate_space

        if min_contactgate_space is not None:
            if contact is None:
                if gate.contact is None:
                    raise ValueError(
                        "no contact layer provided for min_contactgate_space specification",
                    )
                contact = gate.contact
        elif contact is not None:
            raise ValueError(
                "contact layer provided without min_contactgate_space specification",
            )
        self.min_contactgate_space = min_contactgate_space
        self.contact = contact

        # Derive _gate4mosfet
        gate_prims = (gate, *implant)
        if well is not None:
            gate_prims += (well,)
        gate4mosfet = gate_prims[0] if len(gate_prims) == 1 else _Intersect(prims=gate_prims)
        if (well is None) and gate.active.well:
            gate4mosfet = gate4mosfet.remove(gate.active.well)
        self._gate4mosfet = gate4mosfet.alias(f"gate:mosfet:{name}")

        # MOSFET is symmetric so both diffusion regions can be source or drain
        bulknet = (
            _PrimitiveNet(prim=self, name="bulk") if well is not None
            else _wfr.SubstrateNet(name="bulk")
        )
        self.ports += (
            _PrimitiveNet(prim=self, name="sourcedrain1"),
            _PrimitiveNet(prim=self, name="sourcedrain2"),
            _PrimitiveNet(prim=self, name="gate"),
            bulknet,
        )

        self.params += (
            _DeviceParam(primitive=self, name="l", default=self.computed.min_l),
            _DeviceParam(primitive=self, name="w", default=self.computed.min_w),
        )

    @property
    def has_typeimplant(self) -> bool:
        return any(impl.type_ != adjImpl for impl in self.implant)
    @property
    def gate4mosfet(self) -> MaskPrimitiveT:
        """gate_prim attribute is the primitive representing the gate of the MOSFET
        object. Main reason it exists is to use it in rules; for example a minimum spacing
        to the gate of a transistor.
        """
        return self._gate4mosfet

    def _generate_rules(self, *,
        tech: _tch.Technology,
    ) -> Iterable[_rle.RuleT]:
        yield from super()._generate_rules(tech=tech)

        derivedgate = cast(_Alias, self.gate4mosfet)
        derivedgate_edge = _edg.MaskEdge(derivedgate.mask)
        poly_mask = self.gate.poly.mask
        poly_edge = _edg.MaskEdge(poly_mask)
        channel_edge = _edg.Intersect((derivedgate_edge, poly_edge))
        active_mask = self.gate.active.mask
        active_edge = _edg.MaskEdge(active_mask)
        fieldgate_edge = _edg.Intersect((derivedgate_edge, active_edge))

        yield derivedgate.mask
        if self.min_l is not None:
            yield _edg.Intersect(
                (derivedgate_edge, active_edge),
            ).length >= self.min_l
        if self.max_l is not None:
            yield _edg.Intersect(
                (derivedgate_edge, active_edge),
            ).length <= self.max_l
        if self.min_w is not None:
            yield _edg.Intersect(
                (derivedgate_edge, poly_edge),
            ).length >= self.min_w
        if self.max_w is not None:
            yield _edg.Intersect(
                (derivedgate_edge, poly_edge),
            ).length <= self.max_w
        if self.min_sd_width is not None:
            yield (
                active_mask.extend_over(derivedgate.mask) >= self.min_sd_width
            )
        if self.min_polyactive_extension is not None:
            yield (
                poly_mask.extend_over(derivedgate.mask)
                >= self.min_polyactive_extension
            )
        for i in range(len(self.implant)):
            impl_mask = self.implant[i].mask
            enc = self.min_gateimplant_enclosure[i]
            if not enc.is_assymetric:
                yield derivedgate.mask.enclosed_by(impl_mask) >= enc
            else:
                yield channel_edge.enclosed_by(impl_mask) >= enc.spec[0]
                yield fieldgate_edge.enclosed_by(impl_mask) >= enc.spec[1]
        if self.min_gate_space is not None:
            yield derivedgate.mask.space >= self.min_gate_space
        if self.min_contactgate_space is not None:
            assert self.contact is not None
            yield (
                _msk.Spacing(derivedgate.mask, self.contact.mask)
                >= self.min_contactgate_space
            )

    @property
    def designmasks(self):
        yield from super().designmasks
        yield from self.gate.designmasks
        if self.implant is not None:
            for impl in self.implant:
                yield from impl.designmasks
        if self.well is not None:
            yield from self.well.designmasks
        if self.contact is not None:
            if (self.gate.contact is None) or (self.contact != self.gate.contact):
                yield from self.contact.designmasks


class Bipolar(_DevicePrimitive):
    """The Bipolar primitive represents the bipolar injunction transistors.
    It's thus a PNP or a NPN device.

    For more info see https://en.wikipedia.org/wiki/Bipolar_junction_transistor

    Currently no layout generation for this device is implemented and the
    technology will need to provide fixed layout implementations. Bipolar
    devices are assumed to have fixed layouts for each technology.

    Arguments:
        name: name of the Bipolar device
        type_: the bipolar type; has to be 'npn' or 'pnp'
        indicator: the layer(s) to mark a certain structure as a bipolar device

    API Notes:
        Bipolar does not have a fixed API yet. Backwards incompatible changes
        are reserved for implemting more general layout generation.
    """
    class BipolarType(Enum):
        """The type of implant.
        Currently implemented types are: npn, pnp. The .value of the enum
        object is the string of the type; e.g. "npn", "pnp".

        These types are also made available as `npnBipolar` and `pnpBipolar`
        in the primitive module.
        """
        npn = "npn"
        pnp = "pnp"

        def __hash__(self) -> int:
            return super().__hash__()

        def __eq__(self, __o: object) -> bool:
            if isinstance(__o, str):
                warn("Comparison of `BipolarType` with `str` always returns `False`")
            return super().__eq__(__o)

    # TODO: add the specification for WaferWire and implants with which the
    #     collector, base and emittor of the device are made.
    def __init__(self, *,
        name: str, type_: BipolarType, indicator: MultiT[Marker],
    ):
        super().__init__(name=name)

        self.type_ = type_
        self.indicator = cast_MultiT(indicator)

        self.ports += (
            _PrimitiveNet(prim=self, name="collector"),
            _PrimitiveNet(prim=self, name="base"),
            _PrimitiveNet(prim=self, name="emitter"),
        )

    def _generate_rules(self, *, tech: _tch.Technology) -> Iterable[_rle.RuleT]:
        return super()._generate_rules(tech=tech)

    @property
    def designmasks(self) -> Iterable[_msk.DesignMask]:
        yield from super().designmasks
        for indicator in self.indicator:
            yield from indicator.designmasks
BipolarTypeT = Bipolar.BipolarType
npnBipolar = Bipolar.BipolarType.npn
pnpBipolar = Bipolar.BipolarType.pnp
