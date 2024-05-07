# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
"""The pdkmaster.design.geometry module provides classes to represent shapes drawn in
a DesignMask of a technology.

Attributes:
    epsilon: value under which two coordinate values are considered equal.
        Default is 1e-6; as coordinates are assumed to be in µm this
        corresponds with 1 fm.
    origin: (0.0, 0.0)
"""
import abc, enum
from itertools import product
from math import floor
from typing import (
    Any, Dict, Iterable, Iterator, Collection, Tuple, List,
    Optional, Union, TypeVar, cast, overload
)

from .. import _util
from ..typing import MultiT, cast_MultiT, OptMultiT, cast_OptMultiT
from . import property_ as _prp, mask as _msk


__all__ = [
    "epsilon",
    "Rotation", "FloatPoint",
    "RotationContext", "MoveContext",
    "ShapeT", "RectangularT", "PointsShapeT",
    "Point", "origin", "Line", "Polygon", "Rect", "MultiPath", "Ring", "RectRing",
    "MultiPartShape", "MultiShape",
    "RepeatedShape", "ArrayShape",
    "MaskShape", "MaskShapes",
    "Start", "SetWidth", "GoLeft", "GoDown", "GoRight", "GoUp", "Knot", "NoStart",
]


epsilon: float = 1e-6
def _eq(v1: float, v2: float):
    """Compare if two floats have a difference smaller than epsilon

    API Notes:
        This function may only be used inside this module
    """
    return (abs(v1 - v2) < epsilon)


_shape_childclass = TypeVar("_shape_childclass", bound="_Shape")


class Rotation(enum.Enum):
    """Enum type to represent supported `_Shape` rotations
    """
    No = "no"
    R0 = "no" # alias
    R90 = "90"
    R180 = "180"
    R270 = "270"
    MX = "mirrorx"
    MX90 = "mirrorx&90"
    MY = "mirrory"
    MY90 = "mirrory&90"

    @staticmethod
    def from_name(rot: str) -> "Rotation":
        """Helper function to convert a rotation string representation to
        a `Rotation` value.

        Arguments:
            rot: string r of the rotation; supported values:
                ("no", "90", "180", "270", "mirrorx", "mirrorx&90", "mirrory",
                "mirrory&90")

        Returns:
            Corresponding `Rotation` value
        """
        lookup = {
            "no": Rotation.No,
            "90": Rotation.R90,
            "180": Rotation.R180,
            "270": Rotation.R270,
            "mirrorx": Rotation.MX,
            "mirrorx&90": Rotation.MX90,
            "mirrory": Rotation.MY,
            "mirrory&90": Rotation.MY90,
        }
        assert rot in lookup
        return lookup[rot]

    @overload
    def __mul__(self, shape: "Rotation") -> "Rotation":
        ... # pragma: no cover
    @overload
    def __mul__(self, shape: _shape_childclass) -> _shape_childclass:
        ... # pragma: no cover
    @overload
    def __mul__(self, shape: "MaskShape") -> "MaskShape":
        ... # pragma: no cover
    @overload
    def __mul__(self, shape: "MaskShapes") -> "MaskShapes":
        ... # pragma: no cover
    def __mul__(self, shape) -> Union["Rotation", "ShapeT", "MaskShape", "MaskShapes"]:
        if isinstance(shape, Rotation):
            lookup: Dict["Rotation", Dict["Rotation", "Rotation"]] = {
                Rotation.R0: {
                    Rotation.R0: Rotation.R0,
                    Rotation.R90: Rotation.R90,
                    Rotation.R180: Rotation.R180,
                    Rotation.R270: Rotation.R270,
                    Rotation.MX: Rotation.MX,
                    Rotation.MX90: Rotation.MX90,
                    Rotation.MY: Rotation.MY,
                    Rotation.MY90: Rotation.MY90,
                },
                Rotation.R90: {
                    Rotation.R0: Rotation.R90,
                    Rotation.R90: Rotation.R180,
                    Rotation.R180: Rotation.R270,
                    Rotation.R270: Rotation.R0,
                    Rotation.MX: Rotation.MY90,
                    Rotation.MX90: Rotation.R270,
                    Rotation.MY: Rotation.MX90,
                    Rotation.MY90: Rotation.MX,
                },
                Rotation.R180: {
                    Rotation.R0: Rotation.R180,
                    Rotation.R90: Rotation.R270,
                    Rotation.R180: Rotation.R0,
                    Rotation.R270: Rotation.R90,
                    Rotation.MX: Rotation.MY,
                    Rotation.MX90: Rotation.MY90,
                    Rotation.MY: Rotation.MX,
                    Rotation.MY90: Rotation.MX90,
                },
                Rotation.R270: {
                    Rotation.R0: Rotation.R270,
                    Rotation.R90: Rotation.R0,
                    Rotation.R180: Rotation.R90,
                    Rotation.R270: Rotation.R180,
                    Rotation.MX: Rotation.MY90,
                    Rotation.MX90: Rotation.MX,
                    Rotation.MY: Rotation.MX90,
                    Rotation.MY90: Rotation.MY,
                },
                Rotation.MX: {
                    Rotation.R0: Rotation.MX,
                    Rotation.R90: Rotation.MX90,
                    Rotation.R180: Rotation.MY,
                    Rotation.R270: Rotation.MY90,
                    Rotation.MX: Rotation.R0,
                    Rotation.MX90: Rotation.R90,
                    Rotation.MY: Rotation.R180,
                    Rotation.MY90: Rotation.R270,
                },
                Rotation.MX90: {
                    Rotation.R0: Rotation.MX90,
                    Rotation.R90: Rotation.MY,
                    Rotation.R180: Rotation.MY90,
                    Rotation.R270: Rotation.MX,
                    Rotation.MX: Rotation.R270,
                    Rotation.MX90: Rotation.R0,
                    Rotation.MY: Rotation.R90,
                    Rotation.MY90: Rotation.R180,
                },
                Rotation.MY: {
                    Rotation.R0: Rotation.MY,
                    Rotation.R90: Rotation.MY90,
                    Rotation.R180: Rotation.MX,
                    Rotation.R270: Rotation.MX90,
                    Rotation.MX: Rotation.R180,
                    Rotation.MX90: Rotation.R270,
                    Rotation.MY: Rotation.R0,
                    Rotation.MY90: Rotation.R90,
                },
                Rotation.MY90: {
                    Rotation.R0: Rotation.MY90,
                    Rotation.R90: Rotation.MX,
                    Rotation.R180: Rotation.MX90,
                    Rotation.R270: Rotation.MY,
                    Rotation.MX: Rotation.R90,
                    Rotation.MX90: Rotation.R180,
                    Rotation.MY: Rotation.R270,
                    Rotation.MY90: Rotation.R0,
                },
            }

            return lookup[self][shape]
        elif isinstance(shape, (_Shape, MaskShape, MaskShapes)):
            if self == Rotation.R0:
                return shape
            else:
                return shape.rotated(rotation=self)
        else:
            raise TypeError(
                "unsupported operand type(s) for *: "
                f"'{self.__class__.__name__}' and '{shape.__class__.__name__}'"
            )
    __rmul__ = __mul__


class RotationContext:
    """Context for rotate operations that are considered to belong together.

    Currently it will cache rotated MultiPartShape and link part to the rotated parts.

    API Notes:
        * API of `RotationContext` is not fixed yet. No backwards compatible guarantees
          are given. User code using the class may need to be adapted in the future.
          see [#76](https://gitlab.com/Chips4Makers/PDKMaster/-/issues/76)
    """
    def __init__(self):
        self._rotation: Optional[Rotation] = None
        self._mps_cache: Dict["MultiPartShape", "MultiPartShape"] = {}

    def _rotate_part(self, *,
        part: "MultiPartShape._Part", rotation: Rotation,
    ) -> "MultiPartShape._Part":
        if self._rotation is None:
            self._rotation = rotation
        else:
            assert self._rotation == rotation

        mps = part.multipartshape
        idx = mps.parts.index(part)
        if mps in self._mps_cache:
            mps2 = self._mps_cache[mps]
        else:
            mps2 = mps.rotated(rotation=rotation)
            self._mps_cache[mps] = mps2
        return mps2.parts[idx]


class MoveContext:
    """Context for move operations that are considered to be part of one move.

    Currently it will cache moved MultiPartShape and link part to the moved parts.

    API Notes:
        * API of `MoveContext` is not fixed yet. No backwards compatible guarantees
          are given. User code using the class may need to be adapted in the future.
          see [#76](https://gitlab.com/Chips4Makers/PDKMaster/-/issues/76)
    """
    def __init__(self):
        self._dxy: Optional["Point"] = None
        self._mps_cache: Dict["MultiPartShape", "MultiPartShape"] = {}

    def _move_part(self, *, part: "MultiPartShape._Part", dxy: "Point") -> "MultiPartShape._Part":
        if self._dxy is None:
            self._dxy = dxy
        else:
            assert self._dxy == dxy
        mps = part.multipartshape
        idx = mps.parts.index(part)
        try:
            mps2 = self._mps_cache[mps]
        except KeyError:
            mps2 = mps.moved(dxy=dxy)
            self._mps_cache[mps] = mps2
        return mps2.parts[idx]


