# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from matplotlib import pyplot as plt
import shapely.geometry as sh_geo
import descartes

from ...technology import geometry as _geo
from ...design import layout as _lay
from ...design.layout import layout_ as _laylay

from ... import _util


__all__ = ["Plotter"]


class Plotter:
    def __init__(self, plot_specs={}):
        self.plot_specs = dict(plot_specs)

    def plot(self, obj):
        if _util.is_iterable(obj):
            for item in obj:
                self.plot(item)
        elif isinstance(obj, _lay.LayoutT):
            self.plot(obj._sublayouts)
        elif isinstance(obj, _laylay._MaskShapesSubLayout):
            for ms in obj.shapes:
                self.plot(ms)
        elif isinstance(obj, _geo.MaskShape):
            ax = plt.gca()
            draw_args = self.plot_specs.get(obj.mask.name, {})
            for ps in obj.shape.pointsshapes:
                sh_poly = sh_geo.Polygon((p.x, p.y) for p in ps.points)
                patch = descartes.PolygonPatch(sh_poly, **draw_args)
                ax.add_patch(patch)
        else:
            raise NotImplementedError(f"plotting obj of type '{obj.__class__.__name__}'")
