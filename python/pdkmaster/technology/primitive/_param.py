# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from .. import rule as _rle, property_ as _prp

from . import _core


class _PrimParam(_prp._Property):
    def __init__(self, *, primitive: "_core._Primitive", name: str, allow_none=False, default=None):
        super().__init__(name=name, allow_none=allow_none)

        self._primitive = primitive

        if default is not None:
            try:
                default = self.cast(default)
            except TypeError:
                raise TypeError(
                    f"default can't be converted to type '{self.value_type_str}'"
                )
            self.default = default

    def cast(self, value):
        if (value is None) and hasattr(self, "default"):
            return self.default
        else:
            return super().cast(value)

    def __eq__(self, other):
        equal = super().__eq__(other)
        if isinstance(equal, _rle.RuleT):
            return equal
        else:
            return (
                equal
                and isinstance(other, _PrimParam)
                and (self._primitive == other._primitive)
            )
