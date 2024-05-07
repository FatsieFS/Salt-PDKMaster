# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
import abc
from typing import Tuple, Iterable, Optional, ClassVar, cast

from ..typing import MultiT, cast_MultiT
from . import rule as _rle, property_ as _prp


__all__ = ["MaskT", "RuleMaskT", "DesignMask", "Join", "Intersect"]


class _MaskProperty(_prp._Property):
    """`_MaskProperty` is a `Property` object on a single `MaskT` object.
    
    Typical examples are width, area, density etc.
    """
    def __init__(self, *, mask: "MaskT", name: str):
        super().__init__(name=(mask.name + "." + name))
        self.mask = mask
        self.prop_name = name


class _DualMaskProperty(_prp._Property):
    """`_MaskProperty` if a `Property` object on two `MaskT` objects.
    
    Typical example is the spacing or overlap between two masks.
    """
    def __init__(self, *, mask1: "MaskT", mask2: "MaskT", name: str, commutative: bool):
        if commutative:
            supername = f"{name}({mask1.name},{mask2.name})"
        else:
            supername = f"{mask1.name}.{name}({mask2.name})"
        super().__init__(name=supername)

        self.mask1 = mask1
        self.mask2 = mask2
        self.prop_name = name


class _DualMaskEnclosureProperty(_prp._EnclosureProperty):
    """`_DualMaskProperty` is a `Property` object with on two `_Mask` objects with
    an `Enclosure` object as value."""
    def __init__(self, *, mask1: "MaskT", mask2: "MaskT", name: str):
        super().__init__(name=f"{mask1.name}.{name}({mask2.name})")

        self.mask1 = mask1
        self.mask2 = mask2
        self.prop_name = name


class _MultiMaskCondition(_rle._Condition):
    """_MultiMaskCondition is a `_Condition` object involving multiple masks.

    This class is a base class that needs to be subclassed with a `str` value given
    for the operation class variable. Implementation of the methods for this class
    are complete so defining a subclass that only sets this operation class variable
    should be enough.
    """
    operation: ClassVar[str]

    def __init__(self, *, mask: "MaskT", others: MultiT["MaskT"]):
        try:
            self.operation
        except AttributeError:
            raise AttributeError(
                f"class '{self.__class__.__name__}' does not provide operation class variable"
            )
        others = cast_MultiT(others)
        super().__init__(elements=(mask, others))
        self._elements: Tuple["MaskT", Tuple["MaskT"]]

        self._hash: Optional[int] = None

    @property
    def mask(self) -> "MaskT":
        return self._elements[0]
    @property
    def others(self) -> Tuple["MaskT"]:
        return self._elements[1]

    def __eq__(self, other: object) -> bool:
        if self.__class__ is not other.__class__:
            return False
        else:
            other = cast(_MultiMaskCondition, other)
            return set((self.mask, *self.others)) == set((other.mask, *other.others))

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(tuple(sorted(m.name for m in (self.mask, *self.others))))
        return self._hash

    def __repr__(self) -> str:
        return "{}.{}({})".format(
            repr(self.mask), self.operation,
            ",".join(repr(mask) for mask in self.others),
        )


class _InsideCondition(_MultiMaskCondition):
    """`_MultiMaskCondition` true if the main `_Mask` is fully covered by
    any of the other masks"""
    operation = "is_inside"
class _OutsideCondition(_MultiMaskCondition):
    """`_MultiMaskCondition` true if the main `_Mask` is outside
    any of the other masks"""
    operation = "is_outside"


