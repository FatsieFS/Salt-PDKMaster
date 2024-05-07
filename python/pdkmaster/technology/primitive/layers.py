# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from enum import Enum
from typing import Iterable
from warnings import warn

from .. import rule as _rle, wafer_ as _wfr, technology_ as _tch

from ._core import (
    _MaskPrimitive, _DesignMaskPrimitive, _WidthSpaceDesignMaskPrimitive,
)


__all__ = [
    "Base", "BaseTypeT", "nBase", "pBase", "undopedBase",
    "Marker", "SubstrateMarker", "Auxiliary", "ExtraProcess", "Insulator",
    "Implant", "ImplantTypeT", "nImpl", "pImpl", "adjImpl",
]


class Base(_MaskPrimitive):
    class BaseType(Enum):
        n = "n"
        p = "p"
        undoped = "undoped"

    def __init__(self, *, type_: "BaseTypeT"):
        super().__init__(name="base", mask=_wfr.wafer)

        self._type = type_

    @property
    def type_(self) -> "Base.BaseType":
        return self._type

    def _generate_rules(self, *,
        tech: _tch.Technology, gen_mask: bool = True,
    ) -> Iterable[_rle.RuleT]:
        return super()._generate_rules(tech=tech, gen_mask=gen_mask)
BaseTypeT = Base.BaseType
nBase = Base.BaseType.n
pBase = Base.BaseType.p
undopedBase = Base.BaseType.undoped


class Marker(_DesignMaskPrimitive):
    """The Marker primitive represents a layer used by other primitives for definition
    of these primitives; typically a recognition.
    It does not represent a processing layer and thus no physical mask is corresponding
    with this primitive.
    """
    def __init__(self, **super_args):
        super().__init__(**super_args)

    def _generate_rules(self, *,
        tech: _tch.Technology,
    ) -> Iterable[_rle.RuleT]:
        return super()._generate_rules(tech=tech)


class SubstrateMarker(Marker):
    """Often PDKs provide a marker layer to indicate substrate regions that have a net
    connected different than the common ground substrate connection. This marker layer
    is reserved for such purposes.
    Currently no assumptions are made on how such a marker layer is to be used and thus
    no checks on proper use are implemented.
    """
    pass


class Auxiliary(_DesignMaskPrimitive):
    """The Auxiliary primitive represents a layer that is defined by a foundry's
    technology but not used in other PDKMaster primitives.
    """
    def __init__(self, **super_args):
        super().__init__(**super_args)

    def _generate_rules(self, *,
        tech: _tch.Technology,
    ) -> Iterable[_rle.RuleT]:
        return super()._generate_rules(tech=tech)


class ExtraProcess(_WidthSpaceDesignMaskPrimitive):
    """ExtraProcess is a layer indicating an ExtraProcess step not handled
    by other primitives.

    For example non-silicidation for making active or poly resistors.
    """
    def __init__(self, **super_args):
        super().__init__(**super_args)

    def _generate_rules(self, *,
        tech: "_tch.Technology",
    ) -> Iterable[_rle.RuleT]:
        return super()._generate_rules(tech=tech)


class Insulator(_WidthSpaceDesignMaskPrimitive):
    """Insulator is a layer representing an insulator layer.

    Typical use is for thick oxide layer for higher voltage transistors.
    """
    def __init__(self, **super_args):
        super().__init__(**super_args)

    def _generate_rules(self, *,
        tech: "_tch.Technology",
    ) -> Iterable[_rle.RuleT]:
        return super()._generate_rules(tech=tech)


class Implant(_WidthSpaceDesignMaskPrimitive):
    """Implant is a layer that represent an implantation step in the
    semiconductor processing.

    Arguments:
        type_: type of the implant
            an "adjust" implant layer is extra implant that can be used on
            both n-type and p-type regions.
        super_args: `_WidthSpacePrimitive` and `_DesignMaskPrimitive`
            arguments
    """
    class ImplantType(Enum):
        """The type of implant.
        Currently implemented types are: n, p, adjust. The .value of the enum
        object is the string of the type; e.g. "n", "p", ...

        These types are also made available as `nImpl`, `pImpl` and `adjImpl`
        in the primitive module.
        """
        n = "n"
        p = "p"
        adjust = "adjust"

        def __hash__(self) -> int:
            return super().__hash__()

        def __eq__(self, __o: object) -> bool:
            if isinstance(__o, str):
                warn("Comparison of `ImplantType` with `str` always returns `False`")
            return super().__eq__(__o)

    # Implants are supposed to be disjoint unless they are used as combined implant
    # MOSFET and other primitives
    def __init__(self, *, type_: ImplantType, **super_args):
        super().__init__(**super_args)

        self._type = type_

    def _generate_rules(self, *,
        tech: "_tch.Technology",
    ) -> Iterable[_rle.RuleT]:
        return super()._generate_rules(tech=tech)

    @property
    def type_(self) -> ImplantType:
        return self._type
ImplantTypeT = Implant.ImplantType
nImpl = Implant.ImplantType.n
pImpl = Implant.ImplantType.p
adjImpl = Implant.ImplantType.adjust
