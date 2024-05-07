# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
"""_util module with private helper functions

API Notes:
    * This is an internal module and none of the functions or classes should be
      called or instantiated in user code. No backward compatibility is provided
      unless stated otherwise in specific autodoc.
"""
import abc
from collections.abc import Hashable
from itertools import islice
from typing import (
    Any, Dict, List, Tuple,
    Optional, Union, Generic, TypeVar, Type,
    Iterable, Iterator, MutableSequence, Mapping, MutableMapping,
    cast, overload,
)
from .typing import MultiT, cast_MultiT

# Typevars used for Generic Collection classes
_elem_typevar_ = TypeVar("_elem_typevar_")
_index_typevar_ = TypeVar("_index_typevar_", bound=Hashable)
_child_class_ = TypeVar("_child_class_")
_iter_typevar_ = TypeVar("_iter_typevar_")


def i2f_recursive(values: Any) -> Any:
    """Recursively convert int and bool elements of an iterable.
    Iterables will be converted to tuples"""
    if is_iterable(values):
        return tuple(i2f_recursive(v) for v in values)
    else:
        return float(values)

def is_iterable(it: Any) -> bool:
    """Check if a value is Iterable"""
    if type(it) is str:
        return False
    try:
        iter(it)
    except:
        return False
    else:
        return True

def get_nth_of(it: Iterable[_elem_typevar_], *, n: int) -> _elem_typevar_:
    """Return nth element from an iterable.

    Arguments:
        n: element to return starting from 0.  
           All values up to the element will have been consumed from the
           iterable.

    Raises:
        StopIteration: if iterable has less than n+1 elements
    """
    return next(islice(it, n, None))

def get_first_of(it: Iterable[_elem_typevar_]) -> _elem_typevar_:
    """Get first element of an iterable

    This function will consume the first element of the iterator

    Raises:
        StopIteration: if iterable is empty
    """
    return get_nth_of(it, n=0)

def get_last_of(it: Iterable[_iter_typevar_]) -> _iter_typevar_:
    """Get last elemeent from an iterator.

    The iterator will be exhausted after calling this function.

    Raises:
        StopIteration: if iterable is empty
    """
    for _v in it:
        v = _v
    try:
        return v # type: ignore
    except NameError:
        raise StopIteration

def strip_literal(s: str) -> str:
    """Strip surrounding '"' of a string.

    Strip head and tail only if they are both '"'
    """
    if (s[0] == '"') and (s[-1] == '"'):
        return s[1:-1]
    else:
        return s


class IterableOverride(Iterable[_iter_typevar_], Generic[_iter_typevar_]):
    """Mixin class to allow to override element with Iterable element with more
    specific element. This is for static typing support to have right element
    for an iterator whose elements are a subclass of parent's element type.

    Example:

        .. code-block:: python

            class Elem:
                pass

            class ElemChild(Elem):
                pass

            T = TypeVar("T")
            class MyList(List[T], Generic[T]):
                pass

            class ElemList(MyList[Elem]):
                pass

            class ElemChildList(IterableOverride[ElemChild], ElemList):
                pass
    """

    def __iter__(self) -> Iterator[_iter_typevar_]:
        return cast(Iterator[_iter_typevar_], super().__iter__())


class IterTypeMixin(Iterable[_elem_typevar_], Generic[_elem_typevar_]):
    """Internal collection support

    TODO: Extended internal API documentation.
    """
    def __iter_type__(self,
        type_: Union[Type[_iter_typevar_], Tuple[Type[_iter_typevar_], ...]],
    ) -> Iterable[_iter_typevar_]:
        """Iterate over elems of an Iterable of certain type

        Arguments:
            type_: type of the element from the Iterable to iterate over
        """
        for elem in self:
            if isinstance(elem, type_):
                yield elem


