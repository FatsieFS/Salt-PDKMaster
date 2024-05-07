# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from typing import Iterable, Tuple, Dict, Optional, Union, TypeVar, cast

"""This is a module for typing support for PDKMaster.

Type aliases:
    MultiT: generic type to represent singleton or an iterable of a certain type.
    OptMultiT: generic type to represent None, singleton or an iterable of a certain type.
"""

T = TypeVar("T")
MultiT = Union[T, Iterable[T]]
OptMultiT = Optional[MultiT[T]]

def cast_MultiT(vs: MultiT[T], *, singular_type: Tuple[type, ...]=(str,)) -> Tuple[T, ...]:
    """cast a MultiT[T] object to tuple[T, ...].

    contrary to `typing.cast` this function is not pure type annotation but actually
    generated the tuple object that is returned.
    """
    try:
        iter(vs) # type: ignore
    except TypeError:
        return (cast(T, vs),)
    else:
        if isinstance(vs, singular_type):
            return (cast(T, vs),)
        else:
            return tuple(cast(Iterable[T], vs))

def cast_MultiT_n(
    vs: MultiT[T], *,
    n: int, singular_type: Tuple[type, ...]=(str,),
) -> Tuple[T, ...]:
    """cast a MultiT[T] object to tuple[T, ...] with specified number of elements.

    If single value is given it will be repeated n times; if an iterable is given with
    size not equal to 1 or n a ValueError exception will be raised.

    contrary to `typing.cast` this function is not pure type annotation but actually
    generated the tuple object that is returned.
    """
    try:
        iter(vs) # type: ignore
    except TypeError:
        v = (cast(T, vs),)
    else:
        if isinstance(vs, singular_type):
            v = (cast(T, vs),)
        else:
            v = tuple(cast(Iterable[T], vs))
    if (n == 0) and (len(v) != 0):
        raise ValueError(f"Value(s) provided for MultiT that has to be zero length")
    if len(v) == 1:
        v *= n
    if len(v) != n:
        raise ValueError(f"Exactly {n} elements need to be provided not {len(v)}")
    return v

def cast_OptMultiT(vs: OptMultiT[T], *, singular_type: Tuple[type, ...]=(str,)) -> Optional[Tuple[T, ...]]:
    """cast a OptMultiT[T] object to Optional[tuple[T, ...]].

    contrary to `typing.cast` this function is not pure type annotation but actually
    generated the tuple object that is returned.
    """
    if vs is None:
        return None
    else:
        return cast_MultiT(vs, singular_type=singular_type)

def cast_OptMultiT_n(
    vs: OptMultiT[T], *,
    n: int, singular_type: Tuple[type, ...]=(str,),
) -> Optional[Tuple[T, ...]]:
    """cast a OptMultiT[T] object to Optional[tuple[T, ...]] with specified number
    of elements.

    If None is given, None will be returned; if single value is given it will be
    repeated n times; if an iterable is given with size not equal to 1 or n a
    ValueError exception will be raised.

    contrary to `typing.cast` this function is not pure type annotation but actually
    generated the tuple object that is returned.
    """
    return vs if vs is None else cast_MultiT_n(vs, n=n, singular_type=singular_type)


GDSLayerSpec = Union[None, int, Tuple[int, int]]
# We define the gds_layer lookup table by str,
# Doing it directly by DesignMask would be preferred but this leads
# to complicated recursive imports
GDSLayerSpecDict = Dict[str, GDSLayerSpec]