class _Mask(abc.ABC):
    """A `_Mask` object represents that can hold a collection of `_Shape` objects.
    The mask can be with original `_Shape` objects as designed by the user or be
    derived from the `_Shape` objects from other `_Mask` objects.

    Each `_Mask` object has default properties defined that can be accessed as
    attributes of the `_Mask` object. The default properties are:
    - `width`
    - `length`
    - `space`
    - `area`
    - `density`

    TODO: Define exact meaning of width/length
    """
    @abc.abstractmethod
    def __init__(self, *, name: str):
        self.name = name
        self.width: _prp.PropertyT = _MaskProperty(mask=self, name="width")
        self.length: _prp.PropertyT = _MaskProperty(mask=self, name="length")
        self.space: _prp.PropertyT = _MaskProperty(mask=self, name="space")
        self.area: _prp.PropertyT = _MaskProperty(mask=self, name="area")
        self.density: _prp.PropertyT = _MaskProperty(mask=self, name="density")

    def __repr__(self) -> str:
        return self.name

    def extend_over(self, other: "MaskT") -> _prp.PropertyT:
        """Returns a `Property` object representing the extension of one
        the shapes on one `MaskT` object over the shapes on another `MaskT`
        object.
        """
        return _DualMaskProperty(
            mask1=self, mask2=other, name="extend_over", commutative=False,
        )

    def enclosed_by(self, other: "MaskT") -> _prp.EnclosurePropertyT:
        """Returns a `EnclosureProperty` object representing the enclosure of one
        the shapes on one `MaskT` object by the shapes on another `MaskT`
        object.
        """
        return _DualMaskEnclosureProperty(mask1=self, mask2=other, name="enclosed_by")

    def is_inside(self, other: MultiT["MaskT"], *others: "MaskT") -> _rle.ConditionT:
        """Returns a `_Condition` object representing wether all the shapes on a 'MaskT`
        object are inside one of the other `MaskT` objects.
        """
        masks = (*cast_MultiT(other), *others)

        return _InsideCondition(mask=self, others=masks)

    def is_outside(self, other: MultiT["MaskT"], *others: "MaskT") -> _rle.ConditionT:
        """Returns a `_Condition` object representing wether all the shapes on a 'MaskT`
        object are outside any of the other `MaskT` objects.
        """
        masks = (*cast_MultiT(other), *others)

        return _OutsideCondition(mask=self, others=masks)

    def parts_with(self, condition: MultiT[_prp.ComparisonT]) -> "MaskT":
        """Returns a derived `MaskT` representing the parts of the shapes on
        the `MaskT` object that fulfill the given condition(s).  
        The condition may only use properties from the same mask on which one
        calls the `parts_with` method.

        Example: `small = mask.parts_with(mask.width <= 1.0)`
        """
        return _PartsWith(mask=self, condition=condition)

    def remove(self, what: MultiT["MaskT"], *args: "MaskT") -> "MaskT":
        """Returns a derived `MaskT` representing the parts of the shapes on
        the `MaskT` that don't overlap with shapes of the other `MaskT` object.
        """
        what = (*cast_MultiT(what), *args)
        if len(what) == 0:
            raise ValueError("No mask given")
        elif len(what) == 1:
            mask = what[0]
        else:
            mask = Join(what)
        return _MaskRemove(from_=self, what=mask)

    def alias(self, name: str) -> "RuleMaskT":
        """Returns a derived `MaskT` given an alias for another `MaskT` object.
        The return object is also a `_Rule` object in order for scripts that
        are generated from rules can define a variable representing the
        `MaskT` that has been aliased. Typically the variable name will be
        the alias name and further on in generated rules then this variable
        will be used where this alias is used in other derived `MaskT` object
        or properties.
        """
        return _MaskAlias(name=name, mask=self)

    @property
    def same_net(self) -> "MaskT":
        """Returns a derived `MaskT` representing the shapes on a `MaskT` that
        are on the same net. It's thus connectivity related as defined by the
        `Connect` object.  
        The derived mask actually is a collection of separate masks for each
        net that has shapes on this mask. Supporting this kind of mask in
        generated rules may this be non-trivial.

        Typical use of this mask is to allow shape on the same net being put
        closer together than shapes on a different net.
        """
        return _SameNet(mask=self)

    @abc.abstractproperty
    def designmasks(self) -> Iterable["DesignMask"]: # pragma: no cover
        """The designasks property of a `MaskT` object gives a list of
        all designamsks used in a `MaskT`.

        API Notes:
            * The returned Iterable may contain same `DesignMask` object multiple
              times. User who need a unique set can use a `set` object for that.
        """
        ...

    @abc.abstractmethod
    def __eq__(self, other: object) -> bool: # pragma: no cover
        ...

    # When subclasses need to define __eq__ they also need to define
    # __hash__(); otherwise the subclass is considered to not be hashable
    @abc.abstractmethod
    def __hash__(self) -> int:
        # Assume mask names are different so will also give different hash
        return hash(self.name)
