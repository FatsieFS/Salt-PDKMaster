# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from typing import Callable, Optional

from ..technology import primitive as _prm
from ..technology.primitive.conductors import _WaferWireIntersect, _ViaIntersect


class PrimitiveDispatcher:
    """Dispatch to class method based on type of `_Primitive` subclasses.

    This dispatcher follows the common way of working in the `dispatch` module.
    """
    def __init__(self):
        self._parent_call: Optional[Callable] = None

    def __call__(self, prim: _prm.PrimitiveT, *args, **kwargs):
        # Reset _parent_call
        self._parent_call = None

        classname = prim.__class__.__name__.split(".")[-1]
        return getattr(self, classname, self._pd_unhandled)(prim, *args, **kwargs)

    def _pd_unhandled(self, prim, *args, **kwargs):
        raise RuntimeError(
            "Internal error: unhandled dispatcher for object of type "
            f"{prim.__class__.__name__}"
        )

    ### primitive._core

    def _Primitive(self, prim: _prm.PrimitiveT, *args, **kwargs):
        """Currently _PinAttribute and _BlockageAttribute are not handled by the
        dispatcher. It can be handled by overloading this _Primitive method and
        checking there oneself if the provided primitive is an instance of one
        of these classes.
        """
        raise NotImplementedError(
            f"No dispatcher implemented for object of type {prim.__class__.__name__}"
        )

    def _MaskPrimitive(self, prim: _prm.MaskPrimitiveT, *args, **kwargs):
        return self._Primitive(prim, *args, **kwargs)

    def _DesignMaskPrimitive(self,
        prim: _prm.DesignMaskPrimitiveT, *args, **kwargs,
    ):
        return self._MaskPrimitive(prim, *args, **kwargs)

    def _WidthSpacePrimitive(self, prim: _prm.WidthSpacePrimitiveT, *args, **kwargs):
        if isinstance(prim, _prm.DesignMaskPrimitiveT):
            return self._DesignMaskPrimitive(prim, *args, **kwargs)
        else:
            return self._MaskPrimitive(prim, *args, **kwargs)

    def _WidthSpaceDesignMaskPrimitive(self,
        prim: _prm.WidthSpaceDesignMaskPrimitiveT, *args, **kwargs,
    ):
        # _DesignMaskPrimitive is handled by _WidthSpacePrimitive() if needed.
        return self._WidthSpacePrimitive(prim, *args, **kwargs)

    ### primitive._derived

    def _DerivedPrimitive(self, prim: _prm._derived._DerivedPrimitive, *args, **kwargs):
        """
        API Notes:
            * No backwards compatiblity is provided for overloading this function
              in user land code. _DerivedPrimitive is considered for internal use only.
        """
        return self._MaskPrimitive(prim, *args, **kwargs)

    def _Intersect(self, prim: _prm._derived._Intersect, *args, **kwargs):
        """
        API Notes:
            * No backwards compatiblity is provided for overloading this function
              in user land code. _Intersect is considered for internal use only.
        """
        return self._DerivedPrimitive(prim, *args, **kwargs)

    def _Outside(self, prim: _prm._derived._Outside, * args, **kwargs):
        """
        API Notes:
            * No backwards compatiblity is provided for overloading this function
              in user land code. _Outside is considered for internal use only.
        """
        return self._DerivedPrimitive(prim, *args, **kwargs)

    ### primitive.layers

    def Base(self, prim: _prm.Base, *args, **kwargs):
        return self._MaskPrimitive(prim, *args, **kwargs)

    def Marker(self, prim: _prm.Marker, *args, **kwargs):
        return self._DesignMaskPrimitive(prim, *args, **kwargs)

    def SubstrateMarker(self, prim: _prm.Marker, *args, **kwargs):
        return self.Marker(prim, *args, **kwargs)

    def Auxiliary(self, prim: _prm.Auxiliary, *args, **kwargs):
        return self._DesignMaskPrimitive(prim, *args, **kwargs)

    def ExtraProcess(self, prim: _prm.ExtraProcess, *args, **kwargs):
        return self._WidthSpaceDesignMaskPrimitive(prim, *args, **kwargs)

    def Insulator(self, prim: _prm.Insulator, *args, **kwargs):
        return self._WidthSpaceDesignMaskPrimitive(prim, *args, **kwargs)

    def Implant(self, prim: _prm.Implant, *args, **kwargs):
        if self._parent_call is None:
            call = self._WidthSpaceDesignMaskPrimitive
        else:
            call = self._parent_call
            self._parent_call = None
        return call(prim, *args, **kwargs)

    ### primitive.conductors

    def _Conductor(self,
        prim: _prm.ConductorT, *args, **kwargs,
    ):
        if isinstance(prim, _prm.WidthSpacePrimitiveT):
            return self._WidthSpacePrimitive(prim, *args, **kwargs)
        else:
            return self._DesignMaskPrimitive(prim, *args, **kwargs)

    def _WidthSpaceConductor(self,
        prim: _prm.WidthSpaceConductorT, *args, **kwargs,
    ):
        return self._Conductor(prim, *args, **kwargs)

    def Well(self, prim: _prm.Well, *args, **kwargs):
        self._parent_call = self._WidthSpaceConductor
        return self.Implant(prim=prim, *args, **kwargs)

    def DeepWell(self, prim: _prm.DeepWell, *args, **kwargs):
        self._parent_call = self._WidthSpaceConductor
        return self.Implant(prim=prim, *args, **kwargs)

    def WaferWire(self, prim: _prm.WaferWire, *args, **kwargs):
        return self._WidthSpaceConductor(prim, *args, **kwargs)

    def _WaferWireIntersect(self, prim: _WaferWireIntersect, *args, **kwargs):
        return self._Intersect(prim, *args, **kwargs)

    def GateWire(self, prim: _prm.GateWire, *args, **kwargs):
        return self._WidthSpaceConductor(prim, *args, **kwargs)

    def MetalWire(self, prim: _prm.MetalWire, *args, **kwargs):
        return self._WidthSpaceConductor(prim, *args, **kwargs)

    def MIMTop(self, prim: _prm.MIMTop, *args, **kwargs):
        return self.MetalWire(prim, *args, **kwargs)

    def TopMetalWire(self, prim: _prm.TopMetalWire, *args, **kwargs):
        return self.MetalWire(prim, *args, **kwargs)

    def Via(self, prim: _prm.Via, *args, **kwargs):
        return self._Conductor(prim, *args, **kwargs)

    def _ViaIntersect(self, prim: _ViaIntersect, *args, **kwargs):
        return self._Intersect(prim, *args, **kwargs)

    def PadOpening(self, prim: _prm.PadOpening, *args, **kwargs):
        return self._WidthSpaceConductor(prim, *args, **kwargs)

    ### primitive.devices

    def _DevicePrimitive(self, prim: _prm.DevicePrimitiveT, *args, **kwargs):
        if isinstance(prim, _prm.MaskPrimitiveT):
            return self._MaskPrimitive(prim=prim, *args, **kwargs)
        else:
            return self._Primitive(prim=prim, *args, **kwargs)

    def Resistor(self, prim: _prm.Resistor, *args, **kwargs):
        return self._DevicePrimitive(prim, *args, **kwargs)

    def _Capacitor(self, prim: _prm.CapacitorT, *args, **kwargs):
        return self._DevicePrimitive(prim, *args, **kwargs)

    def MIMCapacitor(self, prim: _prm.MIMCapacitor, *args, **kwargs):
        return self._Capacitor(prim, *args, **kwargs)

    def Diode(self, prim: _prm.Diode, *args, **kwargs):
        return self._DevicePrimitive(prim, *args, **kwargs)

    def MOSFETGate(self, prim: _prm.MOSFETGate, *args, **kwargs):
        return self._WidthSpacePrimitive(prim, *args, **kwargs)

    def MOSFET(self, prim: _prm.MOSFET, *args, **kwargs):
        return self._DevicePrimitive(prim, *args, **kwargs)

    def Bipolar(self, prim: _prm.Bipolar, *args, **kwargs):
        return self._DevicePrimitive(prim, *args, **kwargs)

    ### primitive.rules

    def _RulePrimitive(self, prim: _prm.RulePrimitiveT, *args, **kwargs):
        return self._Primitive(prim, *args, **kwargs)

    def MinWidth(self, prim: _prm.MinWidth, *args, **kwargs):
        return self._RulePrimitive(prim, *args, **kwargs)

    def Spacing(self, prim: _prm.Spacing, *args, **kwargs):
        return self._RulePrimitive(prim, *args, **kwargs)

    def Enclosure(self, prim: _prm.Enclosure, *args, **kwargs):
        return self._RulePrimitive(prim, *args, **kwargs)

    def NoOverlap(self, prim: _prm.NoOverlap, *args, **kwargs):
        return self._RulePrimitive(prim, *args, **kwargs)
