# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from typing import Union, Optional, Callable

from ...technology import geometry as _geo, primitive as _prm, technology_ as _tch
from .. import circuit as _ckt

from .layout_ import _SubLayout, _SubLayouts, _Layout, LayoutT
# also imports at end of file to avoid circular import problems

__all__ = ["LayoutFactory"]


class LayoutFactory:
    """The user facing class for creating layouts. This class is also a base
    class on which own factory classes can be built with specific extensions.

    Parameters:
        tech: the technology for which to create circuits. Created layout may
            only contain shapes on masks defined by the technology.
        create_cb: callback to be called after the layout of a primitive is
            generated. This allows to do additional layout for specific nodes.
            Signature cb(*, layout: LayoutT, prim: Primitive, **prim_params)

    API Notes:
        The contract for making subclasses has not been finaziled. Backwards
            incompatible changes are still expected for subclasses of this class.
        The use of create_cb is not considered finalized; signature of the
            callback or even replacement with another mechanism may
            happen in the future.
    """
    def __init__(self, *,
        tech: _tch.Technology, create_cb: Optional[Callable]=None,
    ):
        from ._primitivelayouter import _PrimitiveLayouter

        self.tech = tech
        self.gen_primlayout = _PrimitiveLayouter(self, create_cb)

    def new_layout(self, *,
        sublayouts: Optional[Union[_SubLayout, _SubLayouts]]=None,
        boundary: Optional[_geo._Rectangular]=None,
    ) -> LayoutT:
        """Create a new layout.

        Arguments:
            sublayouts: optional list of sublayouts to add to this new layout
            boundary: optional boundary of the new layout
        """
        if sublayouts is None:
            sublayouts = _SubLayouts()
        if isinstance(sublayouts, _SubLayout):
            sublayouts = _SubLayouts(sublayouts)

        return _Layout(fab=self, sublayouts=sublayouts, boundary=boundary)

    def layout_primitive(self, prim: _prm.PrimitiveT, **prim_params) -> LayoutT:
        """Create the layout of a `_Primitive` object.

        This will generate a default layout for a given primitive with the
        provided paramters. This is a default layout

        Arguments:
            prim: the primitive to create a layout for
            prim_params: the parameters for the primitive

        API Notes:
            User code can't depend on the exact layout generated for a certain
                primitive. Future improvements to the layout generation code
                may change the resulting layout.
        """
        return self.gen_primlayout(prim, **prim_params)

    def new_circuitlayouter(self, *,
        circuit:_ckt._Circuit, boundary: Optional[_geo._Rectangular],
    ) -> "CircuitLayouterT":
        """Helper class to generate layout corresponding to a given `_Circuit`.
        The returned layouter will start with an empty layout with optionally a
        provided boundary. The layouter API can then be used to build up the
        layout for the circuit.

        Arguments:
            circuit: the circuit for which to create a layouter
            boundary: optional boundary of the created layout

        API Notes:
            The API of the returned layouter is not fixed yet and backwards
            incompatible changes are still expected.
        """
        return _CircuitLayouter(fab=self, circuit=circuit, boundary=boundary)


# import at end of file to avoid circular import problems
from ._circuitlayouter import _CircuitLayouter, CircuitLayouterT