MaskT = _Mask


class _RuleMask(_Mask, _rle._Rule):
    "A `MaskT` object that is also a `RuleT` object"
    pass
RuleMaskT = _RuleMask


class DesignMask(_RuleMask):
    """A `DesignMask` object is a `_Mask` object with the shapes on the mask
    provided by shapes by the user. It is not a derived mask.

    Arguments:
        name: the name of the mask
    """
    def __init__(self, *, name: str):
        super().__init__(name=name)

        self.grid: _prp.PropertyT = _MaskProperty(mask=self, name="grid")

    def __repr__(self) -> str:
        return f"design({self.name})"

    @property
    def designmasks(self) -> Iterable["DesignMask"]:
        return (self,)

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, DesignMask)
            and (self.name == other.name)
        )

    def __hash__(self) -> int:
        return super().__hash__()


class _PartsWith(_Mask):
    """`_Mask.parts_with()` support class"""
    def __init__(self, *,
        mask: MaskT, condition: MultiT[_prp.ComparisonT],
    ):
        self.mask = mask

        condition = cast_MultiT(condition)
        if not all(
            (
                isinstance(cond.left, _MaskProperty)
                and cond.left.mask == mask
            ) for cond in condition
        ):
            raise TypeError(
                "condition has to a single or an iterable of condition on properties of mask '{}'".format(
                    mask.name,
                ))
        self.condition = condition

        super().__init__(name="{}.parts_with({})".format(
            mask.name, ",".join(str(cond) for cond in condition),
        ))

    @property
    def designmasks(self) -> Iterable[DesignMask]:
        return self.mask.designmasks

    def __eq__(self, other: object) -> bool:
        if type(self) != type(other):
            return False
        else:
            other = cast(_PartsWith, other)
            return (
                (self.mask == other.mask)
                and (self.condition == other.condition)
            )

    def __hash__(self) -> int:
        return super().__hash__()


class Join(_Mask):
    """A derived `_Mask` object that represenet the shapes resulting of joining
    all the shapes of the provided masks.
    """
    def __init__(self, masks: MultiT[MaskT], *args: MaskT):
        self.masks = masks = (*cast_MultiT(masks), *args)

        super().__init__(name="join({})".format(",".join(mask.name for mask in masks)))

        self._hash: Optional[int] = None

    @property
    def designmasks(self) -> Iterable[DesignMask]:
        for mask in self.masks:
            yield from mask.designmasks

    def __eq__(self, other: object) -> bool:
        if self.__class__ is not other.__class__:
            return False
        else:
            other = cast("Join", other)
            return set(self.masks) == set(other.masks)

    def __hash__(self) -> int:
        if self._hash is None:
            # Convert designmasks to a set to remove duplicates
            # Then compute hash on sorted mask names
            self._hash = hash(tuple(sorted(
                m.name for m in set(self.designmasks)
            )))
        return self._hash


class Intersect(_Mask):
    """A derived `_Mask` object that represenet the shapes resulting of
    the intersection of all the shapes of the provided masks.
    """
    def __init__(self, masks: MultiT[MaskT]):
        self.masks = masks = cast_MultiT(masks)

        super().__init__(name="intersect({})".format(",".join(mask.name for mask in masks)))

        self._hash: Optional[int] = None

    @property
    def designmasks(self) -> Iterable[DesignMask]:
        for mask in self.masks:
            yield from mask.designmasks

    def __eq__(self, other: object) -> bool:
        if self.__class__ is not other.__class__:
            return False
        else:
            other = cast("Intersect", other)
            return set(self.masks) == set(other.masks)

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(tuple(sorted(
                set(self.designmasks),
                key=(lambda m: m.name),
            )))
        return self._hash


