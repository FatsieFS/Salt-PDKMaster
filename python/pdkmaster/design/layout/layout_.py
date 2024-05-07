# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
import abc
from typing import Iterable, Union, Optional, Any, overload

from ... import _util
from ...typing import MultiT
from ...technology import mask as _msk, geometry as _geo, net as _net, primitive as _prm
from .. import circuit as _ckt
# also imports at end of file to avoid circular import problems


__all__ = ["LayerT", "DesignLayerT", "LayoutT"]


# Type aliases
LayerT = Union[_msk.MaskT, _prm.MaskPrimitiveT]
DesignLayerT = Union[_msk.DesignMask, _prm.DesignMaskPrimitiveT]


class _SubLayout(abc.ABC):
    """Internal `_Layout` support class"""
    @abc.abstractmethod
    def __init__(self):
        ... # pragma: no cover

    @property
    @abc.abstractmethod
    def polygons(self) -> Iterable[_geo.MaskShape]:
        ... # pragma: no cover

    @abc.abstractmethod
    def dup(self) -> "_SubLayout":
        ... # pragma: no cover

    @abc.abstractmethod
    def move(self, *,
        dxy: _geo.Point, move_context: Optional[_geo.MoveContext]=None,
    ) -> None:
        ... # pragma: no cover

    @abc.abstractmethod
    def moved(self, *,
        dxy: _geo.Point, move_context: Optional[_geo.MoveContext]=None,
    ) -> "_SubLayout":
        ... # pragma: no cover

    @abc.abstractmethod
    def rotate(self, *,
        rotation: _geo.Rotation, rot_context: Optional[_geo.RotationContext]=None,
    ) -> None:
        ... # pragma: no cover

    @abc.abstractmethod
    def rotated(self, *,
        rotation: _geo.Rotation, rot_context: Optional[_geo.RotationContext]=None,
    ) -> "_SubLayout":
        ... # pragma: no cover

    @property
    @abc.abstractmethod
    def _hier_strs_(self) -> Iterable[str]:
        ... # pragma: no cover


class _MaskShapesSubLayout(_SubLayout):
    """Object representing the sublayout of a net consisting of geometry._Shape
    objects.

    Arguments:
        net: The net of the SubLayout
            `None` value represents no net for the shapes.
        shapes: The maskshapes on the net.

    API Notes:
        * This is internal _Layout support class and should be used in user code.
    """
    def __init__(self, *, net: Optional[_net.NetT], shapes: _geo.MaskShapes):
        self._net = net
        self._shapes = shapes

    @property
    def net(self) -> Optional[_net.NetT]:
        return self._net
    @property
    def shapes(self) -> _geo.MaskShapes:
        return self._shapes

    @property
    def polygons(self) -> Iterable[_geo.MaskShape]:
        yield from self.shapes

    def add_shape(self, *, shape: _geo.MaskShape) -> None:
        self._shapes += shape

    def move(self, *,
        dxy: _geo.Point, move_context: Optional[_geo.MoveContext]=None,
    ) -> None:
        self._shapes = self.shapes.moved(dxy=dxy, context=move_context)

    def moved(self, *,
        dxy: _geo.Point, move_context: Optional[_geo.MoveContext]=None,
    ) -> "_MaskShapesSubLayout":
        return _MaskShapesSubLayout(
            net=self.net, shapes=self.shapes.moved(dxy=dxy, context=move_context),
        )

    def rotate(self, *,
        rotation: _geo.Rotation, rot_context: Optional[_geo.RotationContext]=None,
    ) -> None:
        self.shapes.rotate(rotation=rotation, context=rot_context)

    def rotated(self, *,
        rotation: _geo.Rotation, rot_context: Optional[_geo.RotationContext]=None,
    ) -> "_MaskShapesSubLayout":
        return _MaskShapesSubLayout(
            net=self.net,
            shapes=self.shapes.rotated(rotation=rotation, context=rot_context),
        )

    def dup(self) -> "_MaskShapesSubLayout":
        return _MaskShapesSubLayout(
            net=self.net, shapes=_geo.MaskShapes(self.shapes),
        )

    @property
    def _hier_strs_(self) -> Iterable[str]:
        yield f"MaskShapesSubLayout net={self.net}"
        for ms in self.shapes:
            yield "  " + str(ms)

    def __hash__(self) -> int:
        return hash((self.net, self.shapes))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _MaskShapesSubLayout):
            return (self.net == other.net) and (self.shapes == other.shapes)
        else:
            return False


