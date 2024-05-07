# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from typing import Dict

from ..technology import primitive as _prm, technology_ as _tch


__all__ = ["RoutingGauge"]


class RoutingGauge:
    """RoutingGauge represents the arrangement of different metal layers for routing.

    API Notes:
        API for RoutingGause is not fixed. Backwards incompatible changes may still be
            expected.
        see: https://gitlab.com/Chips4Makers/PDKMaster/-/issues/36
            code likely to be moved to c4m-flexcell in the future
    """
    directions = frozenset(("horizontal", "vertical"))

    def __init__(self, *,
        tech: _tch.Technology,
        bottom: _prm.MetalWire, bottom_direction: str, top: _prm.MetalWire,
        pitches: Dict[_prm.MetalWire, float]={},
        offsets: Dict[_prm.MetalWire, float]={},
        pingrid_pitch: float, row_height: float,
    ):
        self._tech = tech
        self._pingrid_pitch = pingrid_pitch
        self._row_height = row_height

        metals = tuple(tech.primitives.__iter_type__(_prm.MetalWire))
        if bottom not in metals:
            raise ValueError(f"bottom is not a MetalWire of technology '{tech.name}'")
        if top not in metals:
            raise ValueError(f"top is not a MetalWire of technology '{tech.name}'")
        bottom_idx = metals.index(bottom)
        top_idx = metals.index(top)
        if bottom_idx >= top_idx:
            raise ValueError("bottom layer has to be below top layer")
        self.bottom = bottom
        self.top = top

        if not bottom_direction in self.directions:
            raise ValueError(f"bottom_direction has to be one of {self.directions}")
        self.bottom_direction = bottom_direction

        for wire, _ in pitches.items():
            if not (
                (wire in metals)
                and (bottom_idx <= metals.index(wire) <= top_idx)
            ):
                raise ValueError(f"wire '{wire.name}' is not part of the Gauge set")
        self.pitches = pitches

        for wire, _ in offsets.items():
            if not (
                (wire in metals)
                and (bottom_idx <= metals.index(wire) <= top_idx)
            ):
                raise ValueError(f"wire '{wire.name}' is not part of the Gauge set")
        self.offsets = offsets

    @property
    def tech(self) -> _tch.Technology:
        return self._tech
    @property
    def pingrid_pitch(self) -> float:
        return self._pingrid_pitch
    @property
    def row_height(self) -> float:
        return self._row_height