class ExtendedList(
    List[_elem_typevar_], IterTypeMixin[_elem_typevar_],
    Generic[_elem_typevar_],
):
    """An internal list class that allow only elements of certain type.

    TODO: Extended internal API documentation.
    """
    def __init__(self, iterable: Iterable[_elem_typevar_]=tuple()):
        super().__init__(iterable)

        self._frozen__: bool = False

    def __add__(self,  # type: ignore[override]
        x: Union[_elem_typevar_, List[_elem_typevar_]],
    ) -> "ExtendedList[_elem_typevar_]":
        if isinstance(x, list):
            ret = super().__add__(cast(List[_elem_typevar_], x))
        else:
            ret = super().__add__(cast(List[_elem_typevar_], [x]))
        return cast("ExtendedList[_elem_typevar_]", ret)

    def __delitem__(self, i: Union[int, slice]) -> None:
        if self._frozen_:
            raise TypeError("Can't delete from a frozen list")
        return super().__delitem__(i)

    def __iadd__(self: _child_class_,
        x: MultiT[_elem_typevar_],
    ) -> _child_class_:
        cself = cast(ExtendedList[_elem_typevar_], self)
        if cself._frozen_:
            raise TypeError("Can't extend frozen list")
        cself.extend(cast_MultiT(x))
        return self

    def __imul__(self: "ExtendedList[_elem_typevar_]", n: int) -> "ExtendedList[_elem_typevar_]":
        if self._frozen_:
            raise TypeError("Can't extend frozen list")
        return cast("ExtendedList[_elem_typevar_]", super().__imul__(n))

    def __setitem__(self, i: Union[int, slice], value) -> None:
        if self._frozen_:
            raise TypeError("Can't replace item from a frozen list")
        return super().__setitem__(i, value)

    def append(self, __object: _elem_typevar_) -> None:
        if self._frozen_:
            raise TypeError("Can't append to frozen list")
        return super().append(__object)

    def clear(self) -> None:
        if self._frozen_:
            raise TypeError("Can't clear frozen list")
        return super().clear()

    def extend(self, __iterable: Iterable[_elem_typevar_]) -> None:
        if self._frozen_:
            raise TypeError("Can't extend frozen list")
        return super().extend(__iterable)

    def insert(self, __index: int, __object: _elem_typevar_) -> None:
        if self._frozen_:
            raise TypeError("Can't insert in a frozen list")
        return super().insert(__index, __object)

    def pop(self, __index: int=-1) -> _elem_typevar_:
        if self._frozen_:
            raise TypeError("Can't pop from frozen list")
        return super().pop(__index)

    def remove(self, __value: _elem_typevar_) -> None:
        if self._frozen_:
            raise TypeError("Can't remove from frozen list")
        return super().remove(__value)

    def reverse(self) -> None:
        if self._frozen_:
            raise TypeError("Can't reverse frozen list")
        return super().reverse()

    def sort(self, *, key=None, reverse: bool=False) -> None:
        if self._frozen_:
            raise TypeError("Can't sort a frozen list")
        return super().sort(key=key, reverse=reverse)

    def _freeze_(self) -> None:
        self._frozen__ = True

    @property
    def _frozen_(self) -> bool:
        return self._frozen__

    def _reorder_(self, *, neworder: Iterable[int]) -> None:
        if self._frozen_:
            raise TypeError("Can't reorder a frozen list")
        neworder = tuple(neworder)
        if set(neworder) != set(range(len(self))):
            raise ValueError("neworder has to be iterable of indices with value from 'range(len(self))'")
        newlist = [self[i] for i in neworder]
        self.clear()
        self.extend(newlist)

    def __hash__(self) -> int:
        if not self._frozen_:
            raise TypeError(
                f"'{self.__class__.__name__}' objects need to be frozen to be hashable",
            )
        else:
            return hash(tuple(self))

    def __eq__(self, o: object) -> bool:
        return (
            isinstance(o, ExtendedList)
            and (len(self) == len(o))
            and all(self[i] == o[i] for i in range(len(self)))
        )


