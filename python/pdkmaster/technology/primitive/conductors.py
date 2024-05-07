# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
import abc
from itertools import combinations, chain
from typing import Tuple, Dict, Set, Union, Iterable, Optional, cast

from ...typing import (
    MultiT, cast_MultiT, cast_MultiT_n,
    OptMultiT, cast_OptMultiT_n,
)
from .. import (
    property_ as _prp, rule as _rle, mask as _msk, edge as _edg, technology_ as _tch,
)

from . import MaskPrimitiveT
from ._core import (
    _Primitive, _PrimitiveNet, _DesignMaskPrimitive, _WidthSpaceDesignMaskPrimitive,
    UnconnectedPrimitiveError,
)
from ._derived import _Intersect
from .layers import Marker, Insulator, Implant


__all__ = [
    "BlockageAttrPrimitiveT", "PinAttrPrimitiveT",
    "ConductorT", "WidthSpaceConductorT",
    "Well", "DeepWell",
    "WaferWire", "GateWire", "MetalWire", "MIMTop", "TopMetalWire",
    "ViaBottom", "ViaTop", "Via", "PadOpening",
]


class _BlockageAttribute(_Primitive):
    """Mixin class for primitives with a blockage attribute

    The blockage layer is a layer to indicate areas where no base layer
    shapes should be added. This is often used by place-and-route to
    not add routing in certain places. The blockage layer can then also be
    used to have abstract view of cells that don't contain the real
    shapes but just the area where the router should not add shapes.
    """
    def __init__(self, *, blockage: Optional[Marker]=None, **super_args):
        self._blockage = blockage
        super().__init__(**super_args)

    @property
    def blockage(self) -> Marker:
        if self._blockage is None:
            raise AttributeError(f"Primitive '{self.name}' has no blockage attribute")
        return self._blockage
BlockageAttrPrimitiveT = _BlockageAttribute


class _PinAttribute(_Primitive):
    """Mixin class for primitives with a pin attribute

    The pin layer is a layer that can indicate where external signals
    of a cell can be connected. The exact rules of how to use this pin
    layer are PDK specific.
    """
    def __init__(self, *,
        pin: Optional[Marker]=None,
        **super_args,
    ):
        self._pin = pin
        super().__init__(**super_args)

    @property
    def pin(self) -> Marker:
        if self._pin is None:
            raise AttributeError(f"Primitive '{self.name}' has no pin attribute")
        return self._pin
PinAttrPrimitiveT = _PinAttribute


class _Conductor(_BlockageAttribute, _PinAttribute, _DesignMaskPrimitive):
    """Primitive that acts as a conductor.

    This primitive is assumed to use a DesignMask as it's mask. And will
    allow a blockage and a pin layer.
    """
    @abc.abstractmethod
    def __init__(self, **super_args):
        super().__init__(**super_args)

        self.ports += _PrimitiveNet(prim=self, name="conn")

    def _generate_rules(self, *,
        tech: _tch.Technology,
    ) -> Iterable[_rle.RuleT]:
        from .devices import Resistor, MOSFETGate

        yield from super()._generate_rules(tech=tech)

        # Generate a mask for connection, thus without resistor parts
        # or ActiveWire without gate etc.
        indicators = chain(*tuple(r.indicator for r in filter(
            lambda p: p.wire == self,
            tech.primitives.__iter_type__(Resistor),
        )))
        polys = tuple(g.poly for g in filter(
            lambda p: p.active == self,
            tech.primitives.__iter_type__(MOSFETGate)
        ))
        removes = {p.mask for p in chain(indicators, polys)}

        if removes:
            if len(removes) == 1:
                remmask = removes.pop()
            else:
                remmask = _msk.Join(removes)
            self.conn_mask = self.mask.remove(remmask).alias(self.mask.name + "__conn")
            yield self.conn_mask
        else:
            self.conn_mask = self.mask
