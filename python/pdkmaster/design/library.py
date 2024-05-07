# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from typing import Iterable, cast

from ..typing import MultiT, cast_MultiT
from ..technology import technology_ as _tch
from . import layout as _lay, circuit as _ckt, cell as _cell, routinggauge as _rg


__all__ = ["Library", "RoutingGaugeLibrary"]


class Library:
    """A Library is an object representing a collection of Cell objects.
    All cell in a library have be for the same technology.

    Arguments:
        name: the name of the library
        tech: the technology for the cells in the library
    """
    def __init__(self, *, name: str, tech: _tch.Technology):
        self._name = name
        self._tech = tech

        self._cells = _cell._Cells()

    @property
    def name(self) -> str:
        return self._name
    @property
    def tech(self) -> _tch.Technology:
        return self._tech

    @property
    def cells(self) -> _cell.CellsT:
        return self._cells
    @cells.setter
    def cells(self, cells: _cell.CellsT) -> None:
        """The setter is provided to allow adding of cells by `lib.cells += cell`.
        Assigning to the cells attribute is not allowed.
        """
        if id(self._cells) != id(cells):
            raise AttributeError("can't set attribute")

    @property
    def sorted_cells(self) -> Iterable[_cell.Cell]:
        """Return sorted iterable of the hierarchical instantiated cells.
        The cells will be sorted such that a cell is in the list before a
        cell where it is instantiated.

        If there are cells instantiated from other libraries they will be
        included.
        """
        cells = set()
        for cell in self.cells:
            if cell not in cells:
                for subcell in cell.subcells_sorted:
                    if subcell not in cells:
                        yield subcell
                        cells.add(subcell)
                yield cell
                cells.add(cell)


class RoutingGaugeLibrary(Library):
    """A `Library` with an associated `RoutingGauge`

    API Notes:
        API for StdCellLibrary is not fixed. Backwards incompatible changes may still be
            expected.
        see: https://gitlab.com/Chips4Makers/PDKMaster/-/issues/36
            code likely to be moved to c4m-flexcell in the future
    """
    def __init__(self, *,
        name: str, tech: _tch.Technology,
        routinggauge: MultiT[_rg.RoutingGauge],
    ):
        super().__init__(name=name, tech=tech)
        self._routinggauge = cast_MultiT(routinggauge)

    @property
    def routinggauge(self) -> Iterable[_rg.RoutingGauge]:
        return self._routinggauge
    @property
    def pingrid_pitch(self) -> float:
        return self._routinggauge[0].pingrid_pitch
    @property
    def row_height(self) -> float:
        return self._routinggauge[0].row_height
