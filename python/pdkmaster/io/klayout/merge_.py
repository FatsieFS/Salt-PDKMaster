# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
import abc
from itertools import combinations
from typing import (
    Any, List, Tuple, Dict, Union, Iterable, Optional, overload,
)

from pdkmaster import _util
from pdkmaster.technology import geometry as _geo, mask as _msk
from pdkmaster.design import layout as _lay, cell as _cell, library as _lbry
from pdkmaster.design.layout import layout_ as _laylay
from .import_ import import_poly2poly, import_region2poly
from .export import export_poly2region

import pya

__all__ = ["merge"]


class _MPSDictElemMPS:
    def __init__(self, *, mps_orig: _geo.MultiPartShape):
        partshapes = list(part.partshape for part in mps_orig.parts)
        self.partregions = list(
            export_poly2region(partshape) for partshape in partshapes
        )
        # Parts can be removed, mark them by deferring original number to new number
        self.partidcs: List[int] = list(range(len(mps_orig.parts)))
        # Only create mps the first time a dereference is done.
        # Don't allow to marge shapes anymore after the new mps has been created.
        self.mps: Optional[_geo.MultiPartShape] = None
        self.mpsidcs: Optional[Tuple[int, ...]] = None

    @property
    def is_dereffed(self) -> bool:
        return self.mps is not None

    def lookup_partidx(self, idx: int):
        while True:
            idx2 = self.partidcs[idx]
            if idx == idx2:
                return idx
            else:
                idx = idx2

    def part_is_merged(self, idx: int)  -> bool:
        return self.partidcs[idx] != idx

    def deref_part(self, idx: int):
        if self.mps is None:
            lookedup = list(self.lookup_partidx(i) for i in range(len(self.partregions)))
            uni = list(sorted(set(lookedup)))
            partregions = tuple(self.partregions[idx] for idx in uni)
            parts = map(import_region2poly, partregions)
            fullshaperegion = sum(partregions, pya.Region())
            fullshape = import_region2poly(fullshaperegion)
            self.mps = _geo.MultiPartShape(fullshape=fullshape, parts=parts)
            self.mpsidcs = tuple(uni.index(i) for i in lookedup)
        assert self.mpsidcs is not None
        return self.mps.parts[self.mpsidcs[idx]]

    def change_shape(self, *, idx: int, shaperegion: pya.Region):
        assert not self.is_dereffed

        idx2 = self.lookup_partidx(idx)
        self.partregions[idx2] = shaperegion

    def __hash__(self) -> int:
        raise TypeError(f"{self.__class__.__name__} objects are mutable and can't be hashed")

    def __eq__(self, other: Any) -> bool:
        return super().__eq__(other)


