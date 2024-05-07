# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
import abc
from typing import Union

from ..typing import MultiT, cast_MultiT
from . import property_ as _prp, mask as _msk


__all__ = [
    "EdgeT", "MaskOrEdgeT",
    "MaskEdge", "Join", "Intersect",
]


class _EdgeProperty(_prp._Property):
    """`_EdgeProperty` is a `Property` for a `_Edge` object.
    """
    def __init__(self, *, edge: "_Edge", name: str):
        super().__init__(name=(str(edge) + "." + name))
        self.edge = edge
        self.prop_name = name


class _DualEdgeProperty(_prp._Property):
    """`_EdgeProperty` is a `Property` related to an `_Edge` object
    and a second `_Edge` or `Mask` object.
    """
    def __init__(self, *,
        edge1: "EdgeT", edge2: "MaskOrEdgeT", name: str, commutative: bool, allow_mask2: bool,
    ):
        assert (
            isinstance(edge2, _Edge) or (isinstance(edge2, _msk.MaskT) and allow_mask2)
        ), "Internal error"

        if commutative:
            full_name = f"{name}({edge1.name},{edge2.name})"
        else:
            full_name = f"{edge1.name}.{name}({edge2.name})"
        super().__init__(name=full_name)

        self.edge1 = edge1
        self.edge2 = edge2
        self.prop_name = name


class _Edge(abc.ABC):
    """_Edge is a base class representing the edges of shape drawn on a mask.
    It is used to define it's own operation with their own semantics used in
    rules. For example intersection of edges has a different meaning than the
    intersecton of shapes on a mask.
    """
    @abc.abstractmethod
    def __init__(self, *, name: str):
        self.name = name

        self.length: _prp.PropertyT = _EdgeProperty(edge=self, name="length")
        self.space: _prp.PropertyT = _EdgeProperty(edge=self, name="space")

    def __str__(self):
        return self.name

    def enclosed_by(self, other: "MaskOrEdgeT") -> _prp.PropertyT:
        return _DualEdgeProperty(
            edge1=self, edge2=other, name="enclosed_by",
            commutative=False, allow_mask2=True,
        )

    def interact_with(self, other: "MaskOrEdgeT") -> "EdgeT":
        return _DualEdgeOperation(
            edge1=self, edge2=other, name="interact_with", allow_mask2=True,
        )
EdgeT = _Edge
MaskOrEdgeT = Union[_msk.MaskT, EdgeT]


class _DualEdgeOperation(_Edge):
    """`_DualEdgeOperation` represents the resulting `_Edge` from an
    operation performed on a `_Edge` object and a `_Edge` or `Mask` object.
    """
    def __init__(self, *,
        edge1: _Edge, edge2: MaskOrEdgeT, name: str, allow_mask2: bool=False,
    ):
        assert (
            isinstance(edge2, _Edge) or (allow_mask2 and isinstance(edge2, _msk.MaskT))
        ), "Internal error"

        super().__init__(name=f"{edge1.name}.{name}({edge2.name})")
        self.edge1 = edge1
        self.edge2 = edge2
        self.operation = name


class MaskEdge(_Edge):
    """Objects of this class represent the edges of shapes present on a `Mask`
    object.
    """
    def __init__(self, mask: _msk.MaskT):
        self.mask = mask

        super().__init__(name=f"edge({mask.name})")


class Join(_Edge):
    """`Joim` represent the resulting `_Edge` object from joining
    the edges from two or more `_Edge` objects.
    """
    def __init__(self, edges: MultiT[EdgeT]):
        self.edges = edges = cast_MultiT(edges)

        super().__init__(name="join({})".format(",".join(str(edge) for edge in edges)))


class Intersect(_Edge):
    """`Joim` is the resulting `_Edge` object representing the overlapping
    parts of the edges from two or more `_Edge` objects.

    Crossing edges can result in points but the handling of this is application
    dependent.
    """
    def __init__(self, edges: MultiT[MaskOrEdgeT]):
        edges = cast_MultiT(edges)
        if not any(isinstance(edge, _Edge) for edge in edges):
            raise TypeError("at least one element of edges has to be of type 'Edge'")
        self.edges = edges

        super().__init__(name="intersect({})".format(",".join(str(edge) for edge in edges)))
