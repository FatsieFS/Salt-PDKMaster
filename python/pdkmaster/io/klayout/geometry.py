# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from typing import Optional

from pdkmaster.technology import geometry as _geo

from . import import_ as _imp

import pya


__all__ = ["text"]


def text(text: str, *,
    mag: float=1.0,
    inv: Optional[bool]=None,
    bias: float=0.0,
    char_spacing: Optional[float]=None,
    line_spacing: Optional[float]=None,
    grid: Optional[float]=None,
    font_name: str="std_font",
) -> _geo.ShapeT:
    """Function to generate a text shape using the klayout's `TextGenerator.text()`

    The font_name argument will be used to get the generator using
    `pya.TextGenerator.generator_by_name()`. Other parameters are passed to `TextGenerator.text()`
    """
    tg = pya.TextGenerator.generator_by_name(font_name)
    t = tg.text(
        text, _geo.epsilon, mag, inv, bias, char_spacing, line_spacing,
    )
    if grid is not None:
        grid2 = round(grid/_geo.epsilon)
        t.snap(grid2, grid2)

    return _imp.import_region2shape(t)