class _MPSDictElem:
    """Class for the values stored in _MPSDict

    It stores extra info needed during conversion of all MultiPartShape._Part objects.

    API Notes:
        This class is for internal use and does not have backwards compatibility
        guarantee.
    """
    def __init__(self, *,
        mps: _geo.MultiPartShape, mpsdict: "_MPSDict",
    ):
        self.mps_orig = mps
        self.elemmps: Optional[_MPSDictElemMPS]
        self.elemmps = None
        self.partidcs: Optional[List[int]]
        self.partidcs = None
        self.mpsdict = mpsdict
        fullshaperegion = export_poly2region(mps.fullshape)
        self._partregions = partregions = list(
            export_poly2region(part.partshape) for part in mps.parts
        )

        # Check sum of parts is fullshape
        region = sum(partregions, pya.Region())
        region.merge()
        if not (region ^ fullshaperegion).is_empty():
            raise ValueError("MultiPartShape parts do not match fullshape")

        # Check that parts don't overlap
        for part1, part2 in combinations(self.partregions, 2):
            overlaps = not part1.overlapping(part2).is_empty()
            if overlaps:
                raise ValueError(
                    "Overlapping parts in MultiPartShape object",
                )

    def init_elemmps(self):
        assert self.elemmps is None, "Internal error"
        self.elemmps = _MPSDictElemMPS(mps_orig=self.mps_orig)
        self.partidcs = list(range(len(self.mps_orig.parts)))

    def merge_with(self, other: "_MPSDictElem") -> int:
        """
        Return:
            the index offset to add to the index value of other
        """
        if self.elemmps is None:
            self.init_elemmps()
        assert self.elemmps is not None
        if other.elemmps is None:
            other.init_elemmps()
        assert (other.elemmps is not None) and (other.partidcs is not None)

        if self.elemmps == other.elemmps:
            return 0
        else:
            offset = len(self.elemmps.partregions)
            elemmps2 = other.elemmps
            self.elemmps.partregions.extend(elemmps2.partregions)
            self.elemmps.partidcs.extend(idx + offset for idx in elemmps2.partidcs)
            # Replace all accorences of old elemmps with new one
            for elem in self.mpsdict.values():
                if (elem != self) and (elem.elemmps == elemmps2):
                    assert elem.partidcs is not None
                    assert elem.elemmps is not None
                    elem.elemmps = self.elemmps
                    elem.partidcs = list(idx + offset for idx in elem.partidcs)
            return offset

    @property
    def partregions(self) -> List[pya.Region]:
        elemmps = self.elemmps
        if elemmps is None:
            return self._partregions
        else:
            assert self.partidcs is not None
            return list(
                elemmps.partregions[elemmps.lookup_partidx(idx)]
                for idx in self.partidcs
            )

    def change_shape_part(self, *, idx: int, shape: _geo.Polygon):
        shaperegion = export_poly2region(shape)
        self._partregions[idx] = shaperegion

        assert (self.elemmps is not None) and (self.partidcs is not None)
        self.elemmps.change_shape(idx=self.partidcs[idx], shaperegion=shaperegion)

    def part_is_merged(self, *, idx: int) -> bool:
        if self.elemmps is None:
            return False
        else:
            assert self.partidcs is not None
            return self.elemmps.part_is_merged(idx=self.partidcs[idx])

    def deref_part(self, orig_idx: int) -> _geo.MultiPartShape._Part:
        if self.elemmps is None:
            return self.mps_orig.parts[orig_idx]
        else:
            assert self.partidcs is not None
            return self.elemmps.deref_part(self.partidcs[orig_idx])

    def __hash__(self) -> int:
        raise TypeError(f"{self.__class__.__name__} objects are mutable and can't be hashed")

    def __eq__(self, other: Any) -> bool:
        return super().__eq__(other)
        # assert False, "Internal error" # pragma: no cover


class _Reffed:
    @abc.abstractmethod
    def __init__(self):
        return # pragma: no cover

    @abc.abstractmethod
    def deref(self) -> Union[_geo._Shape, _geo.MaskShape, _geo.MaskShapes, _laylay._SubLayout]:
        raise RuntimeError("Non overloaded abstract method") # pragma: no cover


class _ShapeReffed(_Reffed):
    @abc.abstractmethod
    def deref(self) -> _geo._Shape:
        raise RuntimeError("Non overloaded abstract method") # pragma: no cover


class _ShapeRef(_ShapeReffed):
    def __init__(self, *, shape: _geo._Shape):
        self.shape = shape

    def deref(self) -> _geo._Shape:
        return self.shape