ConductorT = _Conductor


class _WidthSpaceConductor(_Conductor, _WidthSpaceDesignMaskPrimitive):
    """_WidthSpacePrimitive that is also a _Conductor"""
    pass
WidthSpaceConductorT = _WidthSpaceConductor


class Well(_WidthSpaceConductor, Implant):
    """Well is an Implant layer that has deeper implant so it forms a
    well of a certain type.

    Typical application is for both NMOS and PMOS transistors on a wafer
    without shorting the source/drain regions to the bulk.

    Arguments:
        min_space_samenet: the smaller spacing between two wells on
            the same net.
    """
    # Wells are non-overlapping by design
    def __init__(self, *,
        min_space_samenet: Optional[float]=None, **super_args,
    ):
        super().__init__(**super_args)

        if min_space_samenet is not None:
            if min_space_samenet >= self.min_space:
                raise ValueError("min_space_samenet has to be smaller than min_space")
        self.min_space_samenet = min_space_samenet

    def _generate_rules(self, *,
        tech: _tch.Technology,
    ) -> Iterable[_rle.RuleT]:
        yield from super()._generate_rules(tech=tech)

        if self.min_space_samenet is not None:
            yield self.mask.same_net.space >= self.min_space_samenet


class DeepWell(_WidthSpaceConductor, Implant):
    """The DeepWell primitive defines a well deeper into the substrate and normally
    used to connect a normal Well and in that way isolate some part of the wafer
    substrate. Most commonly this is the combination of the N-Well together with a
    depp N-Well to isolate the holes in the N-Well layer.

    Currently only low-level _Layout.add_shape() is supported for DeepWell, no
    support is present for combined Well + DeepWell layout generation.
    """
    def __init__(self, *,
        well: Well, type_: Optional[Implant.ImplantType]=None,
        min_well_overlap: float, min_well_enclosure: float,
        **super_args,
    ):
        if type_ is None:
            type_ = well.type_
        elif type_ != well.type_:
            raise ValueError(
                f"DeepWell type '{type_}' is different from type {well.type_} of Well"
                f" '{well.name}'"
            )
        super().__init__(type_=type_, **super_args)

        self.well = well
        self.min_well_overlap = min_well_overlap
        self.min_well_enclosure = min_well_enclosure

    def _generate_rules(self, *,
        tech: _tch.Technology,
    ) -> Iterable[_rle.RuleT]:
        yield from super()._generate_rules(tech=tech)

        yield (
            _msk.Intersect((self.mask, self.well.mask)).width >= self.min_well_overlap
        )
        yield (
            self.well.mask.remove(self.mask).width >= self.min_well_enclosure
        )