class _Shape(abc.ABC):
    """The base class for representing shapes

    API Notes:
        * _Shape objects need to be immutable objects. They need to implement
          __hash__() and __eq__()
    """
    @abc.abstractmethod
    def __init__(self):
        pass

    @property
    @abc.abstractmethod
    def pointsshapes(self) -> Iterable["PointsShapeT"]:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def bounds(self) -> "RectangularT":
        raise NotImplementedError

    @abc.abstractmethod
    def moved(
        self: "_shape_childclass", *,
        dxy: "Point", context: Optional[MoveContext]=None
    ) -> "_shape_childclass":
        """Move a _Shape object by a given vector

        This method is called moved() to represent the fact the _Shape objects are
        immutable and a new object is created by the moved() method.
        """
        raise NotImplementedError

    def repeat(self, *,
        offset0: "Point",
        n: int, n_dxy: "Point", m: int=1, m_dxy: Optional["Point"]=None,
    ) -> "RepeatedShape":
        return RepeatedShape(
            shape=self, offset0=offset0,
            n=n, n_dxy=n_dxy, m=m, m_dxy=m_dxy,
        )

    @abc.abstractmethod
    def rotated(
        self: "_shape_childclass", *,
        rotation: Rotation, context: Optional[RotationContext]=None,
    ) -> "_shape_childclass":
        """Rotate a _Shape object by a given vector

        This method is called rotated() to represent the fact the _Shape objects are
        immutable and a new object is created by the rotated() method.
        """
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def area(self) -> float:
        raise NotImplementedError

    @abc.abstractmethod
    def __eq__(self, o: object) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def __hash__(self) -> int:
        raise NotImplementedError
ShapeT = _Shape


class _Rectangular(_Shape):
    """Mixin base class rectangular shapes

    API Notes:
        * This is private class for this module and is not exported by default.
          It should only be used as mixing inside this module.
    """
    @property
    @abc.abstractmethod
    def left(self) -> float:
        raise NotImplementedError
    @property
    @abc.abstractmethod
    def bottom(self) -> float:
        raise NotImplementedError
    @property
    @abc.abstractmethod
    def right(self) -> float:
        raise NotImplementedError
    @property
    @abc.abstractmethod
    def top(self) -> float:
        raise NotImplementedError

    # Computed properties
    @property
    def width(self) -> float:
        return self.right - self.left
    @property
    def height(self) -> float:
        return self.top - self.bottom
    @property
    def center(self) -> "Point":
        return Point(
            x=0.5*(self.left + self.right),
            y=0.5*(self.bottom + self.top),
        )
RectangularT = _Rectangular


class _PointsShape(_Shape):
    """base class for single shape that can be described
    as a list of points

    API Notes:
        * This is private class for this module and is not exported by default.
          It should only be used as mixing inside this module.
    """
    @property
    @abc.abstractmethod
    def points(self) -> Iterable["Point"]:
        raise NotImplementedError

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, _PointsShape):
            return False
        p_it1 = iter(self.points)
        p_it2 = iter(o.points)
        while True:
            try:
                p1 = next(p_it1)
            except StopIteration:
                try:
                    p2 = next(p_it2)
                except StopIteration:
                    # All points the same
                    return True
                else:
                    return False
            else:
                try:
                    p2 = next(p_it2)
                except StopIteration:
                    # Different number of points
                    return False
                if p1 != p2:
                    # Non-equal point
                    return False

    def __hash__(self) -> int:
        return hash(tuple(self.points))
PointsShapeT = _PointsShape


FloatPoint = Union[Tuple[float, float], List[float]]
class Point(_PointsShape, _Rectangular):
    """A point object

    Arguments:
        x: X-coordinate
        y: Y-coordinate

    API Notes:
        * Point objects are immutable, x and y coordinates may not be changed
          after object creation.
        * Point is a final class, no backwards compatibility is guaranteed for
          subclassing this class.
    """
    def __init__(self, *, x: float, y: float):
        self._x = x
        self._y = y

    @staticmethod
    def from_float(*, point: FloatPoint) -> "Point":
        assert len(point) == 2
        return Point(x=point[0], y=point[1])

    @staticmethod
    def from_point(
        *, point: "Point", x: Optional[float]=None, y: Optional[float]=None,
    ) -> "Point":
        if x is None:
            x = point.x
        if y is None:
            y = point.y
        return Point(x=x, y=y)

    @property
    def x(self) -> float:
        """X-coordinate"""
        return self._x
    @property
    def y(self) -> float:
        """Y-coordinate"""
        return self._y

    # _Shape base class abstract methods
    @property
    def pointsshapes(self) -> Iterable[PointsShapeT]:
        return (self,)
    @property
    def bounds(self) -> RectangularT:
        return self

    def moved(self, *, dxy: "Point", context: Optional[MoveContext]=None) -> "Point":
        x = self.x + dxy.x
        y = self.y + dxy.y

        return Point(x=x, y=y)

    def rotated(self, *, rotation: Rotation, context: Optional[RotationContext]=None) -> "Point":
        x = self.x
        y = self.y
        tx, ty = {
            Rotation.No: (x, y),
            Rotation.R90: (-y, x),
            Rotation.R180: (-x, -y),
            Rotation.R270: (y, -x),
            Rotation.MX: (x, -y),
            Rotation.MX90: (y, x),
            Rotation.MY: (-x, y),
            Rotation.MY90: (-y, -x),
        }[rotation]

        return Point(x=tx, y=ty)

    # _PointsShape base class abstract methods
    @property
    def points(self) -> Iterable["Point"]:
        return (self,)

    # _Rectangular mixin abstract methods
    @property
    def left(self) -> float:
        return self._x
    @property
    def bottom(self) -> float:
        return self._y
    @property
    def right(self) -> float:
        return self._x
    @property
    def top(self) -> float:
        return self._y

    def __neg__(self) -> "Point":
        return Point(x=-self.x, y=-self.y)

    @property
    def area(self):
        return 0.0

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, Point):
            return False
        else:
            return _eq(self.x, o.x) and _eq(self.y, o.y)

    def __hash__(self) -> int:
        return hash((self.x, self.y))

    @overload
    def __add__(self, shape: _shape_childclass) -> _shape_childclass:
        ... # pragma: no cover
    @overload
    def __add__(self, shape: "MaskShape") -> "MaskShape":
        ... # pragma: no cover
    @overload
    def __add__(self, shape: "MaskShapes") -> "MaskShapes":
        ... # pragma: no cover
    def __add__(self, shape) -> Union[_Shape, "MaskShape", "MaskShapes"]:
        """The + operation with a Point.

        The + operation on a (mask)shape will move that shape with the given
        point as vector.

        Returns
            Shape shifted by the point as vector
        """
        if isinstance(shape, (_Shape, MaskShape, MaskShapes)):
            return shape.moved(dxy=self)
        else:
            raise TypeError(
                "unsupported operand type(s) for +: "
                f"'{self.__class__.__name__}' and '{shape.__class__.__name__}'"
            )
    __radd__ = __add__

    @overload
    def __rsub__(self, shape: _shape_childclass) -> _shape_childclass:
        ... # pragma: no cover
    @overload
    def __rsub__(self, shape: "MaskShape") -> "MaskShape":
        ... # pragma: no cover
    @overload
    def __rsub__(self, shape: "MaskShapes") -> "MaskShapes":
        ... # pragma: no cover
    def __rsub__(self, shape) -> Union[_Shape, "MaskShape", "MaskShapes"]:
        """Operation shape - `Point`

        Returns
            Shape shifted by the negative of the point as vector
        """
        if isinstance(shape, (_Shape, MaskShape, MaskShapes)):
            return shape.moved(dxy=-self)
        else:
            raise TypeError(
                "unsupported operand type(s) for -: "
                f"'{shape.__class__.__name__}' and '{self.__class__.__name__}'"
            )

    # Point - Point is not handled by __rsub__
    def __sub__(self, point: "Point") -> "Point":
        if isinstance(point, Point):
            return self.moved(dxy=-point)
        else:
            raise TypeError(
                "unsupported operand type(s) for -: "
                f"'{self.__class__.__name__}' and '{point.__class__.__name__}'"
            )

    def __mul__(self, m: Union[float, Rotation]) -> "Point":
        if isinstance(m, (int, float)):
            return Point(x=m*self.x, y=m*self.y)
        elif isinstance(m, Rotation):
            return self.rotated(rotation=m)
        else:
            raise TypeError(
                f"unsupported operand type(s) for *: "
                f"'{self.__class__.__name__}' and '{m.__class__.__name__}'"
            )
    __rmul__ = __mul__

    def __str__(self) -> str:
        return f"({self.x:.6},{self.y:.6})"

    def __repr__(self) -> str:
        return f"Point(x={self.x:.6},y={self.y:.6})"


