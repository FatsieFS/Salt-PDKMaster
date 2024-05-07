# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
import abc
from typing import Tuple, Any

from .. import _util


__all__ = ["RuleT", "ConditionT", "Rules"]


class _Rule(abc.ABC):
    """_Rule is an abstract base to represent a rule. Functionality of a rule
    need to be implemented in the subclasses.
    """
    @abc.abstractmethod
    def __init__(self): # pragma: no cover
        pass

    @abc.abstractmethod
    def __eq__(self, other: object) -> bool:
        raise TypeError("subclasses of _Rule need to implement __eq__()")

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __bool__(self) -> bool:
        raise ValueError("Rule can't be converted to 'bool'")

    @abc.abstractmethod
    def __hash__(self) -> int:
        raise TypeError("subclasses of _Rule need to implement __hash__()")
RuleT = _Rule


class Rules(_util.ExtendedList[_Rule]):
    pass


class _Condition(_Rule):
    """_Condition is a _Rule subclass that represent a contraint on an object.

    _Condition is an abstract base class that needs to be subclassed.

    _Condition objects are immutable. For convenience the __init__() of this base class
    allows to specify the elements which make this object unique so the subclass does
    not need implement the __eq__() and __hash__() method. Objects of different
    subclasses from each other are considered unequal even if one is subclass of the
    other.
    """
    @abc.abstractmethod
    def __init__(self, *, elements: Tuple[Any, ...]):
        self._elements = elements

    def __hash__(self) -> int:
        return hash(self._elements)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, _Condition):
            return False
        else:
            return (
                (self.__class__ is other.__class__)
                and (self._elements == other._elements)
            )

    @abc.abstractmethod
    def __repr__(self) -> str: # pragma: no cover
        raise RuntimeError("_Condition subclass needs to implement __repr__() method")
ConditionT = _Condition