class WaferWire(_WidthSpaceConductor):
    """WaferWire is representing the wire made from wafer material and normally
    isolated by LOCOS for old technlogies and STI (shallow-trench-isolation)
    or FINFET for newer/recent ones.
    The doping type is supposed the be determing by implant layers.

    Arguments:
        implant: the valid `Implant` layers for this primitive
        min_implant_enclosure: the minimum required enclosure by the implant
            over the waferwire. If a single enclosure is specified it is
            the spec for all the implants.
        implant_abut: wether to allow the abutment of two waferwire shapes
            of opposite type.
        allow_contactless_implant: wether to allow waferwire shapes without
            a contact. If True it is assumed that abutted shapes are on the same
            net.
        allow_in_substrate: wether to allow a waferwire shape that is not in a
            well. Some processes use wafers of a certain doping type; others
            need a well for all active devices.
        well: the well primitives valid for this WaferWire,
            It is assumed that WaferWire with implant type the same as the well
            connect to that well.
        min_well_enclosure: the minimum required enclosure of the WaferWire by
            the well. If only one value is given it is valid for all the wells.
        min_well_enclosure_same_type: allow to specify other enclosure for
            WaferWires with the same type as the well.
        min_substrate_enclosure: the minimum required enclosure of the WaferWire by
            the substrate with the substrate defined as any wafer region that is
            not covered by a well. If not specified the same value as
            min_well_enclosure is used.
        min_substrate_enclosure_same_type: allow to specify other enclosure for
            WaferWires with the same type as the well. If not specified the same value
            as min_well_enclosure_same_type is used.
        allow_well_crossing: wether it is allow for a WaferWire to go over a well
            boundary
        oxide: the list of valid oxide layers for this WaferWire. This can be empty.
        min_oxide_enclosure: the minimum required enclosure of the WaferWire by
            the oxide layer. If only one value is given it is valid for all the oxide
            layers.
        super_args: the argument for `_WidthSpacePrimitive` and `_DesignMaskPrimitive`
    """
    def __init__(self, *,
        implant: MultiT[Implant],
        min_implant_enclosure: MultiT[_prp.Enclosure],
        implant_abut: Union[str, MultiT[Implant]],
        allow_contactless_implant: bool,
        allow_in_substrate: bool,
        well: MultiT[Well],
        min_well_enclosure: MultiT[_prp.Enclosure],
        min_well_enclosure_same_type: OptMultiT[Optional[_prp.Enclosure]]=None,
        min_substrate_enclosure: Optional[_prp.Enclosure]=None,
        min_substrate_enclosure_same_type: Optional[_prp.Enclosure]=None,
        allow_well_crossing: bool,
        oxide: MultiT[Insulator]=(),
        min_oxide_enclosure: MultiT[Optional[_prp.Enclosure]]=None,
        **super_args
    ):
        self.allow_in_substrate = allow_in_substrate

        self.implant = implant = cast_MultiT(implant)
        for impl in implant:
            if isinstance(impl, Well):
                raise TypeError(f"well '{impl.name}' may not be part of implant")
        self.min_implant_enclosure = min_implant_enclosure = cast_MultiT_n(
            min_implant_enclosure, n=len(implant),
        )
        if isinstance(implant_abut, str):
            _conv: Dict[str, Tuple[Implant, ...]] = {
                "all": implant, "none": tuple()
            }
            if implant_abut not in _conv:
                raise ValueError(
                    "only 'all' or 'none' allowed for a string implant_abut"
                )
            implant_abut = _conv[implant_abut]
        else:
            implant_abut = cast_MultiT(implant_abut)
        for impl in implant_abut:
            if impl not in implant:
                raise ValueError(
                    f"implant_abut member '{impl.name}' not in implant list"
                )
        self.implant_abut = implant_abut
        self.allow_contactless_implant = allow_contactless_implant

        self.well = well = cast_MultiT(well)
        self.min_well_enclosure = min_well_enclosure = cast_MultiT_n(
            min_well_enclosure, n=len(well),
        )
        self.min_well_enclosure_same_type = cast_OptMultiT_n(
            min_well_enclosure_same_type, n=len(well),
        )
        if allow_in_substrate:
            if min_substrate_enclosure is None:
                if len(min_well_enclosure) == 1:
                    min_substrate_enclosure = min_well_enclosure[0]
                    if min_substrate_enclosure_same_type is not None:
                        raise TypeError(
                            "min_substrate_enclosure_same_type has to be 'None' "
                            "if min_substrate_enclosure is 'None'"
                        )
                    if self.min_well_enclosure_same_type is not None:
                        min_substrate_enclosure_same_type = \
                            self.min_well_enclosure_same_type[0]
                else:
                    raise TypeError(
                        "min_substrate_enclosure has be provided when providing "
                        "multiple wells"
                    )
        elif min_substrate_enclosure is not None:
            raise TypeError(
                "min_substrate_enclosure has to be 'None' if allow_in_substrate "
                "is 'False'"
            )
        self.allow_well_crossing = allow_well_crossing
        self.min_substrate_enclosure = min_substrate_enclosure
        self.min_substrate_enclosure_same_type = min_substrate_enclosure_same_type

        oxide = cast_MultiT(oxide)
        if (len(oxide) == 0) and (min_oxide_enclosure is None):
            min_oxide_enclosure = ()
        min_oxide_enclosure = cast_MultiT_n(min_oxide_enclosure, n=len(oxide))
        self.oxide = oxide
        self.min_oxide_enclosure = min_oxide_enclosure

        super().__init__(**super_args)

    def _generate_rules(self, *,
        tech: _tch.Technology,
    ) -> Iterable[_rle.RuleT]:
        yield from super()._generate_rules(tech=tech)

        substrate_mask = tech.substrate_prim.mask

        for i, impl in enumerate(self.implant):
            sd_mask_impl = _msk.Intersect((self.conn_mask, impl.mask)).alias(
                f"{self.conn_mask.name}:{impl.name}",
            )
            yield from (sd_mask_impl, _msk.Connect(self.conn_mask, sd_mask_impl))
            if (
                self.allow_in_substrate
                and (impl.type_.value == tech.base.type_.value)
            ):
                yield _msk.Connect(sd_mask_impl, substrate_mask)
            if impl not in self.implant_abut:
                yield _edg.MaskEdge(impl.mask).interact_with(self.mask).length == 0
            enc = self.min_implant_enclosure[i]
            yield self.mask.enclosed_by(impl.mask) >= enc
            for w in self.well:
                if impl.type_ == w.type_:
                    yield _msk.Connect(sd_mask_impl, w.mask)
        for implduo in combinations((impl.mask for impl in self.implant_abut), 2):
            yield _msk.Intersect(implduo).area == 0
        # TODO: allow_contactless_implant

        for i, w in enumerate(self.well):
            enc = self.min_well_enclosure[i]
            if enc.is_assymetric: # pragma: no cover
                raise NotImplementedError(
                    f"Asymmetric enclosure of WaferWire '{self.name}' "
                    f"by well '{w.name}'",
                )
            if self.min_well_enclosure_same_type is None:
                yield self.mask.enclosed_by(w.mask) >= enc
            else:
                enc2 = self.min_well_enclosure_same_type[i]
                if enc2 is None:
                    yield self.mask.enclosed_by(w.mask) >= enc
                else:
                    if enc2.is_assymetric: # pragma: no cover
                        raise NotImplementedError(
                            f"Asymmetric same type enclosure of WaferWire '{self.name}"
                            f"by well '{w.name}",
                        )
                    for ww in (
                        cast("_WaferWireIntersect", self.in_(impl))
                        for impl in filter(
                            # other type
                            lambda impl2: w.type_ != impl2.type_, self.implant,
                        )
                    ):
                        yield ww.mask.enclosed_by(w.mask) >= enc
                    for ww in (
                        cast("_WaferWireIntersect", self.in_(impl))
                        for impl in filter(
                            # same type
                            lambda impl2: w.type_ == impl2.type_, self.implant,
                        )
                    ):
                        yield ww.mask.enclosed_by(w.mask) >= enc2

        if self.min_substrate_enclosure is not None:
            if self.min_substrate_enclosure_same_type is None:
                yield (
                    self.mask.enclosed_by(substrate_mask)
                    >= self.min_substrate_enclosure
                )
            else:
                for ww in (
                    cast("_WaferWireIntersect", self.in_(impl)) for impl in filter(
                    # other type
                    lambda impl2: tech.base.type_.value != impl2.type_.value,
                    self.implant,
                )):
                    yield (
                        ww.mask.enclosed_by(substrate_mask)
                        >= self.min_substrate_enclosure
                    )
                for ww in (
                    cast("_WaferWireIntersect", self.in_(impl)) for impl in filter(
                    # same type
                    lambda impl2: tech.base.type_.value == impl2.type_.value,
                    self.implant,
                )):
                    yield (
                        ww.mask.enclosed_by(substrate_mask)
                        >= self.min_substrate_enclosure_same_type
                    )

        for i, ox in enumerate(self.oxide):
            enc = self.min_oxide_enclosure[i]
            if enc is not None:
                yield self.mask.enclosed_by(ox.mask) >= enc

        if not self.allow_well_crossing:
            mask_edge = _edg.MaskEdge(self.mask)
            yield from (
                mask_edge.interact_with(_edg.MaskEdge(w.mask)).length == 0
                for w in self.well
            )

    def in_(self, prim: MultiT[MaskPrimitiveT]) -> MaskPrimitiveT:
        return _WaferWireIntersect(waferwire=self, prim=prim)


