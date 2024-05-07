# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
import abc
from typing import List, Tuple, Iterable, Union, Optional, cast

from ... import _util
from ...typing import MultiT, cast_MultiT
from .. import (
    rule as _rle, net as _net, mask as _msk, wafer_ as _wfr, technology_ as _tch,
)


# Export all for internal use; only export not starting with _ are imported in
# __init__.py
__all__ = [
    "PrimitiveT", "Primitives", "MaskPrimitiveT", "DesignMaskPrimitiveT",
    "SpaceTableRowT",
    "WidthSpacePrimitiveT", "WidthSpaceDesignMaskPrimitiveT",
    "UnusedPrimitiveError", "UnconnectedPrimitiveError",
]


class _PrimitiveNet(_net._Net):
    def __init__(self, *, prim: "_Primitive", name: str):
        super().__init__(name)
        self.prim = prim

    def __hash__(self):
        return hash((self.name, self.prim))

    def __eq__(self, other: object) -> bool:
        if type(other) is not _PrimitiveNet:
            return False
        else:
            return (self.name == other.name) and (self.prim == other.prim)

    def __repr__(self):
        return f"{self.prim.name}.{self.name}"


class _PrimitivePorts(
    _util.IterableOverride[Union[_PrimitiveNet, _wfr.SubstrateNet]],
    _net.Nets,
):
    pass


class _Primitive(abc.ABC):
    @abc.abstractmethod
    def __init__(self, *, name: str):
        self.name = name

        self.ports = _PrimitivePorts()

        self._rules: Optional[Tuple[_rle.RuleT, ...]] = None

    def __repr__(self):
        cname = self.__class__.__name__.split(".")[-1]
        return f"{cname}(name={self.name})"

    def __eq__(self, other: object) -> bool:
        """Two primitives are the same if their name is the same"""
        return (isinstance(other, _Primitive)) and (self.name == other.name)

    def __hash__(self):
        return hash(self.name)

    @property
    def rules(self) -> Tuple[_rle.RuleT, ...]:
        if self._rules is None:
            raise AttributeError(
                "Internal error: accessing rules before they are generated",
            )
        return self._rules

    @abc.abstractmethod
    def _generate_rules(self, *,
        tech: "_tch.Technology",
    ) -> Iterable[_rle.RuleT]:
        return tuple()

    def _derive_rules(self, tech: "_tch.Technology") -> None:
        if self._rules is not None:
            raise ValueError(
                "Internal error: rules can only be generated once",
            )
        self._rules = tuple(self._generate_rules(tech=tech))

    @abc.abstractproperty
    def designmasks(self) -> Iterable[_msk.DesignMask]:
        return tuple()
PrimitiveT = _Primitive


class _MaskPrimitive(_Primitive):
    @abc.abstractmethod
    def __init__(self, *,
        name: Optional[str]=None, mask: _msk.MaskT,
        **primitive_args,
    ):
        if name is None:
            name = mask.name
        super().__init__(name=name, **primitive_args)

        self.mask = mask

    @abc.abstractmethod
    def _generate_rules(self, *,
        tech: "_tch.Technology", gen_mask: bool=True,
    ) -> Iterable[_rle.RuleT]:
        yield from super()._generate_rules(tech=tech)

        if gen_mask and isinstance(self.mask, _rle.RuleT):
            yield cast(_rle.RuleT, self.mask)

    @property
    def designmasks(self):
        return self.mask.designmasks

    def remove(self, what: MultiT["MaskPrimitiveT"], *args: "MaskPrimitiveT") -> "MaskPrimitiveT":
        """Return a MaskPrimitive based on the MaskPrimitive but with
        the overlapping parts with another MaskPrimitive removed.
        """
        return _drv._Outside(prim=self, where=(*cast_MultiT(what), *args))

    def alias(self, alias: str) -> "MaskPrimitiveT":
        return _drv._Alias(prim=self, alias=alias)
MaskPrimitiveT = _MaskPrimitive


class Primitives(_util.ExtendedListStrMapping[_Primitive]):
    """A collection of `_Primitive` objects"""
    def __iadd__(self, x: MultiT[_Primitive]) -> "Primitives":
        from ._derived import _DerivedPrimitive

        x = cast_MultiT(x)
        for elem in x:
            if isinstance(elem, _DerivedPrimitive):
                raise TypeError(
                    f"_DerivedPrimitive '{elem.name}' can't be added to 'Primitives'",
                )
            if elem in self:
                raise ValueError(
                    f"Adding primitive with name '{elem.name}' twice"
                )
        return cast("Primitives", super().__iadd__(x))