origin: Point = Point(x=0.0, y=0.0)


class Line(_PointsShape, _Rectangular):
    """A line shape

    A line consist of a start point and an end point. It is considered
    to be directional so two lines with start en and point exchanged
    are not considered equal.
    """
    def __init__(self, *, point1: Point, point2: Point):
        self._point1 = point1
        self._point2 = point2

    @property
    def point1(self) -> Point:
        return self._point1
    @property
    def point2(self) -> Point:
        return self._point2

    # _Shape base class abstraxt methods
    @property
    def pointsshapes(self) -> Iterable[PointsShapeT]:
        return (self,)
    @property
    def bounds(self) -> RectangularT:
        return self

    def moved(self, *, dxy: Point, context: Optional[MoveContext]=None) -> "Line":
        return Line(
            point1=self._point1.moved(dxy=dxy, context=context),
            point2=self._point2.moved(dxy=dxy, context=context),
        )

    def rotated(self, *, rotation: Rotation, context: Optional[RotationContext]=None) -> "Line":
        return Line(
            point1=self.point1.rotated(rotation=rotation, context=context),
            point2=self.point2.rotated(rotation=rotation, context=context),
        )

    # _PointsShape mixin abstract methods
    @property
    def points(self) -> Iterable[Point]:
        return (self._point1, self._point2)

    # _Rectangular mixin abstract methods
    @property
    def left(self) -> float:
        return min(self._point1.left, self._point2.left)
    @property
    def bottom(self) -> float:
        return min(self._point1.bottom, self._point2.bottom)
    @property
    def right(self) -> float:
        return max(self._point1.right, self._point2.right)
    @property
    def top(self) -> float:
        return max(self._point1.top, self._point2.top)

    @property
    def area(self):
        return 0.0

    def __str__(self) -> str:
        return f"{self.point1}-{self.point2}"

    def __repr__(self) -> str:
        return f"Line(point1={self.point1!r},point2={self.point2!r})"


class Polygon(_PointsShape):
    def __init__(self, *, points: Iterable["Point"]):
        self._points = points = tuple(points)
        if points[0] != points[-1]:
            raise ValueError("Last point has to be the same as the first point")

        left = min(point.x for point in points)
        bottom = min(point.y for point in points)
        right = max(point.x for point in points)
        top = max(point.y for point in points)
        if _eq(left, right) or _eq(bottom, top):
            raise ValueError("Polygon with only colinear points not allowed")
        self._bounds: Rect = Rect(left=left, bottom=bottom, right=right, top=top)

    @classmethod
    def from_floats(
        cls, *, points: Iterable[FloatPoint],
    ) -> "Polygon":
        """
        API Notes:
            * This method is only meant to be called as Outline.from_floats
              not as obj.__class__.from_floats(). This means that subclasses
              may overload this method with incompatible call signature.
        """
        return cls(points=(Point(x=x, y=y) for x, y in points))

    # _Shape base class abstraxt methods
    @property
    def pointsshapes(self) -> Iterable[PointsShapeT]:
        yield self
    @property
    def bounds(self) -> RectangularT:
        return self._bounds

    def moved(self, *, dxy: Point, context: Optional[MoveContext]=None) -> "Polygon":
        return Polygon(points=(point + dxy for point in self.points))

    def rotated(self, *,
        rotation: Rotation, context: Optional[RotationContext]=None,
    ) -> "Polygon":
        return Polygon(points=(
            point.rotated(rotation=rotation, context=context)
            for point in self.points
        ))

    # _PointsShape mixin abstract methods
    @property
    def points(self) -> Iterable[Point]:
        return self._points

    @property
    def area(self) -> float:
        raise NotImplementedError

    def __str__(self) -> str:
        s = "=".join(f"{str(p)}" for p in self.points)
        return f"{{{s}}}"

    def __repr__(self) -> str:
        s = ",".join(f"{repr(p)}" for p in self.points)
        return f"Polygon(points=({s}))"


class Rect(Polygon, _Rectangular):
    """A rectangular shape object

    Arguments:
        left, bottom, right, top:
            Edge coordinates of the rectangle; left, bottom have to be smaller
            than resp. right, top.

    API Notes:
        * Rect objects are immutable, dimensions may not be changed after creation.
        * This class is final. No backwards guarantess given for subclasses in
          user code
    """
    def __init__(self, *, left: float, bottom: float, right: float, top: float):
        assert (left < right) and (bottom < top)

        self._left = left
        self._bottom = bottom
        self._right = right
        self._top = top

    @staticmethod
    # type: ignore[override]
    def from_floats(*, values: Tuple[float, float, float, float]) -> "Rect":
        left, bottom, right, top = values
        return Rect(left=left, bottom=bottom, right=right, top=top)

    @staticmethod
    def from_rect(
        *, rect: "_Rectangular",
        left: Optional[float]=None, bottom: Optional[float]=None,
        right: Optional[float]=None, top: Optional[float]=None,
        bias: Union[float, _prp.Enclosure]=0.0,
    ) -> "Rect":
        if not isinstance(bias, _prp.Enclosure):
            bias = _prp.Enclosure(bias)
        hbias = bias.first
        vbias = bias.second
        if left is None:
            left = rect.left
        left -= hbias
        if bottom is None:
            bottom = rect.bottom
        bottom -= vbias
        if right is None:
            right = rect.right
        right += hbias
        if top is None:
            top = rect.top
        top += vbias
        return Rect(left=left, bottom=bottom, right=right, top=top)

    @staticmethod
    def from_corners(*, corner1: Point, corner2: Point) -> "Rect":
        left = min(corner1.x, corner2.x)
        bottom = min(corner1.y, corner2.y)
        right = max(corner1.x, corner2.x)
        top = max(corner1.y, corner2.y)

        return Rect(left=left, bottom=bottom, right=right, top=top)

    @staticmethod
    def from_float_corners(*, corners: Tuple[FloatPoint, FloatPoint]) -> "Rect":
        return Rect.from_corners(
            corner1=Point.from_float(point=corners[0]),
            corner2=Point.from_float(point=corners[1]),
        )

    @staticmethod
    def from_size(
        *, center: Point=Point(x=0, y=0), width: float, height: float,
    ) -> "Rect":
        assert (width > 0) and (height > 0)
        x = center.x
        y = center.y
        left = x - 0.5*width
        bottom = y - 0.5*height
        right = x + 0.5*width
        top = y + 0.5*height

        return Rect(left=left, bottom=bottom, right=right, top=top)

    @property
    def left(self) -> float:
        return self._left
    @property
    def bottom(self) -> float:
        return self._bottom
    @property
    def right(self) -> float:
        return self._right
    @property
    def top(self) -> float:
        return self._top

    @property
    def bounds(self) -> RectangularT:
        return self

    # overloaded _Shape base class abstract methods
    def moved(self, *, dxy: Point, context: Optional[MoveContext]=None) -> "Rect":
        left = self.left + dxy.x
        bottom = self.bottom + dxy.y
        right = self.right + dxy.x
        top = self.top + dxy.y

        return Rect(left=left, bottom=bottom, right=right, top=top)

    def rotated(self, *,
        rotation: Rotation, context: Optional[RotationContext]=None,
    ) -> "Rect":
        if rotation in (Rotation.No, Rotation.R180, Rotation.MX, Rotation.MY):
            width = self.width
            height = self.height
        elif rotation in (Rotation.R90, Rotation.R270, Rotation.MX90, Rotation.MY90):
            width = self.height
            height = self.width
        else:
            raise RuntimeError(
                f"Internal error: unsupported rotation '{rotation}'"
            )

        return Rect.from_size(
            center=self.center.rotated(rotation=rotation, context=context),
            width=width, height=height,
        )

    # overloaded _PointsShape mixin abstract methods
    @property
    def points(self) -> Iterable[Point]:
        return (
            Point(x=self.left, y=self.bottom),
            Point(x=self.left, y=self.top),
            Point(x=self.right, y=self.top),
            Point(x=self.right, y=self.bottom),
            Point(x=self.left, y=self.bottom),
        )

    def __str__(self) -> str:
        p1 = Point(x=self.left, y=self.bottom)
        p2 = Point(x=self.right, y=self.top)
        return f"[{str(p1)}-{str(p2)}]"

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"left={self.left:.6},bottom={self.bottom:.6},"
            f"right={self.right:.6},top={self.top:.6})"
        )

    @property
    def area(self) -> float:
        return self.width*self.height

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, Rect):
            return False
        return (
            _eq(self.left, o.left) and _eq(self.bottom,  o.bottom)
            and _eq(self.right, o.right) and _eq(self.top, o.top)
        )

    def __hash__(self) -> int:
        return hash((self.left, self.bottom, self.right, self.top))