class ExtendedListMapping(
    MutableSequence[_elem_typevar_], MutableMapping[_index_typevar_, _elem_typevar_],
    IterTypeMixin[_elem_typevar_], Generic[_elem_typevar_, _index_typevar_],
):
    """An internal collection class that combines a `MutableSequence` with
    `MutableMapping`

    TODO: Extended internal API documentation.

    API Notes:
        ExtendedListMapping assumes not isinstance(Iterable[_elem_typevar], _elem_typevar)
    """
    def __init__(self, iterable: MultiT[_elem_typevar_]=tuple()):
        self._list_ = ExtendedList[_elem_typevar_](cast_MultiT(iterable))

        attr_name = self._index_attribute_
        assert isinstance(attr_name, str)

        self._map_: Dict[_index_typevar_, _elem_typevar_] = {}
        for elem in self._list_:
            if not hasattr(elem, attr_name):
                raise ValueError(f"elem {elem!r} has no attribute '{attr_name}'")
            attr: _index_typevar_ = getattr(elem, attr_name)
            self._map_[attr] = elem

    @property
    @abc.abstractmethod
    def _index_attribute_(self) -> str:
        ... # pragma: no cover

    @overload
    def __getitem__(self, key: Union[int, _index_typevar_]) -> _elem_typevar_:
        ... # pragma: no cover
    @overload
    def __getitem__(self: _child_class_, key: slice) -> _child_class_:
        ... # pragma: no cover
    def __getitem__(self: _child_class_, # type: ignore[override]
        key: Union[int, slice, _index_typevar_],
    ) -> Union[_elem_typevar_, _child_class_]:
        cself = cast(ExtendedListMapping[_elem_typevar_, _index_typevar_], self)
        if isinstance(key, int):
            return cself._list_[key]
        elif isinstance(key, slice):
            o = cself.__class__(
                cself._list_.__getitem__(key),
            )
            return cast(_child_class_, o)
        else:
            # type(key) is _index_typevar_
            return cself._map_[key]

    @overload
    def __setitem__(self,
        key: Union[int, _index_typevar_], value: _elem_typevar_,
    ) -> None:
        ... # pragma: no cover
    @overload
    def __setitem__(self, key: slice, value: Iterable[_elem_typevar_]) -> None:
        ... # pragma: no cover
    def __setitem__(self,
        key: Union[int, slice, _index_typevar_],
        value: MultiT[_elem_typevar_],
    ) -> None:
        if self._frozen_:
            raise TypeError("Can't change a frozen list")
        if isinstance(key, int):
            old = self._list_[key]
            try:
                self._map_.pop(getattr(old, self._index_attribute_))
            except: # pragma: no cover
                # If the elem is in _list_ it should also be in _map_
                raise RuntimeError("Internal error")
            key2 = getattr(value, self._index_attribute_)
            self._list_[key] = cast(_elem_typevar_, value)
            self._map_[key2] = cast(_elem_typevar_, value)
        elif isinstance(key, slice): # pragma: no cover
            raise NotImplementedError(
                "Assigning to slice of ExtendedListMapping"
            )
        else:
            value = cast(_elem_typevar_, value)
            for i, elem in enumerate(self._list_):
                if getattr(elem, self._index_attribute_) == key:
                    self._list_[i] = value
                    self._map_[key] = cast(_elem_typevar_, value)
                    break
            else:
                self += value

    def __delitem__(self,
        key: Union[int, slice, _index_typevar_],
    ) -> None:
        if self._frozen_:
            raise TypeError("Can't change a frozen list")
        if isinstance(key, int):
            old = self._list_[key]
            self._map_.pop(getattr(old, self._index_attribute_))
            self._list_.__delitem__(key)
        elif isinstance(key, slice): # pragma: no cover
            raise NotImplementedError(
                "Deleting slice of ExtendedListMapping"
            )
        else:
            v = self._map_.pop(key)
            self._list_.remove(v)

    def clear(self) -> None:
        if self._frozen_:
            raise TypeError("Can't change a frozen list")
        self._list_.clear()
        self._map_.clear()

    def pop(self, # type: ignore[override]
        key: Optional[Union[_index_typevar_, int]]=None,
    ) -> _elem_typevar_:
        if self._frozen_:
            raise TypeError("Can't change a frozen list")
        if key is None:
            elem = self._list_.pop()
            self._map_.pop(getattr(elem, self._index_attribute_))
        elif isinstance(key, int):
            elem = self._list_.pop(key)
            self._map_.pop(getattr(elem, self._index_attribute_))
        else:
            elem = self._map_.pop(key)
            self._list_.remove(elem)
        return elem

    def popitem(self):
        raise NotImplementedError("ExtendedListMapping.popitem()")

    def update(self, # type: ignore[override]
        __m: Mapping[_index_typevar_, _elem_typevar_]
    ) -> None:
        raise NotImplementedError("ExtendedListMapping.update()")

    def __iter__(self) -> Iterator[_elem_typevar_]:
        return iter(self._list_)

    def __len__(self) -> int:
        return len(self._list_)

    def __contains__(self, elem: Any) -> bool:
        return getattr(elem, self._index_attribute_) in self._map_

    def index(self, elem: _elem_typevar_) -> int: # type: ignore[override]
        """
        API Notes:
            * Specifying start/end is currently not supported
        """
        return self._list_.index(elem)

    def insert(self, index: int, value: _elem_typevar_) -> None:
        if self._frozen_:
            raise TypeError("Can't change a frozen list")
        self._list_.insert(index, value)
        self._map_[getattr(value, self._index_attribute_)] = value

    def keys(self):
        return self._map_.keys()

    def items(self):
        return self._map_.items()

    def values(self):
        return self._map_.values()

    def __iadd__(self: _child_class_,
        x: MultiT[_elem_typevar_],
    ) -> _child_class_:
        if cast("ExtendedListMapping", self)._frozen_:
            raise TypeError("Can't change a frozen list")
        cself = cast(ExtendedListMapping[_elem_typevar_, _index_typevar_], self)
        new = cast_MultiT(x)
        cself._list_ += new
        for e in new:
            cself._map_[getattr(e, cself._index_attribute_)] = e
        return self

    def _freeze_(self) -> None:
        self._list_._freeze_()

    @property
    def _frozen_(self) -> bool:
        return self._list_._frozen_

    def _reorder_(self, neworder: Iterable[int]) -> None:
        if self._frozen_:
            raise TypeError("Can't reorder a frozen list")
        self._list_._reorder_(neworder=neworder)


