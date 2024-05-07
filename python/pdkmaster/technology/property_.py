# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from typing import Any, Iterable, Tuple, Union, ClassVar, overload

from . import rule as _rle


__all__ = [
    "Enclosure", "PropertyT", "EnclosurePropertyT", "ComparisonT",
    "Operators", "Ops",
]


class Enclosure:
    """Enclosure object are representing the enclosure value of one layer
    over another layer. Most of the time it is used to indicae the
    minimum required enclosure of one layer over another layer.

    Enclosure constraints can symmetric or asymmetric. A symmetric
    enclosure can be specified with a single float value, an assymetric one
    with two float values. Internally always two float values are stored and
    be accessed through the `spec` attribute of an Enclosure object. For a
    symmetric object the two float values are the same.

    When an enclosure is used as a constraint symmetric means that the
    enclosure has to be met in all directions. Asymmetric normally means
    that a smaller enclosure in one direction is allowed when both enclosures
    in the other direction are bigger than the bigger enclosure value.
    For this case the order of the two value don't have a meaning.

    An enclosure can also be used to specify when doing layout generation.
    The PDKMaster convention here is that the order has a meaning; the first
    value is for the horizontal direction and the second value for the
    vertical one. Also giving meaning to the `wide()` and `tall()` object methods

    Enclosure objects are implemented as immutable objects.
    """
    def __init__(self, spec: Union[float, Iterable[float]]):
        self._spec: Tuple[float, float]
        if isinstance(spec, float):
            self._spec = (spec, spec)
        else:
            self._spec = tuple(spec)
            if len(self.spec) != 2:
                raise ValueError(
                    f"spec for Enclosure is either a float or 2 floats"
                )

    @property
    def spec(self) -> Tuple[float, float]:
        return self._spec

    @staticmethod
    def cast(v: Union[float, Iterable[float], "Enclosure"]) -> "Enclosure":
        if isinstance(v, Enclosure):
            return v
        else:
            return Enclosure(spec=v)

    @property
    def first(self) -> float:
        return self.spec[0]

    @property
    def second(self) -> float:
        return self.spec[1]

    @property
    def is_assymetric(self) -> bool:
        return self.first != self.second

    def min(self) -> float:
        return min(self.spec)

    def max(self) -> float:
        return max(self.spec)

    def wide(self) -> "Enclosure":
        # Put bigger enclosure value first
        if self.first >= self.second:
            return self
        else:
            return Enclosure(spec=(self.second, self.first))

    def tall(self) -> "Enclosure":
        if self.first <= self.second:
            return self
        else:
            return Enclosure(spec=(self.second, self.first))

    def __hash__(self) -> int:
        return hash(self._spec)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Enclosure):
            return False
        else:
            return (
                (self.first == other.first)
                and (self.second == other.second)
            )

    def __repr__(self) -> str:
        if not self.is_assymetric:
            return f"Enclosure({round(self.first, 6)})"
        else:
            return f"Enclosure(({round(self.spec[0], 6)},{round(self.spec[1], 6)}))"