class _WaferWireIntersect(_Intersect):
    """Intersect of WaferWire with one or more of it's implants, wells and
    oxides"""
    def __init__(self, *,
        waferwire: WaferWire, prim: MultiT[MaskPrimitiveT],
    ):
        ww_prims: Set[MaskPrimitiveT] = set(waferwire.implant)
        ww_prims.update(waferwire.well)
        ww_prims.update(waferwire.oxide)
        prim = cast_MultiT(prim)
        for p in prim:
            if p not in ww_prims:
                raise ValueError(
                    f"prim '{p.name}' not an implant, well or oxide layer for"
                    f" WaferWire '{waferwire.name}'"
                )
        self.waferwire = waferwire
        self.prim = prim

        super().__init__(prims=(waferwire, *prim))


class GateWire(_WidthSpaceConductor):
    """GateWire is a _WidthSpaceConductor that can act as the
    gate of a MOSFET.

    No extra arguments next to the `_WidthSpacePrimitive` and `_DesignMaskPrimitive`
    ones.
    """
    def __init__(self, **super_args):
        super().__init__(**super_args)


class MetalWire(_WidthSpaceConductor):
    """GateWire is a _WidthSpaceConductor that acts as an
    interconnect layer.

    No extra arguments next to the `_WidthSpacePrimitive` and `_DesignMaskPrimitive`
    ones.
    """
    def __init__(self, **super_args):
        super().__init__(**super_args)


