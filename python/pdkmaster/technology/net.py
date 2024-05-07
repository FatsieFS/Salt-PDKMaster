# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
import abc
from typing import Type, Tuple, Union

from .. import _util


__all__ = ["NetT", "Nets"]


class _Net(abc.ABC):
    @abc.abstractmethod
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Net) and (self.name == other.name)

    def __hash__(self) -> int:
        return hash(self.name)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.name})"
NetT = _Net


Nets =_util.ExtendedListStrMapping[_Net]
