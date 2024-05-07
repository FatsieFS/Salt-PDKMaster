# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from ..technology import edge as _edg


class EdgeDispatcher:
    """Dispatch to class method based on type of `_Edge` subclasses.

    This dispatcher follows the common way of working in the `dispatch` module.
    """
    def __call__(self, edge: _edg.EdgeT, *args, **kwargs):
        classname = edge.__class__.__name__.split(".")[-1]
        return getattr(self, classname, self._pd_unhandled)(edge, *args, **kwargs)

    def _pd_unhandled(self, edge, *args, **kwargs):
        raise RuntimeError(
            "Internal error: unhandled dispatcher for object of type "
            f"{edge.__class__.__name__}"
        )

    def _Edge(self, edge: _edg.EdgeT, *args, **kwargs):
        raise NotImplementedError(
            f"No dispatcher implemented for object of type {edge.__class__.__name__}"
        )

    def _DualEdgeOperation(self, op: _edg._DualEdgeOperation, *args, **kwargs):
        return self._Edge(op, *args, **kwargs)

    def MaskEdge(self, edge: _edg.MaskEdge, *args, **kwargs):
        return self._Edge(edge, *args, **kwargs)

    def Join(self, join: _edg.Join, *args, **kwargs):
        return self._Edge(join, *args, **kwargs)

    def Intersect(self, intersect: _edg.Intersect, *args, **kwargs):
        return self._Edge(intersect, *args, **kwargs)