class MultiPath(Polygon):
    """A shape consisting of one or more paths. A single path consist of
    manhattan connections of varying width between points.

    A ``MultiPath`` object is created specifying a list of instructions that
    build the ``MultiPath``. The first instruction has to be the Start
    instructions and then follow by a list of other instructions. If a ``Knot``
    instruction is included it has to be only once in the list as the last
    instruction.
    """
    class _Instruction:
        pass

    class Start(_Instruction):
        """Indicates the start of a MultiPath"""
        def __init__(self, *, point: Point, width: float):
            if width < -epsilon:
                raise ValueError(
                    f"width has to be a positive value not '{width}'"
                )
            self._point = point
            self._width = width

        def __eq__(self, obj: object) -> bool:
            return (
                False if not isinstance(obj, Start)
                else (
                    (self._point == obj._point)
                    and (abs(self._width - obj._width) < epsilon)
                )
            )

    class SetWidth(_Instruction):
        """Set the width for the next segment(s)"""
        def __init__(self, width: float):
            if width < -epsilon:
                raise ValueError(
                    f"width has to be a positive value not '{width}'"
                )
            self._width = width

        def __eq__(self, obj: object) -> bool:
            return (
                False if not isinstance(obj, SetWidth)
                else abs(self._width - obj._width) < epsilon
            )

    class _Go(_Instruction):
        """Base class for drawing a segment with a certain distance"""
        def __init__(self, dist: float):
            if dist < -epsilon:
                raise ValueError(
                    f"dist has to be a positive value not '{dist}'"
                )
            self._dist = dist

        def __eq__(self, obj: object) -> bool:
            if self.__class__ != obj.__class__:
                # _Go objects are final and have to be the same class, not just subclasses
                return False
            else:
                assert isinstance(obj, MultiPath._Go)
                return abs(self._dist - obj._dist) < epsilon

    class GoLeft(_Go):
        """Go left from the current location

        API Notes:
            This class is final, subclassing may cause backwards compatibility problems.
        """
        pass
    class GoDown(_Go):
        """Go down from the current location

        API Notes:
            This class is final, subclassing may cause backwards compatibility problems.
        """
        pass
    class GoRight(_Go):
        """Go right from the current location

        API Notes:
            This class is final, subclassing may cause backwards compatibility problems.
        """
        pass
    class GoUp(_Go):
        """Go up from the current location

        API Notes:
            This class is final, subclassing may cause backwards compatibility problems.
        """
        pass

    class Knot(_Instruction):
        """A node is a point where different subpaths start from.

        Arguments:
            left, down, right, up: instructions for each subpath starting from
                the current location.

                At least two directions need to be specified. The first instruction
                in a direction that is not ``SetWidth`` may not be another ``Knot``
                instruction.

                The direction in conflict with last ``_Go`` instruction may not be
                specified; e.g. if last instruction was ``GoUp``, down may not be
                specified.

        API Notes:
            This class is final, subclassing may cause backwards compatibility problems.
        """
        def __init__(self, *,
            left: OptMultiT["MultiPath.NoKnot"]=None,
            down: OptMultiT["MultiPath.NoKnot"]=None,
            right: OptMultiT["MultiPath.NoKnot"]=None,
            up: OptMultiT["MultiPath.NoKnot"]=None,
        ):
            n_dirs = sum(ins is not None for ins in (left, down, right, up))
            if n_dirs < 2:
                raise TypeError("At least two directions need instuctions for 'Knot'")

            self.left = cast_OptMultiT(left)
            self.down = cast_OptMultiT(down)
            self.right = cast_OptMultiT(right)
            self.up = cast_OptMultiT(up)

    # All instructions except Start; for typing only
    NoStart = Union[SetWidth, _Go, Knot]
    # All instructions except Start & Knot; for typing only
    NoKnot = Union[SetWidth, _Go]

    class _PointsBuilder:
        def __init__(self, *, first: "MultiPath.Start"):
            self.location = first._point
            self.width = first._width
            self.prevwidth = first._width
            self.previnstr: MultiPath._Instruction = first
            self.prevdirtype: type = type(first)

            self.clkwcoords: List[Point] = []
            self.cclkwcoords: List[Point] = []

        def do_go(self, instr: "MultiPath._Go"):
            clkwcoords = self.clkwcoords
            cclkwcoords = self.cclkwcoords

            width = self.width
            prevwidth = self.prevwidth
            location = self.location
            prevdirtype = self.prevdirtype

            instrtype = type(instr)

            if prevdirtype == MultiPath.Start:
                if instrtype == MultiPath.GoLeft:
                    dxy = Point(x=0.0, y=0.5*width)
                    clkwcoords.append(location - dxy)
                    cclkwcoords.append(location - dxy)
                    cclkwcoords.append(location + dxy)
                elif instrtype == MultiPath.GoDown:
                    dxy = Point(x=0.5*width, y=0.0)
                    clkwcoords.append(location + dxy)
                    cclkwcoords.append(location + dxy)
                    cclkwcoords.append(location - dxy)
                elif instrtype == MultiPath.GoRight:
                    dxy = Point(x=0.0, y=0.5*width)
                    clkwcoords.append(location + dxy)
                    cclkwcoords.append(location + dxy)
                    cclkwcoords.append(location - dxy)
                elif instrtype == MultiPath.GoUp:
                    dxy = Point(x=0.5*width, y=0.0)
                    clkwcoords.append(location - dxy)
                    cclkwcoords.append(location - dxy)
                    cclkwcoords.append(location + dxy)
                else: # pragma: no cover
                    raise RuntimeError(
                        f"Internal error: unknown instruction type '{instrtype}'"
                    )
            elif prevdirtype == MultiPath.GoLeft:
                if instrtype == MultiPath.GoLeft:
                    dxy1 = Point(x=0.0, y=0.5*self.prevwidth)
                    dxy2 = Point(x=0.0, y=0.5*width)
                    clkwcoords.extend((location - dxy1, location - dxy2))
                    cclkwcoords.extend((location + dxy1, location + dxy2))
                elif instrtype == MultiPath.GoDown:
                    dxy = Point(x=0.5*width, y=-0.5*prevwidth)
                    clkwcoords.append(location + dxy)
                    cclkwcoords.append(location - dxy)
                elif instrtype == MultiPath.GoRight:
                    raise ValueError(
                        "GoRight instruction after GoLeft not allowed"
                    )
                elif instrtype == MultiPath.GoUp:
                    dxy = Point(x=-0.5*width, y=-0.5*prevwidth)
                    clkwcoords.append(location + dxy)
                    cclkwcoords.append(location - dxy)
                else: # pragma: no cover
                    raise RuntimeError(
                        f"Internal error: unknown instruction type '{instrtype}'"
                    )
            elif prevdirtype == MultiPath.GoDown:
                if instrtype == MultiPath.GoLeft:
                    dxy = Point(x=0.5*prevwidth, y=-0.5*width)
                    clkwcoords.append(location + dxy)
                    cclkwcoords.append(location - dxy)
                elif instrtype == MultiPath.GoDown:
                    dxy1 = Point(x=0.5*prevwidth, y=0.0)
                    dxy2 = Point(x=0.5*width, y=0.0)
                    clkwcoords.extend((location + dxy1, location + dxy2))
                    cclkwcoords.extend((location - dxy1, location - dxy2))
                elif instrtype == MultiPath.GoRight:
                    dxy = Point(x=0.5*prevwidth, y=0.5*width)
                    clkwcoords.append(location + dxy)
                    cclkwcoords.append(location - dxy)
                elif instrtype == MultiPath.GoUp:
                    raise ValueError(
                        "GoUp instruction after GoDown not allowed"
                    )
                else: # pragma: no cover
                    raise RuntimeError(
                        f"Internal error: unknown instruction type '{instrtype}'"
                    )
            elif prevdirtype == MultiPath.GoRight:
                if instrtype == MultiPath.GoLeft:
                    raise ValueError(
                        "GoLeft instruction after GoRight not allowed"
                    )
                elif instrtype == MultiPath.GoDown:
                    dxy = Point(x=0.5*width, y=0.5*prevwidth)
                    clkwcoords.append(location + dxy)
                    cclkwcoords.append(location - dxy)
                elif instrtype == MultiPath.GoRight:
                    dxy1 = Point(x=0.0, y=0.5*prevwidth)
                    dxy2 = Point(x=0.0, y=0.5*width)
                    clkwcoords.extend((location + dxy1, location + dxy2))
                    cclkwcoords.extend((location - dxy1, location - dxy2))
                elif instrtype == MultiPath.GoUp:
                    dxy = Point(x=-0.5*width, y=0.5*prevwidth)
                    clkwcoords.append(location + dxy)
                    cclkwcoords.append(location - dxy)
                else: # pragma: no cover
                    raise RuntimeError(
                        f"Internal error: unknown instruction type '{instrtype}'"
                    )
            elif prevdirtype == MultiPath.GoUp:
                if instrtype == MultiPath.GoLeft:
                    dxy = Point(x=-0.5*prevwidth, y=-0.5*width)
                    clkwcoords.append(location + dxy)
                    cclkwcoords.append(location - dxy)
                elif instrtype == MultiPath.GoDown:
                    raise ValueError(
                        "GoDown instruction after GoUp not allowed"
                    )
                elif instrtype == MultiPath.GoRight:
                    dxy = Point(x=-0.5*prevwidth, y=0.5*width)
                    clkwcoords.append(location + dxy)
                    cclkwcoords.append(location - dxy)
                elif instrtype == MultiPath.GoUp:
                    dxy1 = Point(x=0.5*prevwidth, y=0.0)
                    dxy2 = Point(x=0.5*width, y=0.0)
                    clkwcoords.extend((location - dxy1, location - dxy2))
                    cclkwcoords.extend((location + dxy1, location + dxy2))
                else: # pragma: no cover
                    raise RuntimeError(
                        f"Internal error: unknown instruction type '{instrtype}'"
                    )
            else: # pragma: no cover
                raise RuntimeError(
                    f"Internal error: unknown instruction type '{instrtype}'"
                )

            # Update location
            if instrtype == MultiPath.GoLeft:
                self.location += Point(x=-cast(MultiPath.GoLeft, instr)._dist, y=0.0)
            elif instrtype == MultiPath.GoDown:
                self.location += Point(x=0.0, y=-cast(MultiPath.GoDown, instr)._dist)
            elif instrtype == MultiPath.GoRight:
                self.location += Point(x=cast(MultiPath.GoRight, instr)._dist, y=0.0)
            elif instrtype == MultiPath.GoUp:
                self.location += Point(x=0.0, y=cast(MultiPath.GoDown, instr)._dist)
            else: # pragma: no cover
                raise RuntimeError(
                    f"Internal error: unknown `_Go` instruction type '{instrtype}'"
                )

        def _knot_builder(self, *,
            instrs: Optional[Tuple["MultiPath.NoStart", ...]]
        ) -> Optional["MultiPath._PointsBuilder"]:
            if instrs is None:
                return None
            else:
                first = instrs[0]
                if isinstance(first, MultiPath.SetWidth):
                    start = MultiPath.Start(point=self.location, width=first._width)
                    instrs = instrs[1:]
                else:
                    start = MultiPath.Start(point=self.location, width=self.width)
                builder = MultiPath._PointsBuilder(first=start)
                for instr2 in instrs:
                    builder.do_instr(instr2)
                builder.finalize()

                return builder

        def do_knot(self, instr: "MultiPath.Knot"):
            prevdirtype = self.prevdirtype

            left_builder = self._knot_builder(instrs=instr.left)
            up_builder = self._knot_builder(instrs=instr.up)
            right_builder = self._knot_builder(instrs=instr.right)
            down_builder = self._knot_builder(instrs=instr.down)

            def conn_ends(*, end: Point, start: Point):
                end_sw = (end.x < self.location.x) and (end.y < self.location.y)
                end_se = (end.x > self.location.x) and (end.y < self.location.y)
                end_nw = (end.x < self.location.x) and (end.y > self.location.y)
                end_ne = (end.x > self.location.x) and (end.y > self.location.y)

                start_sw = (start.x < self.location.x) and (start.y < self.location.y)
                start_se = (start.x > self.location.x) and (start.y < self.location.y)
                start_nw = (start.x < self.location.x) and (start.y > self.location.y)
                start_ne = (start.x > self.location.x) and (start.y > self.location.y)

                if (end_sw or end_ne) and (start_sw or start_ne):
                    self.clkwcoords.append(Point(x=end.x, y=start.y))
                elif (end_se or end_nw) and (start_se or start_nw):
                    self.clkwcoords.append(Point(x=start.x, y=end.y))
                elif (end_sw and start_nw) or (end_ne and start_se):
                    if abs(end.x - start.x) > epsilon:
                        self.clkwcoords.extend((
                            Point(x=end.x, y=self.location.y),
                            Point(x=start.x, y=self.location.y)
                        ))
                elif (end_nw and start_ne) or (end_se and start_sw):
                        if abs(end.y - start.y) > epsilon:
                            self.clkwcoords.extend((
                                Point(x=self.location.x, y=end.y),
                                Point(x=self.location.x, y=start.y),
                            ))
                else: # pragma: no cover
                    raise RuntimeError("Internal error")

            if prevdirtype == MultiPath.GoUp:
                assert down_builder is None
                builders = (left_builder, up_builder, right_builder)
            elif prevdirtype == MultiPath.GoLeft:
                assert right_builder is None
                builders = (down_builder, left_builder, up_builder)
            elif prevdirtype == MultiPath.GoDown:
                assert up_builder is None
                builders = (right_builder, down_builder, left_builder)
            elif prevdirtype == MultiPath.GoRight:
                assert left_builder is None
                builders = (up_builder, right_builder, down_builder)
            else: # pragma: no cover
                raise RuntimeError("Internal error")

            for builder in builders:
                if builder is not None:
                    conn_ends(end=self.clkwcoords[-1], start=builder.clkwcoords[1])
                    self.clkwcoords.extend((
                        *builder.clkwcoords[1:],
                        *reversed(builder.cclkwcoords[2:]),
                    ))
            conn_ends(end=self.clkwcoords[-1], start=self.cclkwcoords[-1])

        def do_instr(self, instr: "MultiPath.NoStart"):
            prevtype: type = type(self.previnstr)
            if issubclass(prevtype, (MultiPath._Go, MultiPath.Knot)):
                self.prevdirtype = prevtype
            instrtype: type = type(instr)

            prevdirtype = self.prevdirtype

            if instrtype == prevtype:
                raise ValueError(
                    "Two instructions of same type after each other is not allowed "
                )
            elif instrtype == MultiPath.Start:
                raise ValueError("No 'Start' instruction allowed after the first one")

            if (
                (instrtype == MultiPath.SetWidth)
                and (self.prevdirtype == MultiPath.Start)
            ):
                raise ValueError(
                    "First instruction after 'Start' may not be 'SetWidth'",
                )

            if prevdirtype == MultiPath.Knot:
                raise ValueError(
                    "No instuction allowed after 'Knot' instruction",
                )

            # First instruction after Start needs to be handled differently
            if isinstance(instr, MultiPath._Go):
                self.do_go(instr)
            elif isinstance(instr, MultiPath.Knot):
                self.do_knot(instr)
            elif not isinstance(instr, MultiPath.SetWidth): # pragma: no cover
                raise NotImplementedError(f"instuction type '{instrtype}'")

            # Update width
            newwidth = instr._width if isinstance(instr, MultiPath.SetWidth) else self.width
            self.prevwidth = self.width
            self.width = newwidth

            self.previnstr = instr

        def finalize(self):
            location = self.location
            width = self.width
            clkwcoords = self.clkwcoords
            cclkwcoords = self.cclkwcoords

            # Complete the last instruction
            prevtype = type(self.previnstr)
            if prevtype == MultiPath.SetWidth:
                raise ValueError(
                    f"SetWidth may not be the last instruction"
                )
            elif prevtype == MultiPath.GoLeft:
                dxy = Point(x=0.0, y=0.5*width)
                clkwcoords.append(location - dxy)
                cclkwcoords.append(location + dxy)
            elif prevtype == MultiPath.GoDown:
                dxy = Point(x=0.5*width, y=0.0)
                clkwcoords.append(location + dxy)
                cclkwcoords.append(location - dxy)
            elif prevtype == MultiPath.GoRight:
                dxy = Point(x=0.0, y=0.5*width)
                clkwcoords.append(location + dxy)
                cclkwcoords.append(location - dxy)
            elif prevtype == MultiPath.GoUp:
                dxy = Point(x=0.5*width, y=0.0)
                clkwcoords.append(location - dxy)
                cclkwcoords.append(location + dxy)
            elif prevtype == MultiPath.Knot:
                pass
            else: # pragma: no cover
                raise RuntimeError(
                    f"Internal error: unknown instruction type '{prevtype}'",
                )

            assert len(clkwcoords) > 0
            assert len(cclkwcoords) > 0

    def __init__(self, first: Start, *instrs: "MultiPath.NoStart"):
        if len(instrs) == 0:
            raise ValueError("At least one instruction needed after 'Start'")
        self._first: MultiPath.Start = first
        self._instrs = instrs

        # Build the coordinates
        builder = MultiPath._PointsBuilder(first=first)

        for instr in instrs:
            builder.do_instr(instr)

        builder.finalize()

        super().__init__(points=(
            *builder.clkwcoords, *reversed(builder.cclkwcoords),
        ))

    @property
    def first(self) -> Start:
        return self._first
    @property
    def instrs(self) -> Tuple[_Instruction, ...]:
        return self._instrs