class _MaskRemove(_Mask):
    """`_Mask.remove()` support class"""
    def __init__(self, *, from_: MaskT, what: MaskT):
        super().__init__(name=f"{from_.name}.remove({what.name})")
        self.from_ = from_
        self.what = what

    @property
    def designmasks(self) -> Iterable[DesignMask]:
        for mask in (self.from_, self.what):
            yield from mask.designmasks

    def __eq__(self, other: object) -> bool:
        if self.__class__ is not other.__class__:
            return False
        else:
            other = cast(_MaskRemove, other)
            return (
                (self.from_ == other.from_)
                and (self.what == other.what)
            )

    def __hash__(self) -> int:
        return hash((self.from_, self.what))


class _MaskAlias(_RuleMask):
    """`_Mask.alias()` support class"""
    def __init__(self, *, name: str, mask: MaskT):
        self.mask = mask

        super().__init__(name=name)

    def __repr__(self) -> str:
        return f"{self.mask.name}.alias({self.name})"

    @property
    def designmasks(self) -> Iterable[DesignMask]:
        return self.mask.designmasks

    def __eq__(self, other: object) -> bool:
        if self.__class__ is not other.__class__:
            return False
        else:
            other = cast(_MaskAlias, other)
            return (
                (self.name == other.name)
                and (self.mask == other.mask)
            )

    def __hash__(self) -> int:
        return super().__hash__()


class Spacing(_DualMaskProperty):
    """A `Spacing` object is a `Property` that represents the spacing
    between two shapes on two different masks.  
    The masks may not be the same. For the space between shapes on the same
    mask use the `MaskT.space` property.
    """
    def __init__(self, mask1: MaskT, mask2: MaskT):
        if mask1 == mask2:
            raise ValueError(
                f"mask1 and mask2 may not be the same for 'Spacing'\n"
                "use `MaskT.space` property for that"
            )
        super().__init__(mask1=mask1, mask2=mask2, name="space", commutative=True)


class Connect(_rle._Rule):
    """A `Connect` object is a `_Rule` indicating that overlapping shapes on two
    different layers are connecting with each other. This rule is base to determine
    connectivity and which shapes are on the same net.

    The 'Connect` rules is not associative. For example a `Via` connects to the bottom
    and top layer(s) but the bottom and top layer(s) typically don't connect to each
    other directly.  
    The `Connect` rule is commutative. Meaning that exchanging `mask1` and `mask2`
    arguments results in the same `Connect` rule.

    A `Connect` object is created by specifying to mask arguments `mask1` and `mask2`.
    Each of them can be one or more masks. The `Connect` rule then specifies that
    each shape on one of the masks in `mask1` that overlaps with a shape on one of
    the masks from `mask2` is connecting to it.
    """
    def __init__(self,
        mask1: MultiT[MaskT], mask2: MultiT[MaskT],
    ):
        self.mask1 = mask1 = cast_MultiT(mask1)
        self.mask2 = mask2 = cast_MultiT(mask2)

        self._hash: Optional[int] = None

    def __eq__(self, other: object) -> bool:
        if self.__class__ is not other.__class__:
            return False
        else:
            other = cast("Connect", other)

            masks1 = set(self.mask1)
            masks2 = set(self.mask2)

            others1 = set(other.mask1)
            others2 = set(other.mask2)

            return (
                ((masks1 == others1) and (masks2 == others2))
                or ((masks1 == others2) and (masks2 == others1))
            )

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(tuple(sorted(m.name for m in (*self.mask1, *self.mask2))))
        return self._hash

    def __repr__(self) -> str:
        s1 = self.mask1[0].name if len(self.mask1) == 1 else "({})".format(
            ",".join(m.name for m in self.mask1)
        )
        s2 = self.mask2[0].name if len(self.mask2) == 1 else "({})".format(
            ",".join(m.name for m in self.mask2)
        )
        return f"connect({s1},{s2})"


class _SameNet(_Mask):
    """`_Mask.same_net()` support class"""
    def __init__(self, mask: MaskT):
        self.mask = mask

        super().__init__(name=f"same_net({mask.name})")

    @property
    def designmasks(self) -> Iterable[DesignMask]:
        return self.mask.designmasks

    def __eq__(self, other: object) -> bool:
        if self.__class__ is not other.__class__:
            return False
        else:
            other = cast(_SameNet, other)
            return self.mask == other.mask

    def __hash__(self) -> int:
        return super().__hash__()
