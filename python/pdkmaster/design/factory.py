# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
import abc
from typing import Optional, Any, Type, TypeVar, Generic, cast, overload, Callable

from ..technology import technology_ as _tch
from . import layout as _lay, circuit as _ckt, cell as _cell, library as _lbry


__all__ = ["FactoryCell", "CellFactory", "BaseCellFactory"]


_cell_type_ = TypeVar(name="_cell_type_", bound=_cell.Cell)
_factory_type_ = TypeVar(name="_factory_type_", bound="CellFactory")
_factorycell_type_ = TypeVar(name="_factorycell_type_", bound="FactoryCell")
_factorycell_type2_ = TypeVar(name="_factorycell_type2_", bound="FactoryCell")


class _FactoryBase(Generic[_cell_type_]):
    def __init__(self, *,
        lib: _lbry.Library, cktfab: _ckt.CircuitFactory, layoutfab: _lay.LayoutFactory,
    ):
        self._lib = lib
        self._cktfab = cktfab
        self._layoutfab = layoutfab

    @property
    def lib(self) -> _lbry.Library:
        return self._lib
    @property
    def tech(self) -> _tch.Technology:
        return self._lib.tech
    @property
    def cktfab(self) -> _ckt.CircuitFactory:
        return self._cktfab
    @property
    def layoutfab(self) -> _lay.LayoutFactory:
        return self._layoutfab

    @abc.abstractmethod
    def new_cell(self, *, name: str, **cell_args) -> _cell_type_:
        ... # pragma: no cover


class FactoryCell(_cell.Cell, Generic[_factory_type_]):
    """A `FactoryCell` is a cell that is generated by a `CellFactory` object.
    It stores the related factory so information like technology, circuit and
    layout factory are available inside the methods for the subclasses.
    """
    def __init__(self, *, name: str, fab: _factory_type_):
        self._fab = fab
        super().__init__(
            name=name, tech=fab.tech, cktfab=fab.cktfab, layoutfab=fab.layoutfab,
        )

    @property
    def lib(self) -> _lbry.Library:
        return self.fab.lib
    @property
    def tech(self) -> _tch.Technology:
        return self.fab.tech
    @property
    def cktfab(self) -> _ckt.CircuitFactory:
        return self.fab.cktfab
    @property
    def layoutfab(self) -> _lay.LayoutFactory:
        return self.fab.layoutfab
    @property
    def fab(self) -> _factory_type_:
        return self._fab


class FactoryOnDemandCell(
    FactoryCell[_factory_type_], _cell.OnDemandCell, Generic[_factory_type_],
):
    """A `FactoryCell` that is also an `OnDemandCell`,
    """
    pass