class _InstanceSubLayout(_SubLayout):
    """Internal `_Layout` support class"""
    def __init__(self, *,
        inst: _ckt._CellInstance, origin: _geo.Point,
        layoutname: Optional[str], rotation: _geo.Rotation,
    ):
        self.inst = inst
        self.origin = origin
        self.rotation = rotation
        cell = inst.cell

        if layoutname is None:
            try:
                # Create default layout
                cell.layout
            except:
                raise ValueError(
                    f"Cell '{cell.name}' has no default layout and no layoutname"
                    " was specified"
                )
        else:
            if layoutname not in cell._layouts.keys():
                raise ValueError(
                    f"Cell '{cell.name}' has no layout named '{layoutname}'"
                )
        self.layoutname = layoutname
        # layout is a property and will only be looked up the first time it is accessed.
        # This is to support cell with delayed layout generation.
        self._layout = None

    @property
    def layout(self) -> "LayoutT":
        if self._layout is None:
            l: "_Layout" = (
                self.inst.cell._layouts[self.layoutname].layout
                if self.layoutname is not None
                else self.inst.cell.layout
            )
            self._layout = l.rotated(rotation=self.rotation).moved(dxy=self.origin)

        return self._layout

    @property
    def boundary(self) -> Optional[_geo._Rectangular]:
        l = (
            self.inst.cell._layouts[self.layoutname].layout
            if self.layoutname is not None
            else self.inst.cell.layout
        )
        if l.boundary is None:
            return None
        else:
            return l.boundary.rotated(rotation=self.rotation) + self.origin

    @property
    def polygons(self) -> Iterable[_geo.MaskShape]:
        yield from self.layout.polygons

    def dup(self) -> "_InstanceSubLayout":
        return _InstanceSubLayout(
            inst=self.inst, origin=self.origin, layoutname=self.layoutname,
            rotation=self.rotation,
        )

    def move(self, *,
        dxy: _geo.Point, move_context: Optional[_geo.MoveContext]=None,
    ) -> None:
        self.origin += dxy
        self._layout = None

    def moved(self, *,
        dxy: _geo.Point, move_context: Optional[_geo.MoveContext]=None,
    ) -> "_InstanceSubLayout":
        orig = self.origin + dxy
        return _InstanceSubLayout(
            inst=self.inst, origin=orig, layoutname=self.layoutname, rotation=self.rotation,
        )

    def rotate(self, *,
        rotation: _geo.Rotation, rot_context: Optional[_geo.RotationContext]=None,
    ) -> None:
        self.origin = rotation*self.origin
        self.rotation *= rotation

    def rotated(self, *,
        rotation: _geo.Rotation, rot_context: Optional[_geo.RotationContext]=None,
    ) -> "_InstanceSubLayout":
        p = rotation*self.origin
        rot = rotation*self.rotation

        return _InstanceSubLayout(
            inst=self.inst, origin=p, layoutname=self.layoutname, rotation=rot,
        )

    @property
    def _hier_strs_(self) -> Iterable[str]:
        yield f"_InstanceSubLayout inst={self.inst}, origin={self.origin}, rot={self.rotation}"
        for s in self.layout._hier_strs_:
            yield "  " + s


