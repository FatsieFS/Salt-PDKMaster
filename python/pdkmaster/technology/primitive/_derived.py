# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from typing import Tuple, Iterable, Union, Optional

from pdkmaster.technology import mask as _msk

from ...typing import MultiT, cast_MultiT
from .. import rule as _rle, mask as _msk, technology_ as _tch

from ._core import _MaskPrimitive, DesignMaskPrimitiveT


# _DerivedPrimitive and subclasses are considered for internal use only;
# not to be used in user land code. User land just sees MaskPrimitiveT
__all__ = ["InsidePrimitiveT"]


class _DerivedPrimitive(_MaskPrimitive):
    """A primitive that is derived from other primitives and not a
    Primitive that can be part of the primitive list of a technology.
    """
    def _generate_rules(self, *, tech: _tch.Technology) -> Tuple[_rle.RuleT, ...]:
        """As _DerivedPrimitive will not be added to the list of primitives
        of a technology node, it does not need to generate rules.
        """
        raise RuntimeError("Internal error") # pragma: no cover


class _Intersect(_DerivedPrimitive):
    """A derived primitive representing the overlap of a list of primitives
    """
    def __init__(self, *, name: Optional[str]=None, prims: Iterable[_MaskPrimitive]):
        prims2: Tuple[_MaskPrimitive, ...] = cast_MultiT(prims)
        if len(prims2) < 2:
            raise ValueError(f"At least two prims needed for '{self.__class__.__name__}'")
        self.prims = prims2

        mask = _msk.Intersect(p.mask for p in prims2)
        super().__init__(name=name, mask=mask)

    def __hash__(self):
        return hash(self.prims)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _Intersect):
            return False
        else:
            return set(self.prims) == set(other.prims)


class _InsidePrimitive(_Intersect):
    """A derived primitive that represents a main primitive inside other primitives.
    A separate class super to _Intersect is here to keep track of the main primitive
    which is inside other primitive.
    One of the intended use cases is for min_width/min_space computation for a
    certain primitive (like WaferFire) inside certain context, e.g. implant etc.
    """
    def __init__(self, *,
        name: Optional[str]=None,
        prim: DesignMaskPrimitiveT,
        in_: MultiT[Union[DesignMaskPrimitiveT, "InsidePrimitiveT"]],
    ):
        self.prim = prim
        self.in_ = in_ = cast_MultiT(in_)
        if name is None:
            s_in = (
                in_[0].name if len(in_) == 1
                else f"({','.join(p.name for p in in_)})"
            )
            name = f"inside({prim.name},{s_in})"
        super().__init__(name=name, prims=(prim, *self.in_))

    def __hash__(self):
        return super().__hash__()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _InsidePrimitive):
            return False
        else:
            return (self.prim == other.prim) and (set(self.in_) == set(other.in_))
InsidePrimitiveT = _InsidePrimitive


class _Alias(_DerivedPrimitive):
    """A derived primitive giving an alias to another mask primitive.
    This is mainly used to have aliases for rules on the mask of a given
    MaskPrimitive.
    """
    def __init__(self, *, prim: _MaskPrimitive, alias: str):
        self._prim = prim
        super().__init__(mask=prim.mask.alias(alias))
        self.mask: _msk._MaskAlias

class _Outside(_DerivedPrimitive):
    """A derived primitive representing the part of another primitive
    """
    def __init__(self, *, prim: _MaskPrimitive, where: Tuple[_MaskPrimitive, ...]):
        where = cast_MultiT(where)
        if len(where) == 0:
            raise ValueError(
                "At least one layer has to be given for Outside derived mask"
            )
        elif len(where) == 1:
            mask = prim.mask.remove(where[0].mask)
        else:
            mask = prim.mask.remove(_msk.Join(w.mask for w in where))
        super().__init__(mask=mask)