# Instruction aliases
Start = MultiPath.Start
SetWidth = MultiPath.SetWidth
GoLeft = MultiPath.GoLeft
GoDown = MultiPath.GoDown
GoRight = MultiPath.GoRight
GoUp = MultiPath.GoUp
Knot = MultiPath.Knot
NoStart = MultiPath.NoStart # For typing only


class Ring(MultiPath):
    """A shape representating a ring shape polygon

    Arguments:
        outer_bound: the outer edge of the shape
        ring_width: the width of the ring, it has to be smaller than
            half the width or height of the outer edge.
    """
    def __init__(self, *, outer_bound: Rect, ring_width: float):
        if (ring_width + epsilon) > outer_bound.width/2.0:
            raise ValueError(
                f"ring_width '{ring_width}' is bigger than half outer bound width"
                f" '{outer_bound.width}'",
            )
        if (ring_width + epsilon) > outer_bound.height/2.0:
            raise ValueError(
                f"ring_width '{ring_width}' is bigger than half outer bound height"
                f" '{outer_bound.height}'",
            )

        oleft = outer_bound.left
        obottom = outer_bound.bottom
        oright = outer_bound.right
        otop = outer_bound.top

        oheight = otop - obottom
        owidth = oright - oleft
        mleft = oleft + 0.5*ring_width

        instrs = (
            Start(point=Point(x=mleft, y=obottom), width=ring_width),
            GoUp(oheight - 0.5*ring_width),
            GoRight(owidth - ring_width),
            GoDown(oheight - ring_width),
            GoLeft(owidth - 1.5*ring_width),
        )
        super().__init__(*instrs)

        self.outer_bound = outer_bound
        self.ring_width = ring_width