class _PartRef(_ShapeReffed):
    def __init__(self, *, elem: _MPSDictElem, idx: int):
        self.elem = elem
        self.idx = idx

    @property
    def is_merged(self):
        return self.elem.part_is_merged(idx=self.idx)
    @property
    def region(self):
        return _util.get_nth_of(self.elem.partregions, n=self.idx)

    def deref(self) -> _geo.MultiPartShape._Part:
        return self.elem.deref_part(self.idx)

    def interacts_with(self, *, shapereg) -> bool:
        return not self.region.interacting(shapereg).is_empty()

    def is_same_part_as(self, other: "_PartRef") -> bool:
        elem = self.elem
        elem2 = other.elem
        if elem.elemmps is None:
            return (
                (elem2.elemmps is None)
                and (elem.mps_orig == elem2.mps_orig)
                and (self.idx == other.idx)
            )
        else:
            elemmps = elem.elemmps
            elemmps2 = elem2.elemmps
            return (
                (elemmps == elemmps2)
                and (elemmps2 is not None)
                and (elem.partidcs is not None)
                and (elem2.partidcs is not None)
                and (
                    elemmps.lookup_partidx(idx=elem.partidcs[self.idx])
                    == elemmps2.lookup_partidx(idx=elem2.partidcs[other.idx])
                )
            )

    def add_polygon(self, polygon: pya.Polygon) -> None:
        elem = self.elem
        if elem.elemmps is None:
            elem.init_elemmps()
        assert elem.elemmps is not None

        region = elem.partregions[self.idx]
        region += polygon # type: ignore

        self.change_shape_to(import_region2poly(region))

    def change_shape_to(self, shape: _geo.Polygon) -> None:
        elem = self.elem
        elem.change_shape_part(idx=self.idx, shape=shape)

    def merge_with(self, ref: "_PartRef") -> None:
        elem = self.elem
        elem2 = ref.elem
        if (elem.elemmps is None) or (elem.elemmps != elem2.elemmps):
            elem.merge_with(elem2)
            # The merge_with call above will also ensure elem.init_elemmps() has been
            # called
        elemmps = elem.elemmps
        elem2mps = elem2.elemmps
        assert (
            (elemmps is not None) and (elemmps == elem2mps)
            and (elem.partidcs is not None) and (elem2.partidcs is not None)
            and (elemmps.partidcs is not None)
        )

        # Merge other shape in our shape
        region = self.region
        region += ref.region
        self.change_shape_to(import_region2poly(region))

        # Mark second part as merged to the first one
        partidx = elem.partidcs[self.idx]
        partidx2 = elem2.partidcs[ref.idx]
        elemmps.partidcs[partidx2] = partidx


class _MultiShapeRef(_ShapeReffed):
    def __init__(self, *, shapes: Iterable[Union[_ShapeRef, _PartRef]]):
        self.shapes = shapes

    def deref(self) -> _geo._Shape:
        # Multiple shape can point to the same part and end up with one shape
        shapes = tuple(shape.deref() for shape in self.shapes)
        return _geo.MultiShape(shapes=shapes)


class _MaskShapeRef(_Reffed):
    def __init__(self, *, mask: _msk.DesignMask, ref: _ShapeReffed):
        self.mask = mask
        self.ref = ref

    def deref(self) -> _geo.MaskShape:
        return _geo.MaskShape(mask=self.mask, shape=self.ref.deref())


class _MaskShapesRef(_Reffed):
    def __init__(self, *, maskshapes: Iterable[_MaskShapeRef]):
        self.maskshapes = tuple(maskshapes)

    def deref(self) -> _geo.MaskShapes:
        return _geo.MaskShapes(ms.deref() for ms in self.maskshapes)


class _SubLayoutReffed(_Reffed):
    @abc.abstractmethod
    def deref(self) -> _laylay._SubLayout:
        raise RuntimeError("Non overloaded abstract method") # pragma: no cover


class _SubLayoutRef(_SubLayoutReffed):
    def __init__(self, *, sublayout: _laylay._SubLayout):
        self.sublayout = sublayout

    def deref(self) -> _laylay._SubLayout:
        return self.sublayout


class _MaskShapesSubLayoutRef(_SubLayoutReffed):
    def __init__(self, *, net, ref: _MaskShapesRef):
        self.net = net
        self.ref = ref

    def deref(self) -> _laylay._MaskShapesSubLayout:
        return _laylay._MaskShapesSubLayout(net=self.net, shapes=self.ref.deref())


class _MPSDict(Dict[_geo.MultiPartShape, _MPSDictElem]):
    # Dict with automatically creation of element
    def __getitem__(self, mps: _geo.MultiPartShape) -> _MPSDictElem:
        try:
            return super().__getitem__(mps)
        except KeyError:
            mps2 = _MPSDictElem(mps=mps, mpsdict=self)
            self[mps] = mps2
            return mps2

    def partref(self, part: _geo.MultiPartShape._Part) -> _PartRef:
        mps = part.multipartshape
        e = self[mps]
        return _PartRef(elem=e, idx=mps.parts.index(part))