class _DesignMaskPrimitive(_MaskPrimitive):
    @abc.abstractmethod
    def __init__(self, *, name: str, grid: Optional[float]=None, **super_args):
        if "mask" in super_args:
            raise TypeError(
                f"{self.__class__.__name__} got unexpected keyword argument 'mask'",
            )
        mask = _msk.DesignMask(name=name)
        super().__init__(name=name, mask=mask, **super_args)
        self.mask: _msk.DesignMask
        self.grid = grid

    @abc.abstractmethod
    def _generate_rules(self, *,
        tech: "_tch.Technology", gen_mask: bool=True,
    ) -> Iterable[_rle.RuleT]:
        yield from super()._generate_rules(tech=tech)

        if self.grid is not None:
            yield cast(_msk.DesignMask, self.mask).grid == self.grid
DesignMaskPrimitiveT = _DesignMaskPrimitive


SpaceTableRowT = Tuple[
    Union[float, Tuple[float, float]],
    float,
]
class _WidthSpacePrimitive(_MaskPrimitive):
    """Common abstract base class for Primitives that have width and space property.
    Subclasses of this class will need to provide certain properties as parameters
    to the object `__init__()`

    Arguments:
        min_width: min width of drawn feature
        min_space: min space between drawn features
        space_table: optional width dependent spacing rules.
            it is an iterable of rows with each row of the form
            `width, space` or `(width, height), space`
        min_density, max_density: optional minimum or maximum denity specification
    """
    @abc.abstractmethod
    def __init__(self, *,
        min_width: float, min_space: float,
        space_table: Optional[Iterable[Iterable[float]]]=None,
        min_area: Optional[float]=None,
        min_density: Optional[float]=None, max_density: Optional[float]=None,
        **maskprimitive_args
    ):
        from ._param import _PrimParam

        self.min_width = min_width
        self.min_space = min_space
        self.min_area = min_area
        self.min_density = min_density
        if (
            (min_density is not None)
            and ((min_density < 0.0) or (min_density > 1.0))
        ):
            raise ValueError("min_density has be between 0.0 and 1.0")
        self.max_density = max_density
        if (
            (max_density is not None)
            and ((max_density < 0.0) or (max_density > 1.0))
        ):
            raise ValueError("max_density has be between 0.0 and 1.0")

        if space_table is not None:
            table: List[SpaceTableRowT] = []
            for row in space_table:
                values = _util.i2f_recursive(row)
                width, space = values
                if not (
                    isinstance(width, float)
                    or (
                        isinstance(width, tuple) and (len(width) == 2)
                        and all(isinstance(w, float) for w in width)
                    )
                ):
                    raise TypeError(
                        "first element in a space_table row has to be a float "
                        "or an iterable of two floats"
                    )

                table.append((
                    cast(Union[float, Tuple[float, float]], width),
                    space,
                ))
            self.space_table = tuple(table)
        else:
            self.space_table = None

        super().__init__(**maskprimitive_args)

    @abc.abstractmethod
    def _generate_rules(self, *,
        tech: "_tch.Technology",
    ) -> Iterable[_rle.RuleT]:
        from .layers import Marker

        yield from super()._generate_rules(tech=tech)

        yield from (
            self.mask.width >= self.min_width,
            self.mask.space >= self.min_space,
        )
        if self.min_area is not None:
            yield self.mask.area >= self.min_area
        if self.min_density is not None:
            yield self.mask.density >= self.min_density
        if self.max_density is not None:
            yield self.mask.density <= self.max_density
        if self.space_table is not None:
            for row in self.space_table:
                w = row[0]
                if isinstance(w, float):
                    submask = self.mask.parts_with(
                        condition=self.mask.width >= w,
                    )
                else:
                    submask = self.mask.parts_with(condition=(
                        self.mask.width >= w[0],
                        self.mask.length >= w[1],
                    ))
                yield _msk.Spacing(submask, self.mask) >= row[1]
        try:
            pin: Marker = self.pin # type: ignore
        except AttributeError:
            pass
        else:
            yield _msk.Connect(self.mask, pin.mask)
WidthSpacePrimitiveT = _WidthSpacePrimitive


class _WidthSpaceDesignMaskPrimitive(_DesignMaskPrimitive, _WidthSpacePrimitive):
    """_WidthSpacePrimitive that is also a _DesignMaskPrimitive
    """
    pass
WidthSpaceDesignMaskPrimitiveT = _WidthSpaceDesignMaskPrimitive


class UnusedPrimitiveError(Exception):
    """Exception used by `Technology` when checking the primitives list
    of a technology"""
    def __init__(self, *, primitive: _Primitive, msg: Optional[str]=None):
        if msg is None:
            msg = f"primitive '{primitive.name}' defined but not used"
        super().__init__(msg)


class UnconnectedPrimitiveError(Exception):
    """Exception used by `Technology` when checking the primitives list
    of a technology"""
    def __init__(self, *, primitive: _Primitive):
        super().__init__(
            f"primitive '{primitive.name}' is not connected"
        )


from . import _derived as _drv