class MIMTop(MetalWire):
    """MIMTop is a primitive to be used as the top of a MIM Capacitor
    """
    pass
class TopMetalWire(MetalWire):
    """TopMetalWire is a primitive for top metal layer. A top metal layer
    does not have to appear in the bottom list of a `Via`.
    """
    pass


ViaBottom = Union[WaferWire, GateWire, MetalWire, "Resistor"]
ViaTop = Union[MetalWire, "Resistor"]
class Via(_Conductor):
    """A Via layer is a layer that connect two conductor layer vertically.

    Arguments:
        width: the fixed width; only squares with this width are allowed
            on the Via layer.
        bottom: list of valid bottom primitives for this Via layer.
            These have to be `WaferWire`, `GateWire`, `MetalWire` or `Resistor`
            objects
        min_bottom_enclosure: the minimum required enclosure of the Via by
            the bottom layer. If only one value is given it is valid for all the
            bottom layers.
        top: list of valid bottom primitives for this Via layer.
            These have to be `WaferWire`, `GateWire`, `MetalWire` or `Resistor`
            objects
        min_bottom_enclosure: the minimum required enclosure of the Via by
            the top layer. If only one value is given it is valid for all the
            top layers.
        super_args: parameters for `_DesignMaskPrimitive`
    """
    # When drawing via and bottom or top is not specified by default the first layer
    # will be used if it is a MetalWire, otherwise it needs to be specified.
    def __init__(self, *,
        width: float, min_space: float,
        bottom: MultiT[ViaBottom], top: MultiT[ViaTop],
        min_bottom_enclosure: MultiT[_prp.Enclosure],
        min_top_enclosure: MultiT[_prp.Enclosure],
        **super_args,
    ):
        super().__init__(**super_args)

        self.bottom = bottom = cast_MultiT(bottom)
        self.min_bottom_enclosure = min_bottom_enclosure = cast_MultiT_n(
            min_bottom_enclosure, n=len(bottom),
        )
        for b in bottom:
            if isinstance(b, TopMetalWire):
                raise TypeError(
                    f"TopMetalWire '{b.name} not allowed as bottom of Via '{self.name}'",
                )
        self.top = top = cast_MultiT(top)
        self.min_top_enclosure = min_top_enclosure = cast_MultiT_n(
            min_top_enclosure, n=len(top),
        )
        self.width = width
        self.min_space = min_space

    def _generate_rules(self, *,
        tech: _tch.Technology,
    ) -> Iterable[_rle.RuleT]:
        yield from super()._generate_rules(tech=tech)

        yield from (
            self.mask.width == self.width,
            self.mask.space >= self.min_space,
            _msk.Connect((b.conn_mask for b in self.bottom), self.mask),
            _msk.Connect(self.mask, (b.conn_mask for b in self.top)),
        )
        for i in range(len(self.bottom)):
            bot_mask = self.bottom[i].mask
            enc = self.min_bottom_enclosure[i]
            yield self.mask.enclosed_by(bot_mask) >= enc
        for i in range(len(self.top)):
            top_mask = self.top[i].mask
            enc = self.min_top_enclosure[i]
            yield self.mask.enclosed_by(top_mask) >= enc

    @property
    def designmasks(self):
        yield from super().designmasks
        for conn in self.bottom + self.top:
            yield from conn.designmasks

    def in_(self, prim: MultiT[MaskPrimitiveT]) -> MaskPrimitiveT:
        return _ViaIntersect(via=self, prim=prim)


