# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
import abc
from typing import List, Dict, Optional, Union, Iterable, cast, overload

from . import (
    property_ as _prp, rule as _rle, mask as _msk, wafer_ as _wfr, geometry as _geo,
    primitive as _prm,
)


__all__ = ["Technology"]


class Technology(abc.ABC):
    """A `Technology` object is the representation of a semiconductor process.
    It's mainly a list of `_Primitive` objects with these primitives describing
    the capabilities of the technolgy.

    the `Technology` class is an abstract base class so subclasses need to
    implement some of the abstract methods defined in this base class.

    Subclasses need to overload the `__init__()` method and call the parent's
    `__init__()` with the list of the primitives for this technology. After this
    list has been passed to the super class's `__init__()` it is final and will
    be frozen.

    Next to the `__init__()` abstract method subclasses also need to define some
    abstract properties to define some properties of the technology. These are
    `name()`, `grid()`.
    """
    class ConnectionError(Exception):
        pass

    class _ComputedSpecs:
        """`Technology._ComputedSpecs` is a helper class that allow to compute
        some properties on a technology. This class should not be instantiated
        by user code by is access through the `computed` attribute of a `Technology`
        object.
        """
        def __init__(self, tech: "Technology"):
            self.tech = tech

        @overload
        def min_space(self,
            primitive1: "_prm.MaskPrimitiveT", primitive2: None=None, *,
            max_enclosure: bool=False, width: Optional[float]=None,
        ) -> float:
            ... # pragma: no cover
        @overload
        def min_space(self,
            primitive1: "_prm.PrimitiveT", primitive2: "_prm.PrimitiveT", *,
            max_enclosure: bool=False, width: None=None
        ) -> float:
            ... # pragma: no cover
        def min_space(self,
            primitive1: "_prm.PrimitiveT", primitive2: Optional["_prm.PrimitiveT"]=None, *,
            max_enclosure: bool=False, width: Optional[float]=None,
        ) -> float:
            """Compute the minimum space between one or two primitives. It will go
            over all the rules to determine the minimum space for the provided
            primitive.
            This function allows to compute the min_space on primitives that are
            derived from other primitives.

            It is also usable to derive more complex minimum spacing on WaferWire
            primitives. For exmaple, you can do
            `tech.computed.min_space(active.in_(nimplant), active.in_(pimplant))`
            the value is computed so that none of the implants drawn on the first
            waferwire is not overlapping with the one on the second. The enclosing
            layer is assumed to be drawn with minimal enclosure.

            Arguments:
                primitive1: the first primitive
                    if primitive2 is not given, the minimum space between shapes
                    on the primitive1 layer is returned.
                primitive2: the optional second primitive.
                    if specified the minimum space between shape on layer primitive1
                    and shapes on layer primitive2 is returned.
                max_enclosure: use maximum enclosure for derived primitives.
                    If one of the primitives is a derived primitive (for example WaferWire
                    in an implant) maximum enclosure value may be used to compute the
                    minimum space.
                width: width of the wire to compute min_space for
                    This will be used to lookup minimum space in a space table if
                    provided for a wire. primitive2 may not be specified when width is
                    specified and primitive1 may not be a derived primitive.
            """
            if width is not None:
                if primitive2 is not None:
                    raise TypeError(
                        "primitive2 may not be specified when width is specified",
                    )
                if not isinstance(primitive1, _prm.DesignMaskPrimitiveT):
                    raise TypeError(
                        "primitive1 may not be a derived Primitive when width is specified",
                    )

            def check_prim(prim: _prm.Spacing) -> bool:
                if primitive2 is None:
                    return (
                        (primitive1 in prim.primitives1)
                        and (prim.primitives2 is None)
                    )
                elif prim.primitives2 is not None:
                    return (
                        (
                            (primitive1 in prim.primitives1)
                            and (primitive2 in prim.primitives2)
                        )
                        or (
                            (primitive1 in prim.primitives2)
                            and (primitive2 in prim.primitives1)
                        )
                    )
                else:
                    return False

            spaces = list(
                p.min_space for p in filter(
                    check_prim, self.tech.primitives.__iter_type__(_prm.Spacing),
                )
            )
            if (primitive2 is None) or (primitive1 == primitive2):
                try:
                    space = cast(_prm.WidthSpacePrimitiveT, primitive1).min_space
                except AttributeError: # pragma: no cover
                    pass
                else:
                    spaces.append(space)
                if width is not None:
                    space = None
                    table = cast(_prm.WidthSpacePrimitiveT, primitive1).space_table
                    if table is not None:
                        for spec, value in table:
                            if not isinstance(spec, (int, float)):
                                spec = spec[0]
                            if width > (spec - _geo.epsilon):
                                spaces.append(value)
                if isinstance(primitive1, _prm.InsidePrimitiveT):
                    prim = primitive1.prim
                    assert isinstance(prim, (_prm.WidthSpacePrimitiveT, _prm.Via))
                    spaces.append(prim.min_space)

            if (
                isinstance(primitive1, _prm.InsidePrimitiveT)
                and isinstance(primitive2, _prm.DesignMaskPrimitiveT)
            ):
                (primitive1, primitive2) = (primitive2, primitive1)

            def get_enc(*, ww: _prm.WaferWire, prim: _prm.MaskPrimitiveT):
                enc = None
                if prim in ww.implant:
                    idx = ww.implant.index(prim)
                    enc = ww.min_implant_enclosure[idx]
                elif prim in ww.well:
                    idx = ww.well.index(prim)
                    enc = ww.min_well_enclosure[idx]
                elif prim in ww.oxide:
                    idx = ww.oxide.index(prim)
                    enc = ww.min_oxide_enclosure[idx]
                else: # pragma: no cover
                    raise RuntimeError(
                        "Internal error: unsupported enclosed layer"
                        f" '{prim.name}' for '{p2.name}'")

                return (
                    None if enc is None
                    else enc.min() if not max_enclosure
                    else enc.max()
                )

            if isinstance(primitive1, _prm.DesignMaskPrimitiveT):
                if isinstance(primitive2, _prm.InsidePrimitiveT):
                    p2 = primitive2.prim
                    filtin2 = tuple(
                        p
                        for p in primitive2.in_
                        if not isinstance(p, _prm.Marker)
                    )
                    try:
                        s = self.min_space(primitive1, p2)
                    except: # pragma: no cover
                        pass
                    else:
                        spaces.append(s)

                    if (primitive1 == p2) and isinstance(p2, _prm.WaferWire):
                        for prim in filtin2:
                            enc = get_enc(ww=p2, prim=prim)
                            if enc is not None:
                                try:
                                    s = self.min_space(primitive1, prim)
                                except:
                                    pass
                                else:
                                    spaces.append(enc + s)
            elif (
                isinstance(primitive1, _prm.InsidePrimitiveT)
                and isinstance(primitive2, _prm.InsidePrimitiveT)
            ):
                p1 = primitive1.prim
                filtin1 = tuple(
                    p
                    for p in primitive1.in_
                    if not isinstance(p, _prm.Marker)
                )
                p2 = primitive2.prim
                filtin2 = tuple(
                    p
                    for p in primitive2.in_
                    if not isinstance(p, _prm.Marker)
                )

                spaces.extend((
                    self.min_space(p1, primitive2),
                    self.min_space(p2, primitive1),
                ))

                e1s: List[float] = []
                e2s: List[float] = []
                if isinstance(p1, _prm.WaferWire):
                    for prim in filtin1:
                        enc = get_enc(ww=p1, prim=prim)
                        if enc is not None:
                            e1s.append(enc)
                if isinstance(p2, _prm.WaferWire):
                    for prim in filtin2:
                        enc = get_enc(ww=p2, prim=prim)
                        if enc is not None:
                            e2s.append(enc)
                if (len(e1s) > 0) and (len(e2s) > 0):
                    spaces.append(max(e1s) + max(e2s))

            try:
                return max(spaces)
            except ValueError:
                raise AttributeError(
                    f"min_space between {primitive1} and {primitive2} not found",
                )

        @overload
        def min_width(self,
            primitive: Union["_prm.WidthSpacePrimitiveT", "_prm.InsidePrimitiveT"], *,
            up: bool=False, down: bool=False, min_enclosure: bool=False,
        ) -> float:
            ... # pragma: no cover
        @overload
        def min_width(self, primitive: "_prm.Via") -> float:
            ... # pragma: no cover
        def min_width(self,
            primitive: Union[
                "_prm.WidthSpacePrimitiveT", "_prm.Via", "_prm.InsidePrimitiveT",
            ], *,
            up: bool=False, down: bool=False, min_enclosure: bool=False,
        ) -> float:
            """Compute the minimum width of a primitive.
            This method allows to take into account via enclosure rules to compute
            minimum width but still be contacted through a via.

            Arguments:
                primitive: the primitive
                up: wether it needs to take a connection from the top with a Via
                    into account.
                down: wether it needs to take a connection from the bottom with a Via
                    into account.
                min_enclosure: if True it will take the minimum value minimum value
                    of the relevant via enclosure rule; otherwise the maximum value.
            """
            if isinstance(primitive, _prm.WidthSpacePrimitiveT):
                def wupdown(via):
                    if up and (primitive in via.bottom):
                        idx = via.bottom.index(primitive)
                        enc = via.min_bottom_enclosure[idx]
                        w = via.width
                    elif down and (primitive in via.top):
                        idx = via.top.index(primitive)
                        enc = via.min_top_enclosure[idx]
                        w = via.width
                    else:
                        enc = _prp.Enclosure(0.0)
                        w = 0.0

                    enc = enc.min() if min_enclosure else enc.max()
                    return w + 2*enc

                return max((
                    primitive.min_width,
                    *(wupdown(via) for via in self.tech.primitives.__iter_type__(_prm.Via)),
                ))
            elif isinstance(primitive, _prm.Via):
                return primitive.width
            elif isinstance(primitive, _prm.InsidePrimitiveT):
                from itertools import combinations

                main = primitive.prim
                assert isinstance(main, (_prm.WidthSpacePrimitiveT, _prm.InsidePrimitiveT))
                mws = tuple(self.tech.primitives.__iter_type__(_prm.MinWidth))

                ws = [self.min_width(
                    primitive=main, up=up, down=down, min_enclosure=min_enclosure,
                )]
                for n in range(len(primitive.in_)):
                    for in2 in combinations(primitive.in_, n + 1):
                        ins = _prm._derived._InsidePrimitive(prim=main, in_=in2)
                        for mw in mws:
                            if mw.prim == ins:
                                ws.append(mw.min_width)
                return max(ws)
            else:
                raise TypeError("Wrong type for primitive")

        def min_pitch(self, primitive: "_prm.WidthSpacePrimitiveT", *,
            up: bool=False, down: bool=False, min_enclosure: bool=False,
        ) -> float:
            """Compute the minimum pitch of a primitive.
            It's the minimum width plus the minimum space.

            Arguments:
                primitive: the primitive
                up: wether it needs to take a connection from the top with a Via
                    into account.
                down: wether it needs to take a connection from the bottom with a Via
                    into account.
                min_enclosure: if True it will take the minimum value minimum value
                    of the relevant via enclosure rule; otherwise the maximum value.
            """
            w = self.min_width(primitive, up=up, down=down, min_enclosure=min_enclosure)
            return w + primitive.min_space

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """property with the name of the technology"""
        ... # pragma: no cover
    @property
    @abc.abstractmethod
    def grid(self) -> float:
        """property with the minimum grid of the technology

        Optionally primitives may define a bigger grid for their shapes.
        """
        ... # pragma: no cover

    @abc.abstractmethod
    def __init__(self, *, primitives: "_prm.Primitives"):
        self._primitives = primitives

        # primitives needs to contain exectly one Base primitive which
        # is always called base
        try:
            base = primitives.base
        except:
            raise ValueError("A technology needs exactly one 'Base` primitive")
        else:
            if not isinstance(base, _prm.Base):
                raise ValueError("A technology needs exactly one 'Base` primitive")

        wells = tuple(self._primitives.__iter_type__(_prm.Well))
        if not wells:
            self._substrate_prim = self.base
        else:
            self._substrate_prim = self.base.remove(wells).alias(f"substrate:{self.name}")

        self._build_interconnect()
        self._build_rules()

        primitives._freeze_()

        self.computed = self._ComputedSpecs(self)

    def is_ongrid(self, v: float, mult: int=1) -> bool:
        """Returns wether a value is on grid or not.

        Arguments:
            w: value to check
            mult: value has to be on `mult*grid`
        """
        g = mult*self.grid
        ng = round(v/g)
        return abs(v - ng*g) < _geo.epsilon

    @overload
    def on_grid(self,
        dim: float, *, mult: int=1, rounding: str="nearest",
    ) -> float:
        ... # pragma: no cover
    @overload
    def on_grid(self,
        dim: _geo.Point, *, mult: int=1, rounding: str="nearest",
    ) -> _geo.Point:
        ... # pragma: no cover
    def on_grid(self,
        dim: Union[float, _geo.Point], *, mult: int=1, rounding: str="nearest",
    ) -> Union[float, _geo.Point]:
        """Compute a value on grid from a given value.

        Arguments:
            dim: value to put on grid
            mult: value will be put on `mult*grid`
            rounding: how to round the value
                Has to be one of "floor", "nearest", "ceiling"; "nearest" is the
                default.
        """
        if isinstance(dim, _geo.Point):
            return _geo.Point(
                x=self.on_grid(dim.x, mult=mult, rounding=rounding),
                y=self.on_grid(dim.y, mult=mult, rounding=rounding),
            )
        return _geo.coord_on_grid(coord=dim, grid=mult*self.grid, rounding=rounding)

    @property
    def base(self) -> "_prm.Base":
        return cast(_prm.Base, self.primitives.base)

    @property
    def dbu(self) -> float:
        """Returns database unit compatible with technology grid. An exception is
        raised if the technology grid is not a multuple of 10pm.

        This method is specifically for use to export to format that use the dbu.
        """
        igrid = int(round(1e6*self.grid))
        assert (igrid%10) == 0
        if (igrid%100) != 0:
            return 1e-5
        elif (igrid%1000) != 0:
            return 1e-4
        else:
            return 1e-3

    def gridunit(self, dim: float) -> int:
        """Returns number of grid units for given dimension.

        This converts dimension into integer value which is easier to compare
        with other values.

        The method will raise an exception if the dimension is not on grid.
        """
        if ((dim + _geo.epsilon)%self.grid) > 2*_geo.epsilon:
            raise ValueError(f"dim '{dim}' is not on grid")
        return round((dim + _geo.epsilon)//self.grid)

    def _build_interconnect(self) -> None:
        prims = self._primitives

        neworder = []
        def add_prims(prims2):
            for prim in prims2:
                idx = prims.index(prim)
                if idx not in neworder:
                    neworder.append(idx)

        def get_name(prim):
            return prim.name

        # base
        add_prims((prims.base,))

        # set that are build up when going over the primitives
        # bottomwires: primitives that still need to be bottomconnected by a via
        bottomwires = set()
        # implants: used implant not added yet
        implants = set() # Implants to add
        markers = set() # Markers to add
        # the wells, fixed
        deepwells = set(prims.__iter_type__(_prm.DeepWell))
        wells = set(prims.__iter_type__(_prm.Well))

        # Wells are the first primitives in line
        add_prims(sorted(deepwells, key=get_name))
        add_prims(sorted(wells, key=get_name))

        # process waferwires
        waferwires = set(prims.__iter_type__(_prm.WaferWire))
        bottomwires.update(waferwires) # They also need to be connected
        conn_wells = set()
        for wire in waferwires:
            implants.update((*wire.implant, *wire.well))
            conn_wells.update(wire.well)
        if conn_wells != wells:
            raise _prm.UnconnectedPrimitiveError(primitive=(wells - conn_wells).pop())

        # process gatewires
        bottomwires.update(prims.__iter_type__(_prm.GateWire))

        # Already add implants that are used in the waferwires
        add_prims(sorted(implants, key=get_name))
        implants = set()

        # Add the oxides
        for ww in waferwires:
            add_prims(sorted(ww.oxide, key=get_name))

        # process vias
        vias = set(prims.__iter_type__(_prm.Via))

        def allwires(wire):
            if isinstance(wire, _prm.Resistor):
                yield from allwires(wire.wire)
                yield from wire.indicator
            try:
                yield wire.pin # type: ignore
            except AttributeError:
                pass
            try:
                yield wire.blockage # type: ignore
            except AttributeError:
                pass
            yield wire

        connvias = set(filter(lambda via: any(w in via.bottom for w in bottomwires), vias))
        if connvias:
            viatops = set()
            while connvias:
                viabottoms = set()
                viatops = set()
                for via in connvias:
                    viabottoms.update(via.bottom)
                    viatops.update(via.top)

                noconn = tuple(filter(
                    # MIMTop does not need to be connected from bottom
                    lambda l: not isinstance(l, _prm.MIMTop),
                    bottomwires - viabottoms,
                ))
                if noconn:
                    raise Technology.ConnectionError(
                        f"wires ({', '.join(wire.name for wire in noconn)})"
                        " not in bottom list of any via"
                    )

                for bottom in viabottoms:
                    add_prims(allwires(bottom))

                bottomwires -= viabottoms
                bottomwires.update(viatops)

                vias -= connvias
                connvias = set(filter(lambda via: any(w in via.bottom for w in bottomwires), vias))
            # Add the top layers of last via to the prims
            for top in viatops:
                add_prims(allwires(top))

        if vias:
            raise Technology.ConnectionError(
                f"vias ({', '.join(via.name for via in vias)}) have no connection to"
                " a technology bottom wire"
            )

        # Add via and it's blockage layers
        vias = tuple(prims.__iter_type__(_prm.Via))
        add_prims(prim.blockage for prim in filter(
            lambda v: hasattr(v, "blockage"),
            vias
        ))
        # Now add all vias
        add_prims(vias)

        # process mosfets
        mosfets = set(prims.__iter_type__(_prm.MOSFET))
        gates = {mosfet.gate for mosfet in mosfets}
        allgates = set(prims.__iter_type__(_prm.MOSFETGate))
        if gates != allgates:
            diff = allgates - gates
            if diff:
                raise _prm.UnusedPrimitiveError(primitive=diff.pop())
            raise RuntimeError("Unhandled error condition") # pragma: no cover
        actives = {gate.active for gate in gates}
        polys = {gate.poly for gate in gates}
        for mosfet in mosfets:
            implants.update(mosfet.implant)
            if mosfet.well is not None:
                implants.add(mosfet.well)
            if mosfet.gate.inside is not None:
                markers.update(mosfet.gate.inside)
        # Each well and the substrate may either contain only transistors without
        # n/p type implants or all with n/p type implants
        # store first mosfet in a well in wellmosfet, check nect mosfets if they match
        wellmosfet: Dict[Optional[_prm.Well], _prm.MOSFET] = {}
        for mos in mosfets:
            well = mos.well
            if well not in wellmosfet:
                wellmosfet[well] = mos
            else:
                prevmos = wellmosfet[well]
                if prevmos.has_typeimplant != mos.has_typeimplant:
                    name = f"same well '{well.name}'" if well is not None else "substrate"
                    raise ValueError(
                        f"MOSFETs '{prevmos.name}' and '{mos.name}' with and without type implant"
                        f" in {name}"
                    )

        # Add Substrate markers to list, they don't need to be included as marker in another
        # primitive
        markers.update(prims.__iter_type__(_prm.SubstrateMarker))

        add_prims((
            *sorted(implants, key=get_name),
            *sorted(actives, key=get_name), *sorted(polys, key=get_name),
            *sorted(markers, key=get_name), *sorted(gates, key=get_name),
            *sorted(mosfets, key=get_name),
        ))
        implants = set()
        markers = set()

        # proces pad openings
        padopenings = set(prims.__iter_type__(_prm.PadOpening))
        viabottoms = set()
        for padopening in padopenings:
            add_prims(allwires(padopening.bottom))
        add_prims(padopenings)
        add_prims((padopening.pin for padopening in padopenings if hasattr(padopening, "pin")))

        # process top metal wires
        add_prims(prims.__iter_type__(_prm.TopMetalWire))

        # process resistors
        resistors = set(prims.__iter_type__(_prm.Resistor))
        for resistor in resistors:
            markers.update(resistor.indicator)
            implants.update(resistor.implant)

        # process capacitors
        mimtops = set(prims.__iter_type__(_prm.MIMTop))
        mimcaps = tuple(prims.__iter_type__(_prm.MIMCapacitor))
        usedtops = set(c.top for c in mimcaps)
        unusedtops = mimtops - usedtops
        if unusedtops:
            s_tops = ",".join(f"'{top}.name'" for top in unusedtops)
            raise _prm.UnusedPrimitiveError(
                primitive=unusedtops.pop(), msg=f"MIMTops {s_tops} not used in MIMCapacitor",
            )

        # process diodes
        diodes = set(prims.__iter_type__(_prm.Diode))
        for diode in diodes:
            markers.update(diode.indicator)

        # process bipolars
        bipolars = set(prims.__iter_type__(_prm.Bipolar))
        for bipolar in bipolars:
            markers.update(bipolar.indicator)

        # extra rules
        rules = set(prims.__iter_type__(_prm.RulePrimitiveT))

        add_prims((*implants, *markers, *resistors, *mimcaps, *diodes, *bipolars, *rules))

        # process auxiliary
        def aux_key(aux: _prm.Auxiliary) -> str:
            return aux.name
        add_prims(sorted(prims.__iter_type__(_prm.Auxiliary), key=aux_key))

        # reorder primitives
        unused = set(range(len(prims))) - set(neworder)
        if unused:
            raise _prm.UnusedPrimitiveError(primitive=prims[unused.pop()])
        prims._reorder_(neworder=neworder)

    def _build_rules(self) -> None:
        prims = self._primitives
        self._rules = rules = _rle.Rules()

        # grid
        rules += _wfr._wafer_base.grid == self.grid

        # Generate the rule but don't add them yet.
        for prim in prims:
            prim._derive_rules(self)

        # First add substrate alias if needed. This will only be clear
        # after the rules have been generated.
        sub_mask = self.substrate_prim.mask
        if isinstance(sub_mask, _msk._MaskAlias):
            self._rules += sub_mask
        if sub_mask != _wfr.wafer:
            self._rules += _msk.Connect(sub_mask, _wfr.wafer)

        # Now we can add the rules
        for prim in prims:
            self._rules += prim.rules

        rules._freeze_()

    @property
    def substrate_prim(self) -> "_prm.MaskPrimitiveT":
        """Property representing the substrate of the technology; it's defined as the area
        that is outside any of the wells of the technology.

        As this value needs access to the list of wells it's only available afcer the
        technology has been initialized and is not available during run of the `_init()`
        method.
        """
        if not hasattr(self, "_substrate_prim"):
            raise AttributeError("substrate may not be accessed during object initialization")
        return self._substrate_prim

    @property
    def rules(self) -> Iterable[_rle.RuleT]:
        """Return all the rules that are derived from the primitives of the technology."""
        return self._rules

    @property
    def primitives(self) -> "_prm.Primitives":
        """Return the primitives of the technology."""
        return self._primitives

    @property
    def submasks(self) -> Iterable[_msk.MaskT]:
        """Return all the `MaskT` objects defined by the primitives of the technology.

        The property makes sure there are no duplicates in the returned iterable.
        """
        masks = set()
        for prim in self._primitives:
            for mask in prim.submasks:
                if mask not in masks:
                    yield mask
                    masks.add(mask)

    @property
    def designmasks(self) -> Iterable[_msk.DesignMask]:
        """Return all the `DesignMask` objects defined by the primitives of the technology.

        The property makes sure there are no duplicates in the returned iterable.
        """
        return (mask for mask in self.submasks if isinstance(mask, _msk.DesignMask))