class _Property:
    """This class represents a property of an object. Rules may be built from
    from a comparison operation.

        o = Property(name='width')
        rule = o >= 3.5

    Then `rule` represents the rule for width greater or equal to 3.5.
    """
    value_conv: Any = None
    value_type: Union[type, Tuple[type, ...]] = (float, int)
    value_type_str: str = "float"

    def __init__(self, *, name: str, allow_none: bool=False):
        self.name = name
        self.allow_none = allow_none

        value_type = self.value_type
        if not isinstance(value_type, tuple):
            if issubclass(value_type, _Property):
                raise TypeError("Property.value_type may not be 'Property'")

        self.dependencies = set()

    def __gt__(self, other) -> "ComparisonT":
        return Ops.Greater(left=self, right=other)
    def __ge__(self, other) -> "ComparisonT":
        return Ops.GreaterEqual(left=self, right=other)
    def __lt__(self, other) -> "ComparisonT":
        return Ops.Smaller(left=self, right=other)
    def __le__(self, other) -> "ComparisonT":
        return Ops.SmallerEqual(left=self, right=other)
    @overload
    def __eq__(self, other: "_Property") -> bool:
        ... # pragma: no cover
    @overload
    def __eq__(self, other: Any) -> "ComparisonT":
        ... # pragma: no cover
    def __eq__(self, other: Any) -> Union[bool, "ComparisonT"]:
        """The __eq__() method for Property can have two meanings. If it is
        compared with another Property object it will check if it is the same
        property. For another object it will generate a Rule object representing
        that property being equal to the provided value.
        """
        try:
            return Ops.Equal(left=self, right=other)
        except TypeError:
            return isinstance(other, _Property) and (self.name == other.name)

    def __str__(self) -> str:
        return f"{self.name}"
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, allow_non={self.allow_none!r})"

    def __hash__(self) -> int:
        return hash(self.name)

    def cast(self, value):
        if value is None:
            if self.allow_none:
                return None
            else:
                raise TypeError(
                    f"property '{self.name}' given value '{value!r}' is not of type "
                    f"'{self.value_type_str}'"
                )

        value_conv = self.__class__.value_conv
        if value_conv is not None:
            try:
                value = value_conv(value)
            except:
                raise TypeError("could not convert property value {!r} to type '{}'".format(
                    value, self.value_type_str,
                ))
        if not isinstance(value, self.value_type):
            raise TypeError(
                f"value '{value!r}' for property '{self.name}' is not of type "
                f"'{self.value_type_str}'",
            )
        return value
PropertyT = _Property


class _EnclosureProperty(_Property):
    """An EnclosureProperty object is a Property with an Enclosure object as value.
    """
    value_conv = Enclosure.cast
    value_type = Enclosure
    value_type_str = "'Enclosure'"
EnclosurePropertyT = _EnclosureProperty


class _Comparison(_rle._Condition):
    """A _Comparison object is a _Condition which represent the comparison of a Property
    object with a value. The operator for the comparison is represented as a string class
    variable names `symbol`.
    """
    symbol: ClassVar[str]

    def __init__(self, *, left: _Property, right: Any):
        try:
            self.symbol
        except AttributeError:
            raise TypeError(
                f"class '{self.__class__.__name__}' does not have the"
                " symbol class variable defined"
            )

        right2 = left.cast(right)

        super().__init__(elements=(left, right2))
        self._elements: Tuple[_Property, Any]

    @property
    def left(self) -> _Property:
        return self._elements[0]
    @property
    def right(self) -> Any:
        return self._elements[1]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _Comparison):
            return False
        else:
            return (
                (self.symbol == other.symbol)
                and (self.left == other.left)
                and (self.right == other.right)
            )

    def __str__(self) -> str:
        return f"{self.left} {self.symbol} {self.right}"
    def __repr__(self) -> str:
        return f"{self.left!r} {self.symbol} {self.right!r}"

    def __bool__(self) -> bool:
        raise TypeError("BinaryPropertyCondition can't be converted to a bool")
ComparisonT = _Comparison


class Operators:
    """Operators is a class representing a bunch of boolean operators.
    """
    class Greater(_Comparison):
        symbol = ">"
    class GreaterEqual(_Comparison):
        symbol = ">="
    class Smaller(_Comparison):
        symbol = "<"
    class SmallerEqual(_Comparison):
        symbol = "<="
    class Equal(_Comparison):
        symbol = "=="

        def __bool__(self):
            # When == needs to be interpreted as a bool inside the script it is False
            # It has only to be True when it compared to another Property.
            return False

    # Convenience assigns
    GT = Greater
    GE = GreaterEqual
    ST = Smaller
    SE = SmallerEqual
    EQ = Equal
# Convenience assigns
Ops = Operators