class _ViaIntersect(_Intersect):
    """Intersect of WaferWire with one or more of it's implants, wells and
    oxides"""
    def __init__(self, *,
        via: Via, prim: MultiT[MaskPrimitiveT],
    ):
        via_prims: Set[MaskPrimitiveT] = {*via.bottom, *via.top}
        prim = cast_MultiT(prim)
        for p in prim:
            if isinstance(p, _WaferWireIntersect):
                p = p.waferwire
            if p not in via_prims:
                raise ValueError(
                    f"prim '{p.name}' not a bottom or top layer for Via '{via.name}'"
                )
        self.via = via
        self.prin = prim

        super().__init__(prims=(via, *prim))


class PadOpening(_WidthSpaceConductor):
    """PadOpening is a layer representing an opening in the top layer in the
    processing of a semiconductor wafer.

    Typical application is for wirebonding, bumping for flip-chip or an RDL
    (redistribution) layer.

    Arguments:
        bottom: the MetalWire layer for which on top of which an opening in
            the isolation is made.
        min_bottom_enclsoure: the minimum enclosure of the `PadOpening` layer
            by the bottom layer.
        super_args: arguments for `WidthSpacePrimitive` and `_DesignMaskPrimitive`
    """
    def __init__(self, *,
        bottom: MetalWire, min_bottom_enclosure: _prp.Enclosure, **super_args,
    ):
        super().__init__(**super_args)

        if isinstance(bottom, TopMetalWire):
            raise TypeError(
                f"TopMetalWire '{bottom.name}' not allowed for PadOpening '{self.name}'",
            )
        self.bottom = bottom
        self.min_bottom_enclosure = min_bottom_enclosure

    def _generate_rules(self, *,
        tech: _tch.Technology,
    ) -> Iterable[_rle.RuleT]:
        yield from super()._generate_rules(tech=tech)

        yield (
            self.mask.enclosed_by(self.bottom.mask)
            >= self.min_bottom_enclosure
        )

    @property
    def designmasks(self):
        yield from super().designmasks
        yield from self.bottom.designmasks


# Import at end to avoid circular import problems
from .devices import Resistor