class RectRing(_Shape):
    """A `RectRing` object is a shape that consists of a ring of `Rect` objects.

    An exception will be raised when there is not enough room to put the four corner
    rects.
    If the 'Rect' objects needs to be on a grid all dimensions specified for this
    object - including outer bound placement, width & height - have to be double that
    grid number.

    Arguments:
        outer_bound: the outer bound of the ring; e.g. the generated rect shapes
            will be inside and touching the bound.
        rect_width: the width of the generated rect objects.
        rect_height: the height of the generated rect objects; by default it will
            be the same as rect_width.
        min_rect_space: the minimum space between two rect structures.
    """
    # TODO: Describe rules to get shapes on grid
    def __init__(self, *,
        outer_bound: Rect,
        rect_width: float, rect_height: Optional[float]=None,
        min_rect_space: float,
    ):
        if rect_height is None:
            rect_height = rect_width
        if (outer_bound.width + epsilon) < (2*rect_width + min_rect_space):
            raise ValueError(
                "outer_bound width not big enough to fit two rects in"
            )
        if (outer_bound.height + epsilon) < (2*rect_height + min_rect_space):
            raise ValueError(
                "outer_bound height not big enough to fit two rects in"
            )

        self._outer_bound = outer_bound
        self._rect_width = float(rect_width)
        self._rect_height = float(rect_height)
        self._min_rect_space = float(min_rect_space)

        pitch_x = rect_width + min_rect_space
        # Rects in horizontal direction besides corners
        self._n_x = floor(
            (
                self.outer_bound.width
                - (2*self.rect_width + self._min_rect_space)
                + epsilon
            )/pitch_x
        )
        assert self._n_x >= 0, "Internal error"

        pitch_y = rect_height + min_rect_space
        # Rects in vertical direction besides corners
        self._n_y = floor(
            (
                self.outer_bound.height
                - (2*self.rect_height + self._min_rect_space)
                + epsilon
            )/pitch_y
        )
        assert self._n_y >= 0, "Internal error"

    @property
    def outer_bound(self) -> Rect:
        return self._outer_bound
    @property
    def rect_width(self) -> float:
        return self._rect_width
    @property
    def rect_height(self) -> float:
        return self._rect_height
    @property
    def min_rect_space(self) -> float:
        return self._min_rect_space

    def moved(self, *,
        dxy: "Point", context: Optional[MoveContext]=None,
    ) -> "RectRing":
        return RectRing(
            outer_bound=self.outer_bound.moved(dxy=dxy, context=context),
            rect_width=self.rect_width, rect_height=self.rect_height,
            min_rect_space=self.min_rect_space,
        )

    def rotated(self, *,
        rotation: Rotation, context: Optional[RotationContext]=None,
    ) -> "RectRing":
        return RectRing(
            outer_bound=self.outer_bound.rotated(rotation=rotation, context=context),
            rect_width=self.rect_width, rect_height=self.rect_height,
            min_rect_space=self.min_rect_space,
        )

    @property
    def pointsshapes(self) -> Iterable["PointsShapeT"]:
        rect = Rect.from_size(width=self.rect_width, height=self.rect_height)
        left = self.outer_bound.left
        bottom = self.outer_bound.bottom
        right = self.outer_bound.right
        top = self.outer_bound.top

        left_x = left + 0.5*self.rect_width
        right_x = right - 0.5*self.rect_width
        mid_x = self.outer_bound.center.x
        bottom_y = bottom + 0.5*self.rect_height
        top_y = top - 0.5*self.rect_height
        mid_y = self.outer_bound.center.y

        pitch_x = self.rect_width + self.min_rect_space
        pitch_y = self.rect_height + self.min_rect_space

        # corners
        yield rect + Point(x=left_x, y=bottom_y)
        yield rect + Point(x=left_x, y=top_y)
        yield rect + Point(x=right_x, y=bottom_y)
        yield rect + Point(x=right_x, y=top_y)

        # bottom and top
        left_x2 = mid_x - 0.5*(self._n_x - 1)*pitch_x
        for n in range(self._n_x):
            x = left_x2 + n*pitch_x
            yield rect + Point(x=x, y=bottom_y)
            yield rect + Point(x=x, y=top_y)

        # left and right
        bottom_y2 = mid_y - 0.5*(self._n_y - 1)*pitch_y
        for n in range(self._n_y):
            y = bottom_y2 + n*pitch_y
            yield rect + Point(x=left_x, y=y)
            yield rect + Point(x=right_x, y=y)

    @property
    def bounds(self) -> RectangularT:
        return self.outer_bound

    @property
    def area(self) -> float:
        return (4 + 2*self._n_x + 2*self._n_y)*self.rect_width*self.rect_height

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, RectRing):
            return False
        else:
            return all((
                self.outer_bound == o.outer_bound,
                abs(self.rect_width - o.rect_width) <= epsilon,
                abs(self.rect_height - o.rect_height) <= epsilon,
                abs(self.min_rect_space - o.min_rect_space) <= epsilon,
            ))

    def __hash__(self) -> int:
        return hash(
            (self.outer_bound, self.rect_width, self.rect_height, self.min_rect_space),
        )

    def __repr__(self) -> str:
        s_args = ",".join((
            f"outer_bound={self.outer_bound!r}",
            f"rect_width={self.rect_width!r}",
            f"rect_height={self.rect_height!r}",
            f"min_rect_space={self.min_rect_space!r}",
        ))
        return f"RingRect({s_args})"


class Label(_Shape):
    """This shape represent a text label.

    Arguments:
        origin: location of the label.
            Currently no support for any other property than the origin
            (like rotation, font, etc.) is supported.
        text: the text of the label
    """
    def __init__(self, origin: Point, text: str):
        super().__init__()
        self._origin = origin
        self._text = text

    @property
    def origin(self) -> Point:
        return self._origin
    @property
    def text(self) -> str:
        return self._text

    @property
    def pointsshapes(self) -> Iterable[PointsShapeT]:
        return self.origin.pointsshapes
    @property
    def bounds(self) -> RectangularT:
        return self.origin.bounds
    @property
    def area(self) -> float:
        return self.origin.area

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, Label):
            return False
        else:
            return (self.origin == o.origin) and (self.text == o.text)

    def __hash__(self) -> int:
        return hash((self.origin, self.text))

    def moved(self, *, dxy: Point, context: Optional[MoveContext] = None) -> "Label":
        return self.__class__(origin=origin.moved(dxy=dxy, context=context), text=self.text)

    def rotated(self, *, rotation: Rotation, context: Optional[RotationContext]=None) -> "Label":
        return self