class _ShapeMerger:
    def __init__(self):
        self._mps_lookup: _MPSDict
        self._mps_lookup = _MPSDict()

    @property
    def mps_lookup(self) -> _MPSDict:
        return self._mps_lookup

    @overload
    def __call__(self, shape: _lay.LayoutT) -> _lay.LayoutT:
        ... # pragma: no cover
    @overload
    def __call__(self, shape: _geo.MaskShape) -> _MaskShapeRef:
        ... # pragma: no cover
    @overload
    def __call__(self, shape: _geo.MaskShapes) -> _MaskShapesRef:
        ... # pragma: no cover
    @overload
    def __call__(self, shape: _geo.MultiPartShape._Part) -> _PartRef:
        ... # pragma: no cover
    @overload
    def __call__(self, shape: _geo._Shape) -> _ShapeReffed:
        ... # pragma: no cover
    @overload
    def __call__(self, shape: Iterable[_geo._Shape]) -> Tuple[_ShapeReffed, ...]:
        ... # pragma: no cover
    def __call__(self, shape):
        if isinstance(shape, _lay.LayoutT):
            return self.merge_layout(shape)
        elif isinstance(shape, _geo.MaskShape):
            return self.merge_maskshape(shape)
        elif isinstance(shape, _geo.MaskShapes):
            return self.merge_maskshapes(shape)
        elif isinstance(shape, _geo.MultiShape):
            return self.merge_multishape(shape)
        elif isinstance(shape, _geo.MultiPartShape._Part):
            return self._mps_lookup.partref(shape)
        elif isinstance(shape, _geo._Shape):
            return _ShapeRef(shape=shape)
        elif _util.is_iterable(shape):
            # This is not MaskShapes so assume it's Iterable[_geo._Shape]
            return self.merge_shapes(shape)
        else:
            raise TypeError(f"Unsupported shape object type {type(shape)}")

    def merge_maskshape(self, ms: _geo.MaskShape) -> _MaskShapeRef:
        return _MaskShapeRef(mask=ms.mask, ref=self(ms.shape))

    def merge_maskshapes(self, mss: _geo.MaskShapes) -> _MaskShapesRef:
        return _MaskShapesRef(maskshapes=map(self.merge_maskshape, mss))

    def merge_multishape(self, ms: _geo.MultiShape) -> _ShapeReffed:
        """merge the MultiShape.

        This method will use KLayout to merge a much as possible the shapes
        inside a MultiShape object.

        The resulting merged shape. If original MultiShape object only contained
        interacting polygons a _Shape object will be returned that is not a
        MultiShape object.

        As side effect the MultiPartShape objects will also be checked that they
        are properly defined; e.g. that the fullshape is exactly the or-ing of the
        parts without any of the parts overlapping.
        """
        # Sort the shapes
        shapes: List[Union[_ShapeRef, _PartRef]] = [] # Final list of shapes
        partmps_list: List[_PartRef] = []
        polygons = pya.Region()
        # First stage:
        # - add non-merging shapes directly,
        # - merge polygons inside a klayout region,
        # - build list of multishape part objects
        for shape in ms.shapes:
            try:
                area = shape.area
            except:
                # Try to merge on object that don't have area computation implemented
                pass
            else:
                if area < (_geo.epsilon**2) or isinstance(shape, (_geo.RepeatedShape, _geo.RectRing)):
                    # Zero area and repeated shapes are retained as is.
                    shapes.append(_ShapeRef(shape=shape))
                    self(shape)
                    continue

            # MultiShape should not be hierarchical
            assert (not isinstance(shape, _geo.MultiShape)), "Internal Error"
            # MultiPartShape should not be part of MultiShape,
            # (MultiPartShape._Part should)
            assert (not isinstance(shape, _geo.MultiPartShape)), "Internal Error"

            if isinstance(shape, _geo.MultiPartShape._Part):
                mps = shape.multipartshape
                klmps = self.mps_lookup[shape.multipartshape]
                idx = mps.parts.index(shape)
                partmps_list.append(_PartRef(elem=klmps, idx=idx))
            else:
                assert isinstance(shape, _geo.Polygon)
                polygons += export_poly2region(shape)
        polygons.merge()

        # Join polygons from polygons into the MultiPartShape objects
        merged_polygons = pya.Region()
        for polygon in polygons.each():
            polygonreg = pya.Region(polygon)
            for ref in partmps_list:
                mps = ref.elem
                if ref.interacts_with(shapereg=polygonreg):
                    # Merge polygon
                    # print("\n", type(mps))
                    # print(mps.fullshape)
                    # print("+", polygonreg)
                    ref.add_polygon(polygon)
                    # print("=>", mps.fullshape)

                    merged_polygons += polygon # type: ignore
                    # Only merge it with one part, rest is handled ny merging
                    # part together.
                    break
        polygons -= merged_polygons

        # Join overlapping parts
        # Repeat until not mergers take place anymore; do at least one iteration
        merged = True
        while merged:
            merged = False
            # Merge all parts that overlap with another part and are not already merged
            for ref1, ref2 in combinations(partmps_list, 2):
                if not ref1.is_same_part_as(ref2):
                    if ref1.interacts_with(shapereg=ref2.region):
                        ref1.merge_with(ref2)
                        merged = True

        # Add remaining polygons
        shapes.extend(_ShapeRef(shape=import_poly2poly(poly)) for poly in polygons.each())
        # Add converted parts
        filtered = filter(lambda ref: not ref.is_merged, partmps_list)
        shapes.extend(filtered)

        assert len(shapes) > 0, "Internal error"
        if len(shapes) == 1:
            result = shapes[0]
        else:
            result = _MultiShapeRef(shapes=tuple(shapes))
        return result

    def merge_sublayout(self, sl: _laylay._SubLayout) -> _SubLayoutReffed:
        if isinstance(sl, _laylay._MaskShapesSubLayout):
            return _MaskShapesSubLayoutRef(net=sl.net, ref=self(sl.shapes))
        else:
            # TODO: unit test with _InstanceSubLayout
            return _SubLayoutRef(sublayout=sl) # pragma: no cover

    def merge_layout(self, layout: _lay.LayoutT) -> _lay.LayoutT:
        # Create a tuple so we have merged all the sublayouts before we are going to deref
        # them
        slrefs = tuple(map(self.merge_sublayout, layout._sublayouts))
        sls = _laylay._SubLayouts(slref.deref() for slref in slrefs)
        return layout.fab.new_layout(sublayouts=sls, boundary = layout.boundary)

    def merge_shapes(self, shapes: Iterable[_geo._Shape]) -> Tuple[_ShapeReffed, ...]:
        return tuple(self(shape) for shape in shapes)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def __del__(self):
        # TODO: Check for all MultiPartShape._Part converted to new ones.
        # This is to avoid having shapes where some the the _Part objects point
        # to old MultiPartShape and some to a new one.
        pass


