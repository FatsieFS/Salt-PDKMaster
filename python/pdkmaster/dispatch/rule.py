# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from ..technology import rule as _rle, property_ as _prp, mask as _msk


class RuleDispatcher:
    """Dispatch to class method based on type of `_Rule` subclasses.

    This dispatcher follows the common way of working in the `dispatch` module.
    """
    def __call__(self, rule: _rle.RuleT, *args, **kwargs):
        classname = rule.__class__.__name__.split(".")[-1]
        return getattr(self, classname, self._pd_unhandled)(rule, *args, **kwargs)

    def _pd_unhandled(self, rule, *args, **kwargs):
        raise RuntimeError(
            "Internal error: unhandled dispatcher for object of type "
            f"{rule.__class__.__name__}"
        )

    # pdkmaster.technology.rule

    def _Rule(self, rule: _rle.RuleT, *args, **kwargs):
        raise NotImplementedError(
            f"No dispatcher implemented for object of type {rule.__class__.__name__}"
        )

    def _Condition(self, cond: _rle.ConditionT, *args, **kwargs):
        return self._Rule(cond, *args, **kwargs)

    # pdkmaster.technology.property_

    def _Comparison(self, cond: _prp._Comparison, *args, **kwargs):
        return self._Condition(cond, *args, **kwargs)

    def Greater(self, gt: _prp.Operators.Greater, *args, **kwargs):
        return self._Comparison(gt, *args, **kwargs)

    def GreaterEqual(self, ge: _prp.Operators.GreaterEqual, *args, **kwargs):
        return self._Comparison(ge, *args, **kwargs)

    def Smaller(self, st: _prp.Operators.Smaller, *args, **kwargs):
        return self._Comparison(st, *args, **kwargs)

    def SmallerEqual(self, se: _prp.Operators.SmallerEqual, *args, **kwargs):
        return self._Comparison(se, *args, **kwargs)

    def Equal(self, eq: _prp.Operators.Equal, *args, **kwargs):
        return self._Comparison(eq, *args, **kwargs)

    # pdkmaster.technology.mask

    def _MultiMaskCondition(self, cond: _msk._MultiMaskCondition, *args, **kwargs):
        return self._Condition(cond, *args, **kwargs)

    def _InsideCondition(self, cond: _msk._InsideCondition, *args, **kwargs):
        return self._MultiMaskCondition(cond, *args, **kwargs)

    def _OutsideCondition(self, cond: _msk._OutsideCondition, *args, **kwargs):
        return self._MultiMaskCondition(cond, *args, **kwargs)

    def _RuleMask(self, mask: _msk._RuleMask, *args, **kwargs):
        return self._Rule(mask, *args, **kwargs)

    def DesignMask(self, mask: _msk.DesignMask, *args, **kwargs):
        return self._RuleMask(mask, *args, **kwargs)

    def _MaskAlias(self, alias: _msk._MaskAlias, *args, **kwargs):
        return self._RuleMask(alias, *args, **kwargs)

    def Connect(self, conn: _msk.Connect, *args, **kwargs):
        return self._Rule(conn, *args, **kwargs)