class CellFactory(_FactoryBase[_factorycell_type_], Generic[_factorycell_type_]):
    """`CellFactory` is used to add cells to a library that are object of type
    `FactoryCell` or a subclass of it.

    Arguments:
        lib: the library to add new cells to
        cktfab, layout: the circuit and layout factory for the created cells
        cell_class: the default class to use for new cells
        name_prefix, name_suffix: prefix and suffix to add to the name of cell
            given to new_cell()/getcreate_cell() method.
            This allows to connect two factories that use same naming scheme to the
            same library without generating conflicts.

    Attributes:
        lib: the library
        cktfab, layout: the circuit and layout factory for the created cells
    """
    def __init__(self, *,
        lib: _lbry.Library, cktfab: _ckt.CircuitFactory, layoutfab: _lay.LayoutFactory,
        cell_class: Type[_factorycell_type_],
        name_prefix: str="", name_suffix="",
    ):
        super().__init__(lib=lib, cktfab=cktfab, layoutfab=layoutfab)
        self._cell_class = cell_class
        self._name_prefix = name_prefix
        self._name_suffix = name_suffix

    def lib_name(self, *, name: str) -> str:
        return f"{self._name_prefix}{name}{self._name_suffix}"

    @overload
    def new_cell(self, *,
        name: str, cell_class: None=None,
        create_cb: Optional[Callable[[FactoryCell], None]]=None,
        **cell_args,
    ) -> _factorycell_type_:
        ... # pragma: no cover
    @overload
    def new_cell(self, *,
        name: str, cell_class: Type[_factorycell_type2_],
        create_cb: Optional[Callable[[_factorycell_type2_], None]]=None,
        **cell_args,
    ) -> _factorycell_type2_:
        ... # pragma: no cover
    def new_cell(self, *,
        name: str, cell_class: Optional[Type[FactoryCell]]=None,
        create_cb: Optional[Callable[[FactoryCell], None]]=None,
        **cell_args,
    ) -> FactoryCell:
        """create a new cell in the library.

        Arguments:
            name: the name of the cell
                name in the library will be with configure prefix and suffix added.
            cell_class: optional class to use for the new cell.
                If not given the factory default one will be used.
                Typically this class is a subclass of the factory default class.
            cell_args: optional extra arguments passed during creation of the
                new cell object.
        """
        if cell_class is None:
            cell_class = self._cell_class

        lib_name = self.lib_name(name=name)
        try:
            self.lib.cells[lib_name]
        except:
            pass
        else:
            raise ValueError(f"Cell '{lib_name}' already exists in library '{self.lib.name}'")

        cell = cell_class(name=lib_name, fab=self, **cell_args)
        if create_cb:
            create_cb(cell)
        self.lib.cells += cell
        return cell

    @overload
    def getcreate_cell(self, *,
        name: str, cell_class: None=None,
        create_cb: Optional[Callable[[FactoryCell], None]]=None,
        **cell_args,
    ) -> _factorycell_type_:
        ... # pragma: no cover
    @overload
    def getcreate_cell(self, *,
        name: str, cell_class: Type[_factorycell_type2_],
        create_cb: Optional[Callable[[_factorycell_type2_], None]]=None,
        **cell_args,
    ) -> _factorycell_type2_:
        ... # pragma: no cover
    def getcreate_cell(self, *,
        name: str, cell_class: Optional[Type[FactoryCell]]=None,
        create_cb: Optional[Callable[[FactoryCell], None]]=None,
        **cell_args,
    ) -> FactoryCell:
        """get or create a new cell in the library.

        Arguments:
            name: the name of the cell
                name in the library will be with configure prefix and suffix added.
                If a cell with the name already exists in the library it is checked
                if the existing cell is of the procided class and will be returned;
                no new cell will then be created.
            cell_class: optional class to use for the new cell.
                If not given the factory default one will be used.
                Typically this class is a subclass of the factory default class.
            cell_args: optional extra arguments passed during creation of the
                new cell object.
        """
        lib_name = self.lib_name(name=name)
        try:
            cell = self.lib.cells[lib_name]
        except:
            return self.new_cell(
                name=name, cell_class=cell_class, create_cb=create_cb, **cell_args,
            )
        else:
            if cell_class is None:
                cell_class = self._cell_class
            if not isinstance(cell, cell_class):
                raise TypeError(
                    f"Cell '{cell.name}' is not of type '{cell_class.__name__}'"
                )

        return cell


#@final
class BaseCellFactory(_FactoryBase[_cell.Cell]):
    """This is a cell factory the allows to generate basic cell objects.
    Typical use case is generation of cells with circuit and optionally
    layout not by methods of the cell class but by external code.
    Use of CellFactory over BaseCellFactory is advised though.

    .. code-block:: python

        fab = BaseCellFactory(lib=lib, cktfab=cktfab, layoutfab=layoutfab)
        cell = fab.new_cell(name="cell")
        ckt = cell.new_circuit()
        ckt.add_net(...)


    Arguments:
        lib: the library to add new cells to
        cktfab, layout: the circuit and layout factory for the created cells

    Attributes:
        lib: the library
        cktfab, layout: the circuit and layout factory for the created cells

    API Notes:
        * Subclassing this class in user code is not a supported use case
          and may break at any point in time.
    """
    def __init__(self, *,
        lib: _lbry.Library, cktfab: _ckt.CircuitFactory, layoutfab: _lay.LayoutFactory,
    ):
        super().__init__(lib=lib, cktfab=cktfab, layoutfab=layoutfab)

    def new_cell(self, *, name: str) -> _cell.Cell:
        """create a new cell in the library.

        Arguments:
            name: the name of the cell
                name in the library will be with configure prefix and suffix added.
        """
        try:
            self.lib.cells[name]
        except:
            pass
        else:
            raise ValueError(f"Cell '{name}' already exists in library '{self.lib.name}'")

        cell = _cell.Cell(
            name=name, tech=self.tech, cktfab=self.cktfab, layoutfab=self.layoutfab,
        )
        self.lib.cells += cell
        return cell