class _SubLayouts(_util.ExtendedList[_SubLayout]):
    """Internal `_Layout` support class"""
    def __init__(self, iterable: MultiT[_SubLayout]=tuple()):
        if isinstance(iterable, _SubLayout):
            super().__init__((iterable,))
        else:
            super().__init__(iterable)

            nets = tuple(sl.net for sl in self.__iter_type__(_MaskShapesSubLayout))
            if len(nets) != len(set(nets)):
                raise ValueError("Multiple `MaskShapesSubLayout` for same net")

    def dup(self) -> "_SubLayouts":
        return _SubLayouts(l.dup() for l in self)

    def __iadd__(self, other_: MultiT[_SubLayout]) -> "_SubLayouts":
        other: Iterable[_SubLayout]
        if isinstance(other_, _SubLayout):
            other = (other_,)
        else:
            other = tuple(other_)

        # Now try to add to other sublayouts
        def add2other(other_sublayout):
            if isinstance(other_sublayout, _MaskShapesSubLayout):
                for sublayout in self.__iter_type__(_MaskShapesSubLayout):
                    if sublayout.net == other_sublayout.net:
                        for shape in other_sublayout.shapes:
                            sublayout.add_shape(shape=shape)
                        return True
                else:
                    return False
            elif not isinstance(other_sublayout, _InstanceSubLayout): # pragma: no cover
                raise RuntimeError("Internal error")
        other = tuple(filter(lambda sl: not add2other(sl), other))

        if other:
            # Append remaining sublayouts
            self.extend(sl.dup() for sl in other)
        return self

    def __add__(self, other: MultiT[_SubLayout]) -> "_SubLayouts":
        ret = self.dup()
        ret += other
        return ret


