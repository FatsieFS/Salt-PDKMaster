# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
import abc
from typing import Iterable, Optional

from .. import _util
from ..technology import geometry as _geo, technology_ as _tch
from . import layout as _lay, circuit as _ckt

__all__ = ["Cell", "OnDemandCell", "CellsT"]


class Cell:
    """A cell is an element from a `Library` and represents the building blocks
    of a circuit. A cell may contain one or more circuits and one or more layouts.

    API Notes:
        User supported ways for creating cells is not fixed. Backwards incompatible
        changes are still expected.
    """
    def __init__(self, *,
        name: str,
        tech: _tch.Technology, cktfab: _ckt.CircuitFactory, layoutfab: _lay.LayoutFactory,
    ):
        self._name = name
        self._tech = tech
        self._cktfab = cktfab
        self._layoutfab = layoutfab

        self._circuits = _ckt._Circuits()
        self._layouts = _CellLayouts()

    @property
    def name(self) -> str:
        return self._name
    @property
    def tech(self) -> _tch.Technology:
        return self._tech
    @property
    def cktfab(self) -> _ckt.CircuitFactory:
        return self._cktfab
    @property
    def layoutfab(self) -> _lay.LayoutFactory:
        return self._layoutfab

    @property
    def circuit(self) -> _ckt.CircuitT:
        """The default circuit of the cell;' it's the one with the same name as
        the cell"""
        try:
            return self._circuits[self.name]
        except KeyError:
            raise ValueError(f"Cell '{self.name}' has no default circuit")

    def circuit_lookup(self, *, name: str) -> _ckt.CircuitT:
        try:
            return self._circuits[name]
        except KeyError:
            raise ValueError(f"Cell '{self.name}' has no circuit named '{name}'")

    @property
    def layout(self) -> _lay.LayoutT:
        """The default layout of the cell;' it's the one with the same name as
        the cell"""
        try:
            return self._layouts[self.name].layout
        except KeyError:
            raise ValueError(f"Cell '{self.name}' has no default layout")

    def layout_lookup(self, *, name: str) -> "_lay.LayoutT":
        try:
            return self._layouts[name].layout
        except KeyError:
            raise ValueError(f"Cell '{self.name}' has no layout name '{name}'")


    def new_circuit(self, *, name: Optional[str]=None) -> _ckt.CircuitT:
        """Create a new empty circuit for the cell.

        Arguments:
            name: the name of the circuit. If not specified the same name as the
                cell will be used.
        """
        if name is None:
            name = self.name

        circuit = self.cktfab.new_circuit(name=name)
        self._circuits += circuit
        return circuit

    def new_layout(self, *,
        name: Optional[str]=None, boundary: Optional[_geo._Rectangular]=None,
    ) -> "_lay.LayoutT":
        """Create a new empty layout for the cell.

        Arguments:
            name: the name of the circuit. If not specified the same name as the
                cell will be used.
            boundary: optional boundary for the layout
        """
        if name is None:
            name = self.name

        layout = self.layoutfab.new_layout(boundary=boundary)
        self._layouts += _CellLayout(name=name, layout=layout)
        return layout

    def new_circuitlayouter(self, *,
        name: Optional[str]=None, boundary: Optional[_geo._Rectangular]=None,
    ) -> "_lay.CircuitLayouterT":
        """Create a circuit layouter for a circuit of the cell.

        Arguments:
            name: optional name for the circuit
        API Notes:
            _CircuitLayouter API is not fixed.
                see: https://gitlab.com/Chips4Makers/PDKMaster/-/issues/25
        """
        if name is None:
            name = self.name
            circuit = self.circuit
        else:
            try:
                circuit = self._circuits[name]
            except KeyError:
                raise ValueError(f"circuit with name '{name}' not present")

        layouter = self.layoutfab.new_circuitlayouter(
            circuit=circuit, boundary=boundary,
        )
        self._layouts += _CellLayout(name=name, layout=layouter.layout)
        return layouter

    @property
    def subcells_sorted(self) -> Iterable["Cell"]:
        cells = set()
        for circuit in self._circuits:
            for cell in circuit.subcells_sorted:
                if cell not in cells:
                    yield cell
                    cells.add(cell)


class OnDemandCell(Cell, abc.ABC):
    """_Cell with on demand circuit and layout creation

    The circuit and layout will only be generated the first time it is accessed.
    """
    @property
    def circuit(self) -> _ckt.CircuitT:
        try:
            return self._circuits[self.name]
        except KeyError:
            self._create_circuit()
            try:
                return self._circuits[self.name]
            except:
                raise NotImplementedError(
                    f"Cell '{self.name}' default circuit generation"
                )

    @property
    def layout(self) -> _lay.LayoutT:
        try:
            return self._layouts[self.name].layout
        except KeyError:
            self._create_layout()
            try:
                return self._layouts[self.name].layout
            except:
                raise NotImplementedError(
                    f"Cell '{self.name}' default layout generation"
                )

    @abc.abstractmethod
    def _create_circuit(self):
        ... # pragma: no cover

    @abc.abstractmethod
    def _create_layout(self):
        ... # pragma: no cover


class _Cells(_util.ExtendedListStrMapping[Cell]):
    pass
CellsT = _Cells


class _CellLayout:
    def __init__(self, *, name: str, layout: "_lay.LayoutT"):
        self.name = name
        self.layout = layout


class _CellLayouts(_util.ExtendedListStrMapping[_CellLayout]):
    pass
