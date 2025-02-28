# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from typing import Union, cast

from pdkmaster import _util
from pdkmaster.technology import geometry as _geo

import pya


__all__ = ["import_poly2poly", "import_region2poly", "import_region2shape"]


def import_poly2poly(polygon: pya.Polygon) -> _geo.Polygon:
    """Convert klayout db to PKDMaster Polygon object

    API Notes:
        This function is for internal use and does not have backwards compatibility
        guarantee.
    """
    if isinstance(polygon, pya.Box):
        box = cast(pya.Box, polygon).to_dtype(_geo.epsilon)
        return _geo.Rect(
            left=box.left, bottom=box.bottom, right=box.right, top=box.top,
        )
    elif polygon.is_box():
        box = polygon.bbox().to_dtype(_geo.epsilon)
        return _geo.Rect(
            left=box.left, bottom=box.bottom, right=box.right, top=box.top,
        )
    else:
        poly2 = (
            cast(pya.SimplePolygon, polygon) if isinstance(polygon, pya.SimplePolygon)
            else polygon.to_simple_polygon()
        )
        spoly = poly2.to_dtype(_geo.epsilon)
        p0 = _util.get_first_of(spoly.each_point())
        return _geo.Polygon(points=(
            *(_geo.Point(x=p.x, y=p.y) for p in spoly.each_point()),
            _geo.Point(x=p0.x, y=p0.y),
        ))


def import_region2poly(region: pya.Region) -> _geo.Polygon:
    """Convert pya.Region containing a single polygon to a PDKMaster _geo.Polygon object.
    """
    shape = import_region2shape(region=region)
    if not isinstance(shape, _geo.Polygon):
        raise ValueError("Region with multiple polygons can't be converted to single polygon")
    return shape


def import_region2shape(region: pya.Region) -> Union[_geo.Polygon, _geo.MultiShape]:
    """Convert pya.Region containing a single polygon to a PDKMaster _geo.MultiShape object.
    """
    region.merge()

    shapes = tuple(import_poly2poly(pyapoly) for pyapoly in region.each())
    if len(shapes) == 0:
        raise ValueError("Can't convert an empty region")
    elif len(shapes) == 1:
        return shapes[0]
    else:
        return _geo.MultiShape(shapes=shapes)