class MultiPartShape(Polygon):
    """This shape represents a single polygon shape that consist of
    a build up of touching parts.

    Main use case is to represent a shape where parts are on a different
    net as is typically the case for a WaferWire.

    Arguments:
        fullshape: The full shape
        parts: The subshapes
            The subshapes should be touching shapes and joined should form the
            fullshape shape. Currently it is only checked if the areas match,
            in better checking may be implemented.

            The subshapes will be converted to MultiPartShape._Part objects before
            becoming member of the parts property
    """
    # TODO: merging of shapes is not complete. standard cell library still seems to
    # generate geometries that are no properly merged.
    class _Part(Polygon):
        """A shape representing one part of a MultiPartShape

        This object keeps reference to the MultiPartShape so the parts can be added
        to nets in layout and the shapes still being able to know to which
        MultiPartShape object they belong.
        """
        def __init__(self, *, partshape: Polygon, multipartshape: "MultiPartShape"):
            self._partshape = partshape
            self._multipartshape = multipartshape

        @property
        def partshape(self) -> Polygon:
            return self._partshape
        @property
        def multipartshape(self) -> "MultiPartShape":
            return self._multipartshape

        @property
        def pointsshapes(self) -> Iterable[PointsShapeT]:
            yield self
        @property
        def bounds(self) -> RectangularT:
            return self.partshape.bounds

        def moved(self, *,
            dxy: Point, context: Optional[MoveContext]=None,
        ) -> "MultiPartShape._Part":
            if context is None:
                idx = self.multipartshape.parts.index(self)
                return self.multipartshape.moved(dxy=dxy).parts[idx]
            else:
                return context._move_part(part=self, dxy=dxy)

        def rotated(self, *,
            rotation: Rotation, context: Optional[RotationContext]=None,
        ) -> "MultiPartShape._Part":
            if context is None:
                idx = self.multipartshape.parts.index(self)
                return self.multipartshape.rotated(rotation=rotation).parts[idx]
            else:
                return context._rotate_part(part=self, rotation=rotation)

        # _PointsShape mixin abstract methods
        @property
        def points(self) -> Iterable[Point]:
            return self.partshape.points

        @property
        def area(self) -> float:
            return self.partshape.area

        def __str__(self) -> str:
            return f"<<{str(self.partshape)}>>"

        def __repr__(self) -> str:
            ps = self.partshape
            return f"MultiPartShape._Part(partshape={ps!r})"

        def __hash__(self) -> int:
            return hash((self.partshape, self.multipartshape))

        def __eq__(self, other: Any) -> bool:
            if not isinstance(other, MultiPartShape._Part):
                return False
            else:
                return (
                    (self.partshape == other.partshape)
                    and (self.multipartshape == other.multipartshape)
                )

    def __init__(self, fullshape: Polygon, parts: Iterable[Polygon]):
        # TODO: check if shape is actually build up of the parts
        self._fullshape = fullshape
        self._parts = tuple(
            MultiPartShape._Part(partshape=part, multipartshape=self)
            for part in parts
        )

    @property
    def fullshape(self) -> Polygon:
        return self._fullshape
    @property
    def parts(self) -> Tuple["MultiPartShape._Part", ...]:
        return self._parts

    @property
    def pointsshapes(self) -> Iterable[PointsShapeT]:
        return self.fullshape.pointsshapes
    @property
    def bounds(self) -> RectangularT:
        return self.fullshape.bounds

    def moved(self, *, dxy: Point, context: Optional[MoveContext]=None) -> "MultiPartShape":
        return MultiPartShape(
            fullshape=self.fullshape.moved(dxy=dxy),
            parts=(part.partshape.moved(dxy=dxy) for part in self.parts)
        )

    def rotated(self, *,
        rotation: Rotation, context: Optional[RotationContext]=None,
    ) -> "MultiPartShape":
        return MultiPartShape(
            fullshape=self.fullshape.rotated(rotation=rotation, context=context),
            parts=(
                part.partshape.rotated(rotation=rotation, context=context)
                for part in self.parts
            )
        )

    # _PointsShape mixin abstract methods
    @property
    def points(self) -> Iterable[Point]:
        return self.fullshape.points

    @property
    def area(self) -> float:
        return self.fullshape.area

    def __hash__(self) -> int:
        return hash(self.fullshape)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, MultiPartShape):
            return False
        else:
            return (
                {part.partshape for part in self.parts}
                == {part.partshape for part in other.parts}
            )

    def __str__(self) -> str:
        s = "|".join(str(p.partshape) for p in self._parts)
        return f"({s})"

    def __repr__(self) -> str:
        s1 = repr(self.fullshape)
        s2 = ",".join(repr(p.partshape) for p in self._parts)
        return f"MultiPartShape(fullshape={s1},parts=({s2}))"


class MultiShape(_Shape, Collection[_Shape]):
    """A shape representing a group of shapes

    Arguments:
        shapes: the sub shapes.
            Subshapes may or may not overlap. The object will fail to create if only one unique
            shape is provided including if the same shape is provided multiple times without
            another shape.

            MultiShape objects part of the provided shapes will be flattened and it's children will
            be joined with the other shapes.
    """
    def __init__(self, *, shapes: Iterable[_Shape]):
        def iterate_shapes(ss: Iterable[_Shape]) -> Iterable[_Shape]:
            for shape in ss:
                if isinstance(shape, MultiShape):
                    yield from iterate_shapes(shape.shapes)
                else:
                    yield shape
        self._shapes = shapes = frozenset(iterate_shapes(shapes))
        if len(shapes) < 2:
            raise ValueError("MultiShape has to consist of more than one shape")

    @property
    def shapes(self) -> Iterable[ShapeT]:
        return self._shapes

    # _Shape base class abstract methods
    @property
    def pointsshapes(self) -> Iterable[PointsShapeT]:
        for shape in self._shapes:
            yield from shape.pointsshapes
    @property
    def bounds(self) -> RectangularT:
        boundss = tuple(shape.bounds for shape in self.shapes)
        left = min(bounds.left for bounds in boundss)
        bottom = min(bounds.bottom for bounds in boundss)
        right = max(bounds.right for bounds in boundss)
        top = max(bounds.top for bounds in boundss)

        # It should be impossible to create a MultiShape where bounds
        # corresponds with a point.
        assert (left != right) or (bottom != top), "Internal error"
        if (left == right) or (bottom == top):
            return Line(
                point1=Point(x=left, y=bottom),
                point2=Point(x=right, y=top),
            )
        else:
            return Rect(left=left, bottom=bottom, right=right, top=top)

    def moved(self, *, dxy: Point, context: Optional[MoveContext]=None) -> "MultiShape":
        # Avoid generating different MultiPartShape for parts from the same MultiPartShape
        if context is None:
            context=MoveContext()

        return MultiShape(
            shapes=(
                polygon.moved(dxy=dxy, context=context)
                for polygon in self.pointsshapes
            ),
        )

    def rotated(self, *,
        rotation: Rotation, context: Optional[RotationContext]=None,
    ) -> "MultiShape":
        return MultiShape(
            shapes=(
                polygon.rotated(rotation=rotation, context=context)
                for polygon in self.pointsshapes
            )
        )

    # Collection mixin abstract methods
    def __iter__(self) -> Iterator[_Shape]:
        return iter(self.shapes)

    def __len__(self) -> int:
        return len(self._shapes)

    def __contains__(self, shape: object) -> bool:
        return shape in self._shapes

    @property
    def area(self) -> float:
        # TODO: guarantee non overlapping shapes
        return sum(shape.area for shape in self._shapes)

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, MultiShape):
            return False
        else:
            return self._shapes == o._shapes

    def __hash__(self) -> int:
        return hash(self.shapes)

    def __str__(self) -> str:
        # substrings are sorted to get reproducable order independent str representation
        return "(" + ",".join(sorted(str(shape) for shape in self.shapes)) + ")"

    def __repr__(self) -> str:
        # substrings are sorted to get reproducable order independent str representation
        return (
            "MultiShape(shapes=("
            + ",".join(sorted(repr(shape) for shape in self.shapes))
            + "))"
        )