@overload
def merge(obj: _lay.LayoutT) -> _lay.LayoutT:
    ... # pragma: no cover
@overload
def merge(obj: _cell.Cell) -> None:
    ... # pragma: no cover
@overload
def merge(obj: _lbry.Library) -> None:
    ... # pragma: no cover
@overload
def merge(obj: _geo.MultiShape) -> _geo._Shape:
    ... # pragma: no cover
@overload
def merge(obj: _geo.MaskShape) -> _geo.MaskShape:
    ... # pragma: no cover
@overload
def merge(obj: _geo.MaskShapes) -> _geo.MaskShapes:
    ... # pragma: no cover
def merge(
    obj: Union[
        _lay.LayoutT, _cell.Cell, _lbry.Library, _geo.MultiShape,
        _geo.MaskShape, _geo.MaskShapes,
    ],
) -> Optional[Union[
    _lay.LayoutT, _geo._Shape, _geo.MaskShape, _geo.MaskShapes,
]]:
    """This function allows to use the KLayout engine to merge PDKMaster _Shape objects;
    either directly or as part of another PDKMaster object

    Althouogh it will be tried to merge shapes there is no guarantee given that merge-able
    shapes are effectively merged. Currently RepeatedShape objects are retained as is and
    not merged with other shapes.

    Arguments:
        obj: the PDKMaster object from which the shape(s) needs to be merged.
            obj can also be an iterable of Shape objects.

    Returns:
        Return same type of object; the object may have been simplified; e.g.
        merging a MultiShape with all shapes overlapping can result in a Polygon or a Rect.
        Currently RepeatedShape and _InstanceSubLayout will not be merge and returned
        as is.
        For object of type `_Cell` and `Library` the merging will be done on the provided
        object and no value is returned.
    """
    if isinstance(obj, _cell.Cell):
        for l in obj._layouts:
            l.layout = merge(l.layout)
    elif isinstance(obj, _lbry.Library):
        for cell in obj.cells:
            merge(cell)
    else:
        merged = _ShapeMerger()(obj)
        if isinstance(merged, _lay.LayoutT):
            return merged
        else:
            return merged.deref()