class _ListMappingOverride(
    MutableSequence[_elem_typevar_], MutableMapping[_index_typevar_, _elem_typevar_],
    Generic[_elem_typevar_, _index_typevar_],
):
    """A support class for helping subclassing of ListMapping. It allows to subclass
    a ListMapping class with an element that is a subclass of the parent ListMapping
    element.

    TODO: Extended internal API documentation.
    """
    @overload
    def __getitem__(self, key: Union[int, _index_typevar_]) -> _elem_typevar_:
        ... # pragma: no cover
    @overload
    def __getitem__(self: _child_class_, key: slice) -> _child_class_:
        ... # pragma: no cover
    def __getitem__(self: _child_class_, # type: ignore[override]
        key: Union[int, slice, _index_typevar_],
    ) -> Union[_elem_typevar_, _child_class_]:
        return cast(Any, super()).__getitem__(key)

    @overload
    def __setitem__(self,
        key: Union[int, _index_typevar_], value: _elem_typevar_,
    ) -> None:
        ... # pragma: no cover
    @overload
    def __setitem__(self, key: slice, value: Iterable[_elem_typevar_]) -> None:
        ... # pragma: no cover
    def __setitem__(self,
        key: Union[int, slice, _index_typevar_],
        value: MultiT[_elem_typevar_],
    ) -> None:
        return cast(Any, super()).__setitem__(key, value)

    def __delitem__(self,
        key: Union[int, slice, _index_typevar_],
    ) -> None:
        return cast(Any, super()).__delitem__(key)

    def pop(self, # type: ignore[override]
        key: Optional[_index_typevar_]=None,
    ) -> _elem_typevar_:
        return cast(Any, super()).pop(key)

    def update(self, # type: ignore[override]
        __m: Mapping[_index_typevar_, _elem_typevar_]
    ) -> None:
        return cast(Any, super()).update(__m)

    def __iter__(self) -> Iterator[_elem_typevar_]:
        return cast(Any, super()).__iter__()

    def index(self, elem: _elem_typevar_) -> int: # type: ignore[override]
        return cast(Any, super()).index(elem)

    def insert(self, index: int, value: _elem_typevar_) -> None:
        return cast(Any, super()).insert(index, value)

    def __iadd__(self: _child_class_,
        x: MultiT[_elem_typevar_],
    ) -> _child_class_:
        return cast(Any, super()).__iadd__(x)


class ExtendedListStrMapping(ExtendedListMapping[_elem_typevar_, str], Generic[_elem_typevar_]):
    """TypeListMapping where the index `type_` is `str`. By default this also take 'name'
    as default attribute name for the index. This can be overloaded in a subclass if
    needed.

    TODO: Extended internal API documentation.
    """
    @property
    def _index_attribute_(self):
        return "name"

    def __getattr__(self, name: str) -> _elem_typevar_:
        return self._map_[name]


class ListStrMappingOverride(
    _ListMappingOverride[_elem_typevar_, str], Generic[_elem_typevar_],
):
    """A support class for helping subclassing of TypeListStrMapping analog to
    `_ListMappingOverride`.

    TODO: Extended internal API documentation.
    """
    def __getattr__(self, name: str) -> _elem_typevar_:
        return cast(Any, super()).__getattr__(name)
