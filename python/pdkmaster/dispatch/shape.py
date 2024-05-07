# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from typing import Optional, Callable

from ..technology import geometry as _geo


class ShapeDispatcher:
    """Dispatch to class method based on type of `_Shape` subclasses.

    This dispatcher follows the common way of working in the `dispatch` module.
    Exception is the "geometry.MultiPartShape._Part", for this one can overload
    the `MultiPartShape__Part` method. The default implementation with call the
    dispatcher on the `part_shape` of the given object. Assume that dispatcher is
    called with a `MultiPartShape._Part` with object `part` with `part.part_shape`
    of type `Rect`. Then the default implement will call the `Rect` method with
    `part.part_shape` as shape.
    """
    def __init__(self):
        self._parent_call: Optional[Callable] = None

    def __call__(self, shape: _geo._Shape, *args, **kwargs):
        # Reset _parent_call
        self._parent_call = None

        if isinstance(shape, _geo.MultiPartShape._Part):
            classname = "MultiPartShape__Part"
        else:
            classname = shape.__class__.__name__.split(".")[-1]
        return getattr(self, classname, self._pd_unhandled)(shape, *args, **kwargs)

    def _pd_unhandled(self, shape: _geo._Shape, *args, **kwargs):
        raise RuntimeError(
            "Internal error: unhandled dispatcher for object of type "
            f"{shape.__class__.__name__}"
        )

    def _Shape(self, shape: _geo._Shape, *args, **kwargs):
        """This for the base class and by default raises NotImplementedError
        """
        raise NotImplementedError(
            f"No dispatcher implemented for object of type {shape.__class__.__name__}"
        )

    def _Rectangular(self, shape: _geo._Rectangular, *args, **kwargs):
        return self._Shape(shape, *args, **kwargs)

    def _PointsShape(self,
        shape: _geo._PointsShape, *args, **kwargs,
    ):
        if self._parent_call is None:
            call = self._Shape
        else:
            call = self._parent_call
            self._parent_call = None
        return call(shape, *args, **kwargs)

    def Point(self, point: _geo.Point, *args, **kwargs):
        self._parent_call = self._Rectangular
        return self._PointsShape(point, *args, **kwargs)

    def Line(self, line: _geo.Line, *args, **kwargs):
        self._parent_call = self._Rectangular
        return self._PointsShape(line, *args, **kwargs)

    def Polygon(self,
        polygon: _geo.Polygon, *args, **kwargs,
    ):
        # _parent_call is kept and used in self._PointsShape
        return self._PointsShape(polygon, *args, **kwargs)

    def Rect(self, rect: _geo.Rect, *args, **kwargs):
        self._parent_call = self._Rectangular
        return self.Polygon(rect, *args, **kwargs)

    def MultiPath(self, mp: _geo.MultiPath, *args, **kwargs):
        return self.Polygon(mp, *args, **kwargs)

    def Ring(self, ring: _geo.Ring, *args, **kwargs):
        return self.MultiPath(ring, *args, **kwargs)

    def RectRing(self, ring: _geo.RectRing, *args, **kwargs):
        return self._Shape(ring, *args, **kwargs)

    def Label(self, label: _geo.Label, *args, **kwargs):
        return self._Shape(label, *args, **kwargs)

    def MultiPartShape(self, mps: _geo.MultiPartShape, *args, **kwargs):
        return self.Polygon(mps, *args, **kwargs)

    def MultiPartShape__Part(self, part: _geo.MultiPartShape._Part, *args, **kwargs):
        return self(part._partshape, *args, **kwargs)

    def MultiShape(self, ms: _geo.MultiShape, *args, **kwargs):
        return self._Shape(ms, *args, **kwargs)

    def RepeatedShape(self, rs: _geo.RepeatedShape, *args, **kwargs):
        return self._Shape(rs, *args, **kwargs)

    def ArrayShape(self, array: _geo.ArrayShape, *args, **kwargs):
        return self.RepeatedShape(array, *args, **kwargs)
