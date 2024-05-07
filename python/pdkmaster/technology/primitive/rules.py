# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
# This file was named ruleprims.py as rule.py seemed to be able to confuse pylance
# from vscode.
from itertools import product
from typing import Iterable

from ...typing import MultiT, cast_MultiT, OptMultiT, cast_OptMultiT
from .. import (
    property_ as _prp, rule as _rle, mask as _msk, technology_ as _tch,
)

from ._core import _Primitive, _MaskPrimitive
from ._derived import _Intersect


__all__ = [
    "RulePrimitiveT",
    "MinWidth", "Spacing", "Enclosure", "NoOverlap",
]


class _RulePrimitive(_Primitive):
    """Subclasses of _RulePrimitive represent extra design rules without further
    physical representation of a Primitive. They thus don't have a layout etc.
    It's a base class that needs to be subclassed.
    """
    pass
RulePrimitiveT = _RulePrimitive


class MinWidth(_RulePrimitive):
    """A _RulePrimitive to be able to add extra width rule for a derived
    primitive.

    Arguments:
        prim: the primitive on which to add minimum width rule.
            Typically this should be a derived layer; e.g. minimum width
            higher for higher voltage diffusion than low voltage diffusion.
        min_width: the minimum width
    """
    def __init__(self, *,
        prim: _MaskPrimitive, min_width: float,
    ):
        name = f"MinWidth({prim.name},{min_width:.6})"
        super().__init__(name=name)
        self.prim = prim
        self.min_width = min_width

    def _generate_rules(self, *,
        tech: _tch.Technology,
    ) -> Iterable[_rle.RuleT]:
        yield self.prim.mask.width >= self.min_width

    @property
    def designmasks(self):
        yield from super().designmasks
        yield from self.prim.designmasks


class Spacing(_RulePrimitive):
    """A _RulePrimitive that allows to define extra minimum space requirement
    that is not derived from the parameters from any of the primitives in the
    a technology

    Arguments:
        primitives1: first set of primitives
            If primitives2 is not provided this set has to contain more than
            one primitive and the minimum space requirement is for the
            combined shape of joining all shapes in all the layers in this
            set.
        primitives2: optinal second set of primitives
            If this set is provided the minimum space specification is for
            each shape on a layer in primitives1 to each shape on a layer
            in primitives2.
        min_space: the minimum space specifcation
    """
    def __init__(self, *,
        primitives1: MultiT[_MaskPrimitive],
        primitives2: OptMultiT[_MaskPrimitive]=None,
        min_space: float,
    ):
        primitives1 = cast_MultiT(primitives1)
        primitives2 = cast_OptMultiT(primitives2)

        if primitives2 is not None:
            name = "Spacing({},{:.6})".format(
                ",".join(
                    (
                        prims[0].name if len(prims) == 1
                        else "({})".format(",".join(prim.name for prim in prims))
                    ) for prims in (primitives1, primitives2)
                ),
                min_space,
            )
        else:
            s_prim1 = (
                primitives1[0].name if len(primitives1) == 1
                else "({})".format(",".join(prim.name for prim in primitives1))
            )
            name = f"Spacing({s_prim1},None,{min_space:.6})"
        super().__init__(name=name)
        self.primitives1 = primitives1
        self.primitives2 = primitives2
        self.min_space = min_space

    def _generate_rules(self, *,
        tech: _tch.Technology,
    ) -> Iterable[_rle.RuleT]:
        yield from super()._generate_rules(tech=tech)

        if self.primitives2 is None:
            joined = _msk.Join(prim1.mask for prim1 in self.primitives1)
            yield joined.space >= self.min_space
        else:
            yield from (
                _msk.Spacing(prim1.mask, prim2.mask) >= self.min_space
                for prim1, prim2 in product(self.primitives1, self.primitives2)
            )

    @property
    def designmasks(self):
        yield from super().designmasks
        if self.primitives2 is not None:
            for prim in (*self.primitives1, *self.primitives2):
                yield from prim.designmasks
        else:
            for prim in self.primitives1:
                yield from prim.designmasks

    def __repr__(self):
        return self.name


class Enclosure(_RulePrimitive):
    """A _RulePrimitive that allows to define extra minimum enclosure
    requirement that is not derived from the parameters from any of the
    primitives in a technology.

    Argumnets:
        prim: the base primitive
        by: the enclosing primitive
        min_enclosure: the minimum `Enclosure` of `prim` by `by`
    """
    def __init__(self, *,
        prim: _MaskPrimitive, by: _MaskPrimitive, min_enclosure: _prp.Enclosure,
    ):
        name = f"Enclosure(prim={prim!r},by={by!r},min_enclosure={min_enclosure!r})"
        super().__init__(name=name)

        self.prim = prim
        self.by = by
        self.min_enclosure = min_enclosure

    def _generate_rules(self, *,
        tech: _tch.Technology,
    ) -> Iterable[_rle.RuleT]:
        yield from super()._generate_rules(tech=tech)

        yield self.prim.mask.enclosed_by(self.by.mask) >= self.min_enclosure

    @property
    def designmasks(self) -> Iterable[_msk.DesignMask]:
        yield from super().designmasks
        yield from self.prim.designmasks
        yield from self.by.designmasks

    def __repr__(self) -> str:
        return self.name


class NoOverlap(_RulePrimitive):
    """A _RulePrimitive that allows to define extra no overlap
    requirement that is not derived from the parameters from any of the
    primitives in a technology.

    Argumnets:
        prim1, prim2:  the two primitives where none of the shape may
            have a overlapping part.
    """
    def __init__(self, *, prim1: _MaskPrimitive, prim2: _MaskPrimitive):
        name = f"NoOverlap(prim1={prim1!r},prim2={prim2!r})"
        super().__init__(name=name)

        self.prim1 = prim1
        self.prim2 = prim2

    def _generate_rules(self, *,
        tech: _tch.Technology,
    ) -> Iterable[_rle.RuleT]:
        yield from super()._generate_rules(tech=tech)

        intersect = _Intersect(prims=(self.prim1, self.prim2))
        yield intersect.mask.area == 0.0

    @property
    def designmasks(self) -> Iterable[_msk.DesignMask]:
        yield from super().designmasks
        yield from self.prim1.designmasks
        yield from self.prim2.designmasks

    def __repr__(self) -> str:
        return self.name