class _Layout:
    """A `_Layout` object contains the shapes making up the layout of a design.
    Contrary to other EDA layout tools all shapes are put on a net or are netless.
    Netless are only allowed on mask derived from certain primitives.

    `LayoutFactory.new_layout()` needs to be used to generate new layouts.

    Attributes:
        fab: the factory with which this _layout is created
        sublayouts: the sublayouts making up this layout
        boundary: optional boundary of this layout
    """
    def __init__(self, *,
        fab: "LayoutFactory",
        sublayouts: _SubLayouts, boundary: Optional[_geo._Rectangular]=None,
    ):
        self.fab = fab
        self._sublayouts = sublayouts
        self.boundary = boundary

    @property
    def polygons(self) -> Iterable[_geo.MaskShape]:
        """All the `MaskShape` polygons of this layout.

        Typically use case is exporting to a format that has no net information.
        """
        for sublayout in self._sublayouts:
                yield from sublayout.polygons

    def _net_sublayouts(self, *,
        net: Optional[_net.NetT], depth: Optional[int],
    ) -> Iterable[_MaskShapesSubLayout]:
        for sl in self._sublayouts:
            if isinstance(sl, _InstanceSubLayout):
                if depth != 0:
                    if net is None:
                        yield from sl.layout._net_sublayouts(
                            net=None,
                            depth=(None if depth is None else (depth - 1)),
                        )
                    else:
                        assert isinstance(net, _ckt._CircuitNet)
                        for port in net.childports:
                            if (
                                isinstance(port, _ckt._InstanceNet)
                                and (port.inst == sl.inst)
                            ):
                                yield from sl.layout._net_sublayouts(
                                    net=port.net,
                                    depth=(None if depth is None else (depth - 1)),
                                )
            elif isinstance(sl, _MaskShapesSubLayout):
                if (net is None) or (net == sl.net):
                    yield sl
            else: # pragma: no cover
                raise AssertionError("Internal error")

    def filter_polygons(self, *,
        net: Optional[_net.NetT]=None, mask: Optional[_msk.MaskT]=None,
        split: bool=False, depth: Optional[int]=None,
    ) -> Iterable[_geo.MaskShape]:
        """Return polygons in the layout matching the given criteria.

        Arguments:
            net: only return polygons on this net.
                If net is `None` it will return polygons on all nets.
                Currently there is no way to only get shapes not on a net.
            mask: only return polygons on this mask
                If mask is `None` it will return polygons for all masks.
            split: whether to split up into ``_PointsShape`` object.
            depth: the depth for which to return shapes.
                0 means only polygons on top level, 1 includes top level of
                instantiated cells, and so on.
                Shape will be returned taking into account the origin of the cell
                placements; e.g. coordinates of shapes is as seen in the top
                level.
        """
        for sl in self._net_sublayouts(net=net, depth=depth):
            assert isinstance(sl, _MaskShapesSubLayout)
            if mask is None:
                shapes = sl.shapes
            else:
                shapes = filter(lambda sh: sh.mask == mask, sl.shapes)
            if not split:
                yield from shapes
            else:
                for shape in shapes:
                    for shape2 in shape.shape.pointsshapes:
                        yield _geo.MaskShape(mask=shape.mask, shape=shape2)

    def dup(self) -> "LayoutT":
        """Create a duplication of a layout."""
        return _Layout(
            fab=self.fab,
            sublayouts=_SubLayouts(sl.dup() for sl in self._sublayouts),
            boundary=self.boundary,
        )

    def bounds(self, *,
        mask: Optional[_msk.MaskT]=None, net: Optional[_net.NetT]=None,
        depth: Optional[int]=None,
    ) -> _geo.Rect:
        """Return the rectangle enclosing selected shapes; filtering of the
        shapes is done based on the given arguments.

        Arguments:
            mask: only shapes on this mask are selected
            net: only shapes on this net are selected
            depth: when specified only shapes until a certain hierarchy depth
                are selected.
        """
        boundslist = tuple(
            mp.bounds
            for mp in self.filter_polygons(net=net, mask=mask, depth=depth)
        )
        return _geo.Rect(
            left=min(bds.left for bds in boundslist),
            bottom=min(bds.bottom for bds in boundslist),
            right=max(bds.right for bds in boundslist),
            top=max(bds.top for bds in boundslist),
        )

    def __iadd__(self, other: Union["LayoutT", _SubLayout, _SubLayouts]) -> "LayoutT":
        if self._sublayouts._frozen_:
            raise ValueError("Can't add sublayouts to a frozen 'Layout' object")

        self._sublayouts += (
            other._sublayouts if isinstance(other, _Layout) else other
        )

        return self

    @overload
    def add_primitive(self, prim: _prm.PrimitiveT, *,
        origin: Optional[_geo.Point]=None, x: None=None, y: None=None,
        rotation: _geo.Rotation=_geo.Rotation.R0,
        **prim_params,
    ) -> "LayoutT":
        ... # pragma: no cover
    @overload
    def add_primitive(self, prim: _prm.PrimitiveT, *,
        origin: None=None, x: float, y: float,
        rotation: _geo.Rotation=_geo.Rotation.R0,
        **prim_params,
    ) -> "LayoutT":
        ... # pragma: no cover
    def add_primitive(self, prim: _prm.PrimitiveT, *,
        origin: Optional[_geo.Point]=None,
        x: Optional[float]=None, y: Optional[float]=None,
        rotation: _geo.Rotation=_geo.Rotation.R0,
        **prim_params,
    ) -> "LayoutT":
        """Add the layout for a primitive to a layout. It uses the layout
        generated with `_Layout.layout_primitive()` and places it in the current
        layout at a specified location and with a specified rotation.

        Arguments:
            prim: the primitive for which the generate and place the layout
            prim_params: the parameters for the primitive
                This is passed to `_Layout.layout_primitive()`.
            origin or x, y: origin where to place the primitive layout
            rotation: the rotation to apply on the generated primitive layout
                before it is placed. By default no rotation is done.
        """
        if not (prim in self.fab.tech.primitives):
            raise ValueError(
                f"prim '{prim.name}' is not a primitive of technology"
                f" '{self.fab.tech.name}'"
            )
        # Translate possible x/y specification to origin
        if origin is None:
            if x is None:
                x = 0.0
            if y is None:
                y = 0.0
            origin = _geo.Point(x=x, y=y)

        primlayout = self.fab.layout_primitive(prim, **prim_params)
        primlayout.rotate(rotation=rotation)
        primlayout.move(dxy=origin)
        self += primlayout
        return primlayout

    @overload
    def add_shape(self, *,
        shape: _geo.MaskShape, layer: None=None, net: Optional[_net.NetT],
    ) -> None:
        ... #pragma: no cover
    @overload
    def add_shape(self, *,
        shape: _geo._Shape, layer: DesignLayerT, net: Optional[_net.NetT],
    ) -> None:
        ... #pragma: no cover
    def add_shape(self, *,
        shape: Union[_geo._Shape, _geo.MaskShape], layer: Optional[DesignLayerT]=None,
        net: Optional[_net.NetT],
    ) -> None:
        """Add a shape to a _Layout.

        This is a low-level layout manipulation method that does not do much checking,
        like space violations, shorted nets originating from the using this method.

        Arguments:
            shape, layer: shape and mask specification to add to `_Layout` object.
                If shape is a `MaskShape` object no layer may be specified. If shape is
                a `_Shape` object the mask has to be specified through the layer
                parameter.
                The `add_shape()` method only allows shapes to be put on a `DesignMask`
                layer.
            net: net to put the shape on.
                One has to specify `None` if one wants to put the shape not on a net.
                No checking is done if the mask is a conductor and thus should be added
                on a net or not.
        """
        if layer is None:
            assert isinstance(shape, _geo.MaskShape), "typing violation"
            ms = shape
        else:
            assert isinstance(shape, _geo._Shape), "typing violation"
            if isinstance(layer, _msk.MaskT):
                assert isinstance(layer, _msk.DesignMask), "typing violation"
                mask = layer
            else:
                assert isinstance(layer, _prm.DesignMaskPrimitiveT), "typing violation"
                mask = layer.mask
            ms = _geo.MaskShape(mask=mask, shape=shape)
        for sl in self._sublayouts.__iter_type__(_MaskShapesSubLayout):
            if sl.net == net:
                sl.add_shape(shape=ms)
                break
        else:
            self._sublayouts += _MaskShapesSubLayout(
                net=net, shapes=_geo.MaskShapes(ms),
            )

    def move(self, *, dxy: _geo.Point) -> None:
        """Move the shapes in the layout by the given displacement.
        This method changes the layout on which this method is called.

        Arguments:
            dxy: the displacement to apply to all the shapes in this layout
        """
        move_context = _geo.MoveContext()
        for sl in self._sublayouts:
            sl.move(dxy=dxy, move_context=move_context)
        if self.boundary is not None:
            self.boundary += dxy

    def moved(self, *, dxy: _geo.Point) -> "LayoutT":
        """Return _Layout with all shapes moved by the given displacement.
        The original layout is not changed,

        Arguments:
            dxy: the displacement to apply to all the shapes in this layout
        """
        move_context = _geo.MoveContext()

        if self.boundary is None:
            bound = None
        else:
            bound = self.boundary.moved(dxy=dxy, context=move_context)
        return _Layout(
            fab=self.fab, sublayouts=_SubLayouts(
                sl.moved(dxy=dxy, move_context=move_context)
                for sl in self._sublayouts
            ),
            boundary=bound,
        )

    def rotate(self, *, rotation: _geo.Rotation) -> None:
        """Rotate the shapes in the layout by the given rotation.
        This method changes the layout on which this method is called.

        Arguments:
            rotation: the rotation to apply to all the shapes in this layout
        """
        rot_context = _geo.RotationContext()

        if self.boundary is not None:
            self.boundary = self.boundary.rotated(rotation=rotation, context=rot_context)
        self._sublayouts=_SubLayouts(
            sl.rotated(rotation=rotation, rot_context=rot_context)
            for sl in self._sublayouts
        )

    def rotated(self, *, rotation: _geo.Rotation) -> "LayoutT":
        """Return _Layout with all shapes rotated by the given rotation.
        The original layout is not changed,

        Arguments:
            rotation: the rotation to apply to all the shapes in this layout
        """
        rot_context = _geo.RotationContext()

        if self.boundary is None:
            bound = None
        else:
            bound = self.boundary.rotated(rotation=rotation, context=rot_context)
        return _Layout(
            fab=self.fab, sublayouts=_SubLayouts(
                sl.rotated(rotation=rotation, rot_context=rot_context)
                for sl in self._sublayouts
            ),
            boundary=bound,
        )

    def freeze(self) -> None:
        """see: https://gitlab.com/Chips4Makers/PDKMaster/-/issues/37"""
        self._sublayouts._freeze_()

    @property
    def _hier_str_(self) -> str:
        """Return a string representing the full hierarchy of the layout.
        Indentation is used to represent the hierarchy.

        API Notes:
            This is for debuggin purposes only and user code should not depend
                on the exact format of this string.
        """
        return "\n  ".join(("layout:", *(s for s in self._hier_strs_)))

    @property
    def _hier_strs_(self) -> Iterable[str]:
        for sl in self._sublayouts:
            yield from sl._hier_strs_

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, _Layout):
            return self._sublayouts == other._sublayouts
        else:
            return False
LayoutT = _Layout


# import at end of file to avoid circular import problems
from .factory_ import LayoutFactory
