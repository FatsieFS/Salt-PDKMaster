# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from ..technology import mask as _msk, wafer_ as _wfr


class MaskDispatcher:
    """Dispatch to class method based on type of `_Mask` subclasses.

    This dispatcher follows the common way of working in the `dispatch` module.
    """
    def __call__(self, mask: _msk.MaskT, *args, **kwargs):
        classname = mask.__class__.__name__.split(".")[-1]
        return getattr(self, classname, self._pd_unhandled)(mask, *args, **kwargs)

    def _pd_unhandled(self, mask, *args, **kwargs):
        raise RuntimeError(
            "Internal error: unhandled dispatcher for object of type "
            f"{mask.__class__.__name__}"
        )

    def _Mask(self, mask: _msk.MaskT, *args, **kwargs):
        raise NotImplementedError(
            f"No dispatcher implemented for object of type {mask.__class__.__name__}"
        )

    def _RuleMask(self, mask: _msk._RuleMask, *args, **kwargs):
        return self._Mask(mask, *args, **kwargs)

    def DesignMask(self, mask: _msk.DesignMask, *args, **kwargs):
        return self._RuleMask(mask, *args, **kwargs)

    def _PartsWith(self, pw: _msk._PartsWith, *args, **kwargs):
        return self._Mask(pw, *args, **kwargs)

    def Join(self, join: _msk.Join, *args, **kwargs):
        return self._Mask(join, *args, **kwargs)

    def Intersect(self, intersect: _msk.Intersect, *args, **kwargs):
        return self._Mask(intersect, *args, **kwargs)

    def _MaskRemove(self, mr: _msk._MaskRemove, *args, **kwargs):
        return self._Mask(mr, *args, **kwargs)

    def _MaskAlias(self, mask: _msk._MaskAlias, *args, **kwargs):
        return self._RuleMask(mask, *args, **kwargs)

    def _SameNet(self, same: _msk._SameNet, *args, **kwargs):
        return self._Mask(same, *args, **kwargs)

    def _Wafer(self, wafer: _wfr._Wafer, *args, **kwargs):
        return self._Mask(wafer, *args, **kwargs)