class RepeatedShape(_Shape):
    """A repetition of a shape allowing easy generation of array of objects.
    Implementation is generic so that one can represent any repetition with
    one or two vector that don't need to be manhattan.

    API Notes:
        * The current implementation assumes repeated shapes don't overlap. If they
          do area property will give wrong value.
    """
    # TODO: decide if repeated shapes may overlap, if not can we check it ?
    def __init__(self, *,
        shape: ShapeT, offset0: Point,
        n: int, n_dxy: Point, m: int=1, m_dxy: Optional[Point]=None,
    ):
        if n < 2:
            raise ValueError(f"n has to be equal to or higher than 2, not '{n}'")
        if m < 1:
            raise ValueError(f"m has to be equal to or higher than 1, not '{m}'")
        if (m > 1) and (m_dxy is None):
            raise ValueError("m_dxy may not be None if m > 1")
        self._shape = shape
        self._offset0 = offset0
        self._n = n
        self._n_dxy = n_dxy
        self._m = m
        self._m_dxy = m_dxy

        self._hash = None

    @property
    def shape(self) -> ShapeT:
        return self._shape
    @property
    def offset0(self) -> Point:
        return self._offset0
    @property
    def n(self) -> int:
        return self._n
    @property
    def n_dxy(self) -> Point:
        return self._n_dxy
    @property
    def m(self) -> int:
        return self._m
    @property
    def m_dxy(self) -> Optional[Point]:
        return self._m_dxy

    def moved(
        self: "RepeatedShape", *, dxy: "Point", context: Optional[MoveContext]=None,
    ) -> "RepeatedShape":
        return RepeatedShape(
            shape=self.shape, offset0=(self.offset0 + dxy),
            n=self.n, n_dxy=self.n_dxy, m=self.m, m_dxy=self.m_dxy,
        )

    @property
    def pointsshapes(self) -> Iterable[PointsShapeT]:
        if self.m <= 1:
            for i_n in range(self.n):
                dxy = self.offset0 + i_n*self.n_dxy
                yield from (polygon + dxy for polygon in self.shape.pointsshapes)
        else:
            assert self.m_dxy is not None
            for i_n, i_m in product(range(self.n), range(self.m)):
                dxy = self.offset0 + i_n*self.n_dxy + i_m*self.m_dxy
                yield from (polygon + dxy for polygon in self.shape.pointsshapes)

    @property
    def bounds(self) -> RectangularT:
        b0 = self.shape.bounds
        b1 = b0 + self.offset0
        if self.m <= 1:
            b2 = b0 + (self.offset0 + (self.n - 1)*self.n_dxy)
        else:
            assert self.m_dxy is not None
            b2 = b0 + (
                self.offset0 + (self.n - 1)*self.n_dxy + (self.m - 1)*self.m_dxy
            )
        return Rect(
            left=min(b1.left, b2.left), right=max(b1.right, b2.right),
            bottom=min(b1.bottom, b2.bottom), top=max(b1.top, b2.top),
        )

    def rotated(self, *,
        rotation: Rotation, context: Optional[RotationContext]=None,
    ) -> "RepeatedShape":
        return RepeatedShape(
            shape=self.shape.rotated(rotation=rotation, context=context),
            offset0=self.offset0.rotated(rotation=rotation, context=context),
            n=self.n, n_dxy=self.n_dxy.rotated(rotation=rotation, context=context),
            m=self.m, m_dxy=(
                None if self.m_dxy is None
                else self.m_dxy.rotated(rotation=rotation, context=context)
            )
        )

    @property
    def area(self) -> float:
        # TODO: Support case with overlapping shapes ?
        return self.n*self.m*self.shape.area

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, RepeatedShape):
            return False
        elif (self.shape != o.shape) or (self.offset0 != o.offset0):
            return False
        elif self.m == 1:
            return (
                (self.n == o.n) and (self.n_dxy == o.n_dxy)
                and (o.m == 1)
            )
        elif self.n == self.m:
            return (
                (self.n == o.n == o.m)
                # dxy value may be exchanged => compare sets
                and ({self.n_dxy, self.m_dxy} == {o.n_dxy, o.m_dxy})
            )
        else: # (self.n != self.m) and (self.m > 1)
            return (
                (
                    (self.n == o.n) and (self.n_dxy == o.n_dxy)
                    and (self.m == o.m) and (self.m_dxy == o.m_dxy)
                )
                or
                (
                    (self.n == o.m) and (self.n_dxy == o.m_dxy)
                    and (self.m == o.n) and (self.m_dxy == o.n_dxy)
                )
            )

    def __hash__(self) -> int:
        if self._hash is None:
            if self.m == 1:
                self._hash = hash(frozenset((
                    self.shape, self.offset0, self.n, self.n_dxy,
                )))
            else:
                self._hash = hash(frozenset((
                    self.shape, self.offset0, self.n, self.n_dxy, self.m, self.m_dxy,
                )))
        return self._hash

    def __repr__(self) -> str:
        s_args = ",".join((
            f"shape={self.shape!r}",
            f"offset0={self.offset0!r}",
            f"n={self.n}", f"n_dxy={self.n_dxy!r}",
            f"m={self.m}", f"m_dxy={self.m_dxy!r}",
        ))
        return f"RepeatedShape({s_args})"


class ArrayShape(RepeatedShape):
    """Object representing a manhattan repeared shape.

    This is a RepeatedShape subclass with repeat vectors either a horizontal and/or a
    vertical one.

    Arguments:
        shape: The object to repeat
        offset0: The placement of the first shape
        rows, columns: The number of rows and columns
            Both have to be equal or higher than 1 and either rows or columns has to
            be higher than 1.
        pitch_y, pitch_x: The displacement for resp. the rows and the columns.
    """
    def __init__(self, *,
        shape: _Shape, offset0: Point,
        rows: int, columns: int,
        pitch_y: Optional[float]=None, pitch_x: Optional[float]=None,
    ):
        if (rows <= 0) or (columns <= 0):
            raise ValueError(
                f"rows ({rows}) and columns ({columns}) need to be integers greater than zero"
            )
        if (rows == 1) and (columns == 1):
            raise ValueError(
                "either rows or columns or both have to be greater than 1"
            )
        if (rows > 1) and (pitch_y is None):
            raise ValueError(
                "pitch_y not given for rows > 1"
            )
        if (columns > 1) and (pitch_x is None):
            raise ValueError(
                "pitch_x not given for columns > 1"
            )
        self._rows = rows
        self._columns = columns
        self._pitch_x = pitch_x
        self._pitch_y = pitch_y

        if rows == 1:
            n = columns
            n_dxy = Point(x=cast(float, pitch_x), y=0.0)
            m = 1
            m_dxy = None
        else:
            n = rows
            n_dxy = Point(x=0.0, y=cast(float, pitch_y))
            m = columns
            m_dxy = None if pitch_x is None else Point(x=pitch_x, y=0.0)
        super().__init__(
            shape=shape, offset0=offset0, n=n, n_dxy=n_dxy, m=m, m_dxy=m_dxy,
        )

    @property
    def rows(self) -> int:
        return self._rows
    @property
    def columns(self) -> int:
        return self._columns
    @property
    def pitch_x(self) -> Optional[float]:
        return self._pitch_x
    @property
    def pitch_y(self) -> Optional[float]:
        return self._pitch_y


class MaskShape:
    def __init__(self, *, mask: _msk.DesignMask, shape: ShapeT):
        self._mask = mask
        self._shape = shape
        # TODO: Check grid

    @property
    def mask(self) -> _msk.DesignMask:
        return self._mask
    @property
    def shape(self) -> ShapeT:
        return self._shape

    def moved(self, *, dxy: Point, context: Optional[MoveContext]=None) -> "MaskShape":
        return MaskShape(mask=self.mask, shape=self.shape.moved(dxy=dxy, context=context))

    def rotated(self, *,
        rotation: Rotation, context: Optional[RotationContext]=None,
    ) -> "MaskShape":
        return MaskShape(
            mask=self.mask,
            shape=self.shape.rotated(rotation=rotation, context=context),
        )

    @property
    def area(self) -> float:
        return self.shape.area

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, MaskShape):
            return False
        return (self.mask == o.mask) and (self.shape == o.shape)

    def __hash__(self) -> int:
        return hash((self.mask, self.shape))

    def __repr__(self) -> str:
        return f"MaskShape=(mask={self.mask!r},shape={self.shape!r})"

    @property
    def bounds(self) -> RectangularT:
        return self.shape.bounds


class MaskShapes(_util.ExtendedListMapping[MaskShape, _msk.DesignMask]):
    """A TypedListMapping of MaskShape objects.

    API Notes:
        Contrary to other classes a MaskShapes object is mutable if not frozen.
    """
    @property
    def _index_attribute_(self):
        return "mask"

    def __init__(self, iterable: MultiT[MaskShape]):
        shapes = cast_MultiT(iterable)

        def join_shapes() -> Iterable[MaskShape]:
            masks = []
            for shape in shapes:
                mask = shape.mask
                if mask not in masks:
                    shapes2 = tuple(filter(lambda ms: ms.mask == mask, shapes))
                    if len(shapes2) == 1:
                        yield shapes2[0]
                    else:
                        yield MaskShape(
                            mask=mask,
                            shape=MultiShape(shapes=(ms.shape for ms in shapes2))
                        )
                    masks.append(mask)

        super().__init__(join_shapes())

    def __iadd__(self, shape: MultiT[MaskShape]) -> "MaskShapes":
        for s in cast_MultiT(shape):
            mask = s.mask
            try:
                ms = self[mask]
            except KeyError:
                super().__iadd__(s)
            except: # pragma: no cover
                raise
            else:
                if ms.shape != s.shape:
                    ms2 = MaskShape(
                        mask=mask, shape=MultiShape(shapes=(ms.shape, s.shape)),
                    )
                    self[mask] = ms2

        return self

    def move(self, *, dxy: Point, context: Optional[MoveContext]=None) -> None:
        if context is None:
            context = MoveContext()
        if self._frozen_:
            raise TypeError(f"moving frozen '{self.__class__.__name__}' object not allowed")
        for i in range(len(self)):
            self[i] = self[i].moved(dxy=dxy, context=context)

    def moved(self, *, dxy: Point, context: Optional[MoveContext]=None) -> "MaskShapes":
        """Moved MaskShapes object will not be frozen"""
        if context is None:
            context = MoveContext()
        return MaskShapes(ms.moved(dxy=dxy, context=context) for ms in self)

    def rotate(self, *,
        rotation: Rotation, context: Optional[RotationContext]=None,
    ) -> None:
        if self._frozen_:
            raise TypeError(f"rotating frozen '{self.__class__.__name__}' object not allowed")
        if context is None:
            context = RotationContext()
        for i in range(len(self)):
            self[i] = self[i].rotated(rotation=rotation, context=context)

    def rotated(self, *,
        rotation: Rotation, context: Optional[RotationContext]=None,
    ) -> "MaskShapes":
        """Rotated MaskShapes object will not be frozen"""
        if context is None:
            context = RotationContext()
        return MaskShapes(
            ms.rotated(rotation=rotation, context=context)
            for ms in self
        )
