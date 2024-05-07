# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from typing import Dict, Sequence, Mapping, Iterable, Union, Optional, Any, Callable, cast

from pdkmaster.technology import primitive as _prm

from ...typing import MultiT, cast_MultiT, OptMultiT, cast_OptMultiT
from ...technology import (
    property_ as _prp,  geometry as _geo, net as _net, primitive as _prm, technology_ as _tch,
)
from ...technology.primitive._param import _PrimParam

from ... import _util, dispatch as _dsp

from .layout_ import _MaskShapesSubLayout, LayoutT
# also imports at end of file to avoid circular import problems


def _rect(
    left: float, bottom: float, right: float, top: float, *,
    enclosure: Optional[Union[float, Sequence[float], _prp.Enclosure]]=None,
) -> _geo.Rect:
    """undocumented deprecated function;
    see: https://gitlab.com/Chips4Makers/PDKMaster/-/issues/39
    """
    if enclosure is not None:
        if isinstance(enclosure, _prp.Enclosure):
            enclosure = enclosure.spec
        if isinstance(enclosure, (int, float)):
            left -= enclosure
            bottom -= enclosure
            right += enclosure
            top += enclosure
        else:
            left -= enclosure[0]
            bottom -= enclosure[1]
            right += enclosure[0]
            top += enclosure[1]

    return _geo.Rect(
        left=left, bottom=bottom, right=right, top=top,
    )


def _via_array(
    left: float, bottom: float, width: float, pitch: float, rows: int, columns: int,
):
    """undocumented deprecated function;
    see: https://gitlab.com/Chips4Makers/PDKMaster/-/issues/39
    """
    via = _geo.Rect.from_size(width=width, height=width)
    xy0 = _geo.Point(x=(left + 0.5*width), y=(bottom + 0.5*width))

    if (rows == 1) and (columns == 1):
        return via + xy0
    else:
        return _geo.ArrayShape(
            shape=via, offset0=xy0, rows=rows, columns=columns, pitch_x=pitch, pitch_y=pitch,
        )


class _LayoutParam(_PrimParam):
    """_LayoutParam is a param that can be specified when generating the layout of a
    technology primitive. This is also valid for non-device; e.g. for generating the
    layouts of a wire etc.
    """
    pass


class _IntLayoutParam(_LayoutParam):
    value_conv = None
    value_type = int
    value_type_str = "int"


class _BoolLayoutParam(_LayoutParam):
    value_conv = None
    value_type = bool
    value_type_str = "bool"


class _PrimitiveLayoutParam(_LayoutParam):
    value_conv = None
    value_type = _prm.PrimitiveT
    value_type_str = "Primitive"

    def __init__(self, *,
        primitive: _prm.PrimitiveT, name: str, allow_none=False, default=None,
        choices: OptMultiT[_prm.PrimitiveT]=None,
    ):
        self.choices = cast_OptMultiT(choices)

        super().__init__(
            primitive=primitive, name=name, allow_none=allow_none, default=default,
        )

    def cast(self, value):
        value = super().cast(value)
        if self.choices is not None:
            if not ((value is None) or (value in self.choices)):
                raise ValueError(
                    f"Param '{self.name}' value '{value}' is not one of the allowed values:\n"
                    f"    {self.choices}"
            )

        return value


class _PrimitivesLayoutParam(_LayoutParam):
    value_type_str = "iterable of '_Primitive'"

    def __init__(self, *,
        primitive: _prm.PrimitiveT, name: str,
        default: MultiT[_prm.PrimitiveT]=(),
        choices: OptMultiT[_prm.PrimitiveT]=None,
    ):
        self.choices = cast_OptMultiT(choices)
        super().__init__(
            primitive=primitive, name=name, allow_none=True,
            default=cast_MultiT(default),
        )

    def cast(self, value):
        err = (
            f"param '{self.name}' has to be a `_Primitive` or an iterable \n"
            "of type `_Primitive'"
        )

        def check_elem(elem):
            if not isinstance(elem, _prm.PrimitiveT):
                raise TypeError(err)
            if (self.choices is not None) and (elem not in self.choices):
                raise ValueError(
                    f"param '{elem.name}' is not one of {self.choices!r}"
                )
            return elem

        if value is None:
            value = self.default
        elif not _util.is_iterable(value):
            value = (check_elem(value),)
        else:
            value = tuple(check_elem(elem) for elem in value)
        return value


class _EnclosureLayoutParam(_LayoutParam):
    value_type = (_prp.Enclosure, float, Iterable[float])
    value_type_str = "'Enclosure'"

    def cast(self, value):
        if value is None:
            if hasattr(self, "default"):
                value = self.default
            elif not self.allow_none:
                raise TypeError(
                    f"'None' value not allowed for parameter '{self.name}'"
                )
        elif not (
            isinstance(value, _prp.Enclosure)
            or (value in ("wide", "tall"))
        ):
            try:
                value = _prp.Enclosure(value)
            except:
                raise TypeError(
                    f"value {repr(value)} can't be converted to an Enclosure object"
                )

        return value


class _EnclosuresLayoutParam(_LayoutParam):
    value_type_str = "iterable of 'Enclosure'"

    def __init__(self, *,
        primitive: _prm.PrimitiveT, name: str, allow_none=False, default=None, n: int,
    ):
        self.n = n
        super().__init__(
            primitive=primitive, name=name, allow_none=allow_none, default=default,
        )

    def cast(self, value):
        err = (
            f"param '{self.name}' has to be an enclosure value or an iterable \n"
            "of type 'Enclosure'"
        )
        if self.n > 0:
            err += f" with length {self.n}"

        if value is None:
            if hasattr(self, "default"):
                value = self.default
            elif not self.allow_none:
                raise TypeError(
                    f"'None' value not allowed for parameter '{self.name}'"
                )
        elif isinstance(value, _prp.Enclosure) or (value in ("wide", "tall")):
            value = max(self.n, 1)*(value,)
        elif not _util.is_iterable(value):
            try:
                value = (_prp.Enclosure(value),)
            except:
                raise TypeError(err)
            else:
                if self.n > 1: # Not needed for 0 or 1
                    value *= self.n
        else:
            try:
                value = tuple(
                    (None if elem is None
                     else elem if isinstance(elem, _prp.Enclosure) or (elem in ("wide", "tall"))
                     else _prp.Enclosure(elem)
                    ) for elem in value
                )
            except:
                raise TypeError(err)
            else:
                if self.n != 0:
                    if len(value) != self.n:
                        raise TypeError(err)
        return value


class _NetLayoutParam(_LayoutParam):
    value_type = _net.NetT
    value_type_str = "Net"


class _NetsLayoutParam(_LayoutParam):
    value_type_str = "iterable of 'NetT'"

    def __init__(self, *,
        primitive: _prm.PrimitiveT, name: str,
        default: MultiT[_net.NetT]=(),
    ):
        super().__init__(
            primitive=primitive, name=name, allow_none=True,
            default=cast_MultiT(default),
        )

    def cast(self, value):
        err = (
            f"param '{self.name}' has to be a `NetT` or an iterable \n"
            "of type `NetT'"
        )

        def check_elem(elem):
            # we assume None is always a valid value for a Net
            if (elem is not None) and not isinstance(elem, _net.NetT):
                raise TypeError(err)
            return elem

        if value is None:
            value = self.default
        elif not _util.is_iterable(value):
            value = (check_elem(value),)
        else:
            value = tuple(check_elem(elem) for elem in value)
        return value


class _LayoutParamCaster(_dsp.PrimitiveDispatcher):
    """Support class that will cast parameters given to _PrimitiveLayouter
    """
    def __call__(self, prim: _prm.PrimitiveT, **params: Any) -> Dict[str, Any]:
        return super().__call__(prim, **params)

    def cast_params(self, *,
        layout_params: MultiT[_LayoutParam], prim_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """cast parameters for a list of given layout parameters

        Arguments:
            layout_params: The list params specification
            prim_params: The parameters to cast.
                Params specified in layout_params will be removed from prim_params
        """
        layout_params = cast_MultiT(layout_params)
        return {
            param.name: param.cast(prim_params.pop(param.name, None))
            for param in layout_params
        }

    def _Primitive(self, prim: _prm.PrimitiveT, **params: Any) -> Dict[str, Any]:
        out = {}
        try:
            pin: _prm.Marker = prim.pin # type: ignore
        except AttributeError:
            pass
        else:
            out.update(self.cast_params(
                layout_params=_PrimitiveLayoutParam(
                    primitive=prim, name="pin", allow_none=True, choices=pin,
                ),
                prim_params=params,
            ))

        if len(prim.ports) > 0:
            try:
                portnets = params.pop("portnets")
            except KeyError:
                # Specifying nets is optional
                pass
            else:
                # If nets are specified all nets need to be specified
                portnames = {p.name for p in prim.ports}
                portnetnames = set(portnets.keys())
                if (
                    (portnames != portnetnames)
                    or (len(prim.ports) != len(portnets)) # Detect removal of doubles in set
                ):
                    raise ValueError(
                        f"Nets for ports {portnetnames} specified but prim '{prim.name}'"
                        f" has ports {portnames}"
                    )
                out["portnets"] = portnets

        if len(params) != 0:
            raise TypeError(
                f"primitive '{prim.name}' got unexpected parameter(s) "
                f"{tuple(params.keys())}"
            )

        return out

    def _DevicePrimitive(self, prim: _prm.DevicePrimitiveT, **params: Any) -> Dict[str, Any]:
        dev_params = prim.cast_params(params)

        super_params = super()._DevicePrimitive(prim=prim, **params)
        super_params.update(dev_params)

        return super_params

    def _WidthSpacePrimitive(self,
        prim: _prm.WidthSpacePrimitiveT, **params: Any,
    ) -> Dict[str, Any]:
        try:
            # width/height for Marker can be specified but it has no min_width attribute
            def_width = prim.min_width
        except AttributeError:
            assert params["width"] is not None
            assert params["height"] is not None
            def_width = -1.0 # Fake width
        ws_params = self.cast_params(
            layout_params=(
                _LayoutParam(primitive=prim, name="width", default=def_width),
                _LayoutParam(primitive=prim, name="height", default=def_width),
                _PrimitivesLayoutParam(
                    primitive=prim, name="extra", default=(),
                ),
                _NetsLayoutParam(
                    primitive=prim, name="extra_net", default=(),
                ),
                _EnclosuresLayoutParam(
                    primitive=prim, name="extra_enclosure", default=(), allow_none=True, n=0,
                )
            ),
            prim_params=params,
        )

        extra = ws_params["extra"]
        extra_net = ws_params["extra_net"]
        extra_enc = ws_params["extra_enclosure"]
        if extra:
            if not extra_net:
                ws_params["extra_net"] = len(extra)*(None,)
            else:
                if len(extra) > 1:
                    if len(extra_net) == 1:
                        ws_params["extra_net"] = len(extra)*extra_net
                    elif len(extra) != len(extra_net):
                        raise ValueError(
                            f"Number of extra nets '{len(extra_enc)}' != "
                            f"number of extra layers '{len(extra)}'"
                        )
            if not extra_enc:
                ws_params["extra_enclosure"] = len(extra)*(None,)
            else:
                if len(extra) > 1:
                    if len(extra_enc) == 1:
                        ws_params["extra_enclosure"] = len(extra)*extra_enc
                    elif len(extra) != len(extra_enc):
                        raise ValueError(
                            f"Number of extra enclosures '{len(extra_enc)}' != "
                            f"number of extra layers '{len(extra)}'"
                        )

        super_params = super()._WidthSpacePrimitive(prim=prim, **params)
        super_params.update(ws_params)

        return super_params

    def Marker(self, prim: _prm.Marker, **params: Any) -> Dict[str, Any]:
        marker_params = self.cast_params(
            layout_params=(
               _LayoutParam(primitive=prim, name="width", allow_none=True),
               _LayoutParam(primitive=prim, name="height", allow_none=True),
            ),
            prim_params=params,
        )
        if (marker_params["width"] is not None) and (marker_params["height"] is not None):
            params.update(marker_params) # Re-add the arguments
            return self._WidthSpacePrimitive(
                cast(_prm.WidthSpacePrimitiveT, prim), **params)
        else:
            super_params = super().Marker(prim, **params)
        super_params.update(marker_params)

        return super_params

    def WaferWire(self, prim: _prm.WaferWire, **params) -> Dict[str, Any]:
        layparams = []
        ww_params = {}

        layparams.extend((
            _PrimitivesLayoutParam(
                primitive=prim, name="implant", choices=prim.implant,
                default=(),
            ),
            _EnclosuresLayoutParam(
                primitive=prim, name="implant_enclosure", default=(), allow_none=True, n=0,
            ),
        ))
        if (len(prim.well) > 1) or prim.allow_in_substrate:
            layparams.extend((
                _PrimitiveLayoutParam(
                    primitive=prim, name="well", allow_none=prim.allow_in_substrate,
                    choices=prim.well
                ),
                _EnclosureLayoutParam(
                    primitive=prim, name="well_enclosure", allow_none=True,
                ),
            ))
        else:
            ww_params["well"] = prim.well[0]
            layparams.append(
                _EnclosureLayoutParam(
                    primitive=prim, name="well_enclosure", default=prim.min_well_enclosure[0],
                ),
            )
        layparams.append(_NetLayoutParam(
            primitive=prim, name="well_net", allow_none=prim.allow_in_substrate,
        ))
        if prim.oxide:
            layparams.extend((
                _PrimitiveLayoutParam(
                    primitive=prim, name="oxide", choices=prim.oxide, allow_none=True,
                ),
                _EnclosureLayoutParam(
                    primitive=prim, name="oxide_enclosure", allow_none=True,
                ),
            ))
        ww_params.update(self.cast_params(layout_params=layparams, prim_params=params))

        implant = ww_params["implant"]
        enclosure = ww_params["implant_enclosure"]
        if len(implant) != len(enclosure):
            if len(implant) == 0:
                raise TypeError(
                    f"Enclusore specified without an implant layer for WaferWire `{prim.name}`"
                )
            elif len(enclosure) == 0:
                # Use minimum enclosure for all implants
                enclosure = len(implant)*(None,)
            elif len(enclosure) == 1:
                enclosure = len(implant)*enclosure
            else:
                raise ValueError(
                    f"Parameter number mismatch for WaferWire `{prim.name}`\n"
                    f"{len(implant)} implant layers and {len(enclosure)} enclosures"
                )
        # Replace None enclosure values with minimal enclosure values
        assert len(implant) == len(enclosure), "Internal error"
        def min_enc(impl, enc):
            if (enc is None) or enc in ("wide", "tall"):
                idx = prim.implant.index(impl)
                if enc is None:
                    enc = prim.min_implant_enclosure[idx]
                elif enc == "wide":
                    enc = prim.min_implant_enclosure[idx].wide()
                elif enc == "tall":
                    enc = prim.min_implant_enclosure[idx].tall()
                else: # pragma: no cover
                    assert False, "Internal error"
            return enc
        enclosure = tuple(min_enc(implant[i], enc) for i, enc in enumerate(enclosure))
        ww_params["implant"] = implant
        ww_params["implant_enclosure"] = enclosure

        well = cast(_prm.Well, ww_params["well"])
        enclosure = ww_params["well_enclosure"]
        well_net = ww_params["well_net"]
        if well is not None:
            if "portnets" in params:
                net = params["portnets"]["conn"]
            else:
                net = prim.ports["conn"]
            for main_impl in implant:
                if main_impl.type_ in (_prm.nImpl, _prm.pImpl):
                    break
            else:
                main_impl = None
            if well_net is None:
                if (
                    (main_impl is not None)
                    and (main_impl.type_ == well.type_)
                ):
                    ww_params["well_net"] = net
                else:
                    raise TypeError("well_net needs to be provided if well is specified")
            else:
                if (
                    (main_impl is not None) and (main_impl.type_ == well.type_)
                    and (net != well_net)
                ):
                    raise ValueError(
                        f"Net '{well_net}' for well '{well.name}' of WaferWire"
                        f" {prim.name} is different from net '{net}''\n"
                        f"\tbut implant '{main_impl.name}' have same type as the well"
                    )

            if enclosure is None:
                idx = prim.well.index(well)
                ww_params["well_enclosure"] = prim.min_well_enclosure[idx]

        if ("oxide" in ww_params):
            oxide = ww_params["oxide"]
            if oxide is not None:
                oxide_enclosure = ww_params["oxide_enclosure"]
                if oxide_enclosure is None:
                    idx = prim.oxide.index(oxide)
                    ww_params["oxide_enclosure"] = prim.min_oxide_enclosure[idx]

        super_params = super().WaferWire(prim, **params)
        super_params.update(ww_params)

        return super_params

    def Via(self, prim, **params) -> Dict[str, Any]:
        layparams = [
            _LayoutParam(primitive=prim, name="space", default=prim.min_space),
            _IntLayoutParam(primitive=prim, name="rows", allow_none=True),
            _IntLayoutParam(primitive=prim, name="columns", allow_none=True),
            _EnclosureLayoutParam(primitive=prim, name="bottom_enclosure", allow_none=True),
            _LayoutParam(primitive=prim, name="bottom_width", allow_none=True),
            _LayoutParam(primitive=prim, name="bottom_height", allow_none=True),
            _PrimitivesLayoutParam(primitive=prim, name="bottom_extra"),
            _NetsLayoutParam(primitive=prim, name="bottom_extra_net"),
            _EnclosuresLayoutParam(
                primitive=prim, name="bottom_extra_enclosure", allow_none=True, default=(), n=0,
            ),
            _EnclosureLayoutParam(primitive=prim, name="top_enclosure", allow_none=True),
            _LayoutParam(primitive=prim, name="top_width", allow_none=True),
            _LayoutParam(primitive=prim, name="top_height", allow_none=True),
            _PrimitivesLayoutParam(primitive=prim, name="top_extra"),
            _NetsLayoutParam(primitive=prim, name="top_extra_net"),
            _EnclosuresLayoutParam(
                primitive=prim, name="top_extra_enclosure", allow_none=True, default=(), n=0,
            ),
        ]
        via_params = {}

        if len(prim.bottom) > 1:
            default = prim.bottom[0]
            if not isinstance(default, _prm.MetalWire) or isinstance(default, _prm.MIMTop):
                default = None
            layparams.append(_PrimitiveLayoutParam(
                primitive=prim, name="bottom", default=default, choices=prim.bottom,
            ))
        else:
            via_params["bottom"] = prim.bottom[0]

        choices = sum(
            (cast(_prm.WaferWire, wire).implant for wire in filter(
                lambda w: isinstance(w, _prm.WaferWire),
                prim.bottom,
            )),
            tuple(),
        )
        layparams.extend((
            _PrimitivesLayoutParam(
                primitive=prim, name="bottom_implant", choices=choices,
            ),
            _EnclosuresLayoutParam(
                primitive=prim, name="bottom_implant_enclosure", default=(), allow_none=True, n=0,
            ),
            _PrimitiveLayoutParam(primitive=prim, name="bottom_well", allow_none=True),
            _NetLayoutParam(primitive=prim, name="well_net", allow_none=True),
            _EnclosureLayoutParam(
                primitive=prim, name="bottom_well_enclosure", allow_none=True,
            ),
        ))

        choices = sum(
            (
                cast(_prm.WaferWire, wire).oxide
                for wire in filter(
                    lambda w: isinstance(w, _prm.WaferWire),
                    prim.bottom,
                )
            ),
            tuple(),
        )
        if choices:
            layparams.extend((
                _PrimitiveLayoutParam(
                    primitive=prim, name="bottom_oxide", allow_none=True, choices=choices,
                ),
                _EnclosureLayoutParam(
                    primitive=prim, name="bottom_oxide_enclosure", allow_none=True,
                ),
            ))

        if len(prim.top) > 1:
            default = prim.top[0]
            assert isinstance(default, _prm.MetalWire), "Not implemented"
            layparams.append(_PrimitiveLayoutParam(
                primitive=prim, name="top", default=default, choices=prim.top,
            ))
        else:
            via_params["top"] = prim.top[0]

        via_params.update(self.cast_params(layout_params=layparams, prim_params=params))

        super_params = super().Via(prim, **params)
        super_params.update(via_params)

        bottom = super_params["bottom"]
        if not isinstance(bottom, _prm.WaferWire):
            for param, value in (
                ("bottom_implant", ()),
                ("bottom_implant_enclosure", ()),
                ("bottom_well", None),
                ("bottom_well_enclosure", None),
                ("well_net", None),
            ):
                if super_params[param] != value:
                    raise TypeError(
                        f"param '{param}' not valid for bottom '{bottom.name}'"
                    )

        return super_params

    def MIMCapacitor(self, prim: _prm.MIMCapacitor, **params) -> Dict[str, Any]:
        mim_params = self.cast_params(
            layout_params=_BoolLayoutParam(
                primitive=prim, name="bottom_connect_up", default=True,
            ),
            prim_params=params,
        )

        super_params = super().MIMCapacitor(prim, **params)
        super_params.update(mim_params)

        return super_params

    def Diode(self, prim: _prm.Diode, **params) -> Dict[str, Any]:
        if prim.implant:
            layparams = [
                _EnclosuresLayoutParam(
                    primitive=prim, name="implant_enclosure", n=len(prim.implant),
                    default=prim.min_implant_enclosure,
                ),
            ]
            dio_params = self.cast_params(layout_params=layparams, prim_params=params)
        else:
            dio_params = {}

        super_params = super().Diode(prim, **params)
        super_params.update(dio_params)

        return super_params

    def MOSFET(self, prim: _prm.MOSFET, **params) -> Dict[str, Any]:
        impl_act_enc = None
        for impl in prim.implant:
            try:
                idx = prim.gate.active.implant.index(impl)
            except: # pragma: no cover
                continue
            else:
                impl_act_enc = prim.gate.active.min_implant_enclosure[idx]
                break

        layparams = [
            _LayoutParam(
                primitive=prim, name="sd_width", default=prim.computed.min_sd_width),
            _LayoutParam(
                primitive=prim, name="polyactive_extension",
                default=prim.computed.min_polyactive_extension,
            ),
            _EnclosuresLayoutParam(
                primitive=prim, name="gateimplant_enclosures", n=len(prim.implant),
                default=prim.min_gateimplant_enclosure,
            ),
        ]
        if impl_act_enc is not None:
            layparams.append(_EnclosureLayoutParam(
                primitive=prim, name="activeimplant_enclosure",
                default=impl_act_enc,
            ))
        spc = prim.computed.min_gate_space
        if spc is not None:
            layparams.append(
                _LayoutParam(primitive=prim, name="gate_space", default=spc)
            )

        if prim.computed.contact is not None:
            spc = prim.computed.min_contactgate_space
            assert spc is not None
            layparams.append(
                _LayoutParam(primitive=prim, name="contactgate_space", default=spc)
            )
        mos_params = self.cast_params(layout_params=layparams, prim_params=params)

        super_params = super().MOSFET(prim, **params)
        super_params.update(mos_params)

        return super_params


class _PrimitiveLayouter(_dsp.PrimitiveDispatcher):
    """Support class to generate layout for a `_Primitive`.

    TODO: Proper docs after fixing the API.
    see https://gitlab.com/Chips4Makers/PDKMaster/-/issues/25

    API Notes:
        The API is not finalized yet; backwards incompatible changes are still
            expected.
    """
    def __init__(self, fab: "LayoutFactory", create_cb: Optional[Callable]):
        self.fab = fab
        self.create_cb = create_cb
        self._caster = _LayoutParamCaster()

    def __call__(self, prim: _prm.PrimitiveT, **prim_params) -> LayoutT:
        lay = super().__call__(prim, **self._caster(prim, **prim_params))
        if self.create_cb is not None:
            self.create_cb(layout=lay, prim=prim, **prim_params)
        return lay

    @property
    def tech(self) -> _tch.Technology:
        return self.fab.tech

    # Dispatcher implementation
    def _Primitive(self, prim: _prm.PrimitiveT, **params) -> LayoutT:
        raise NotImplementedError(
            f"Don't know how to generate minimal layout for primitive '{prim.name}'\n"
            f"of type '{prim.__class__.__name__}'"
        )

    def Marker(self, prim: _prm.Marker, **params) -> LayoutT:
        if (params["width"] is not None) and (params["height"] is not None):
            return self._WidthSpacePrimitive(cast(_prm.WidthSpacePrimitiveT, prim), **params)
        else:
            return super().Marker(prim, **params)

    def _WidthSpacePrimitive(self,
        prim: _prm.WidthSpacePrimitiveT, net=None, **widthspace_params,
    ) -> LayoutT:
        width = widthspace_params["width"]
        height = widthspace_params["height"]
        r = _geo.Rect.from_size(width=width, height=height)

        extra = widthspace_params.pop("extra")
        extra_net = widthspace_params.pop("extra_net")
        extra_enclosure = widthspace_params.pop("extra_enclosure")

        l = self.fab.new_layout()
        assert isinstance(prim, _prm.DesignMaskPrimitiveT)
        l.add_shape(layer=prim, net=net, shape=r)
        for i, ex in enumerate(extra):
            assert ex is not None
            l.add_shape(layer=ex, net=extra_net[i], shape=_rect(
                -0.5*width, -0.5*height, 0.5*width, 0.5*height,
                enclosure=extra_enclosure[i],
            ))

        return l

    def _WidthSpaceConductor(self,
        prim: _prm.WidthSpaceConductorT, **conductor_params,
    ) -> LayoutT:
        assert (
            (len(prim.ports) == 1) and (prim.ports[0].name == "conn")
        ), "Internal error"
        try:
            portnets = conductor_params["portnets"]
        except KeyError:
            net = prim.ports.conn
        else:
            net = portnets["conn"]

        pin = conductor_params.pop("pin", None)
        if pin is not None:
            conductor_params["extra"] += (pin,)
            conductor_params["extra_net"] += (net,)
            conductor_params["extra_enclosure"] += (None,)

        return self._WidthSpacePrimitive(prim=prim, net=net, **conductor_params)

    def WaferWire(self, prim: _prm.WaferWire, **waferwire_params) -> LayoutT:
        implant = waferwire_params.pop("implant")
        implant_enclosure = waferwire_params.pop("implant_enclosure")
        add_extra = implant
        add_extra_net = len(implant)*(None,)
        add_extra_enc = implant_enclosure

        well = waferwire_params.pop("well", None)
        well_enclosure = waferwire_params.pop("well_enclosure", None)
        if well is not None:
            well_net = waferwire_params["well_net"]
            assert well_net is not None, "Internal error"
            add_extra += (well,)
            add_extra_net += (well_net,)
            add_extra_enc += (well_enclosure,)

        oxide = waferwire_params.pop("oxide", None)
        oxide_enclosure = waferwire_params.pop("oxide_enclosure", None)
        if oxide is not None:
            add_extra += (oxide,)
            add_extra_net += (None,)
            add_extra_enc += (oxide_enclosure,)

        waferwire_params["extra"] += add_extra
        waferwire_params["extra_net"] += add_extra_net
        waferwire_params["extra_enclosure"] += add_extra_enc

        return self._WidthSpaceConductor(prim, **waferwire_params)

    def Via(self, prim: _prm.Via, **via_params) -> LayoutT:
        tech = self.tech

        try:
            portnets = via_params["portnets"]
        except KeyError:
            net = prim.ports["conn"]
        else:
            net = portnets["conn"]

        bottom = via_params["bottom"]
        bottom_enc = via_params["bottom_enclosure"]
        if (bottom_enc is None) or isinstance(bottom_enc, str):
            idx = prim.bottom.index(bottom)
            enc = prim.min_bottom_enclosure[idx]
            if bottom_enc is None:
                bottom_enc = enc
            elif bottom_enc == "wide":
                bottom_enc = enc.wide()
            else:
                assert bottom_enc == "tall"
                bottom_enc = enc.tall()
        assert isinstance(bottom_enc, _prp.Enclosure)
        bottom_enc_x = bottom_enc.spec[0]
        bottom_enc_y = bottom_enc.spec[1]

        top = via_params["top"]
        top_enc = via_params["top_enclosure"]
        if (top_enc is None) or isinstance(top_enc, str):
            idx = prim.top.index(top)
            enc = prim.min_top_enclosure[idx]
            if top_enc is None:
                top_enc = enc
            elif top_enc == "wide":
                top_enc = enc.wide()
            else:
                assert top_enc == "tall"
                top_enc = enc.tall()
        assert isinstance(top_enc, _prp.Enclosure)
        top_enc_x = top_enc.spec[0]
        top_enc_y = top_enc.spec[1]

        width = prim.width
        space = via_params["space"]
        pitch = width + space

        rows = via_params["rows"]
        bottom_height = via_params["bottom_height"]
        top_height = via_params["top_height"]
        if (rows is None) and (bottom_height is None) and (top_height is None):
            rows = 1
        if rows is None:
            if bottom_height is None:
                assert top_height is not None
                rows = int(self.tech.on_grid(top_height - 2*top_enc_y - width)//pitch + 1)
                via_height = rows*pitch - space
                bottom_height = tech.on_grid(
                    via_height + 2*bottom_enc_y, mult=2, rounding="ceiling",
                )
            else:
                rows = int(self.tech.on_grid(bottom_height - 2*bottom_enc_y - width)//pitch + 1)
                if top_height is not None:
                    rows = min(
                        rows,
                        int(self.tech.on_grid(top_height - 2*top_enc_y - width)//pitch + 1),
                    )
                via_height = rows*pitch - space
                if top_height is None:
                    top_height = tech.on_grid(
                        via_height + 2*top_enc_y, mult=2, rounding="ceiling",
                    )
        else:
            assert (bottom_height is None) and (top_height is None)
            via_height = rows*pitch - space
            bottom_height = tech.on_grid(
                via_height + 2*bottom_enc_y, mult=2, rounding="ceiling",
            )
            top_height = tech.on_grid(
                via_height + 2*top_enc_y, mult=2, rounding="ceiling",
            )

        columns = via_params["columns"]
        bottom_width = via_params["bottom_width"]
        top_width = via_params["top_width"]
        if (columns is None) and (bottom_width is None) and (top_width is None):
            columns = 1
        if columns is None:
            if bottom_width is None:
                assert top_width is not None
                columns = int(self.tech.on_grid(top_width - 2*top_enc_x - width)//pitch + 1)
                via_width = columns*pitch - space
                bottom_width = tech.on_grid(
                    via_width + 2*bottom_enc_x, mult=2, rounding="ceiling",
                )
            else:
                columns = int(self.tech.on_grid(bottom_width - 2*bottom_enc_x - width)//pitch + 1)
                if top_width is not None:
                    columns = min(
                        columns,
                        int(self.tech.on_grid(top_width - 2*top_enc_x - width)//pitch + 1)
                    )
                via_width = columns*pitch - space
                if top_width is None:
                    top_width = tech.on_grid(
                        via_width + 2*top_enc_x, mult=2, rounding="ceiling",
                    )
        else:
            assert (bottom_width is None) and (top_width is None)
            via_width = columns*pitch - space
            bottom_width = tech.on_grid(
                via_width + 2*bottom_enc_x, mult=2, rounding="ceiling",
            )
            top_width = tech.on_grid(
                via_width + 2*top_enc_x, mult=2, rounding="ceiling",
            )

        bottom_left = tech.on_grid(-0.5*bottom_width, rounding="floor")
        bottom_bottom = tech.on_grid(-0.5*bottom_height, rounding="floor")
        bottom_right = bottom_left + bottom_width
        bottom_top = bottom_bottom + bottom_height
        bottom_rect = _geo.Rect(
            left=bottom_left, bottom=bottom_bottom,
            right=bottom_right, top=bottom_top,
        )

        top_left = tech.on_grid(-0.5*top_width, rounding="floor")
        top_bottom = tech.on_grid(-0.5*top_height, rounding="floor")
        top_right = top_left + top_width
        top_top = top_bottom + top_height
        top_rect = _geo.Rect(
            left=top_left, bottom=top_bottom,
            right=top_right, top=top_top,
        )

        via_bottom = tech.on_grid(-0.5*via_height)
        via_left = tech.on_grid(-0.5*via_width)

        layout = self.fab.new_layout()

        if isinstance(bottom, _prm.WaferWire):
            bottom_args = {
                param: via_params[f"bottom_{param}"]
                for param in (
                    "implant", "implant_enclosure",
                    "oxide", "oxide_enclosure",
                    "well", "well_enclosure",
                )
            }
            bottom_args["well_net"] = via_params["well_net"]
        else:
            bottom_args = {}
        layout.add_primitive(
            prim=bottom, portnets={"conn": net}, origin=bottom_rect.center,
            extra=via_params["bottom_extra"], extra_net=via_params["bottom_extra_net"],
            extra_enclosure=via_params["bottom_extra_enclosure"],
            width=bottom_rect.width, height=bottom_rect.height,
            **bottom_args,
        )
        layout.add_shape(layer=prim, net=net, shape=_via_array(
            via_left, via_bottom, width, pitch, rows, columns,
        ))
        layout.add_primitive(
            prim=top, portnets={"conn": net}, origin=top_rect.center,
            extra=via_params["top_extra"], extra_net=via_params["top_extra_net"],
            extra_enclosure=via_params["top_extra_enclosure"],
            width=top_rect.width, height=top_rect.height,
        )

        return layout

    def DeepWell(self, prim: _prm.DeepWell, **deepwell_params) -> LayoutT:
        raise NotImplementedError("layout generation for DeepWell primitive")

    def Resistor(self, prim: _prm.Resistor, **resistor_params) -> LayoutT:
        try:
            portnets = resistor_params["portnets"]
        except KeyError:
            port1 = prim.ports.port1
            port2 = prim.ports.port2
        else:
            port1 = portnets["port1"]
            port2 = portnets["port2"]
        if prim.contact is None:
            raise NotImplementedError("Resistor layout without contact layer")

        res_width = cast(float, resistor_params["width"])
        res_length = cast(float, resistor_params["length"])

        wire = prim.wire

        cont = prim.contact
        cont_space = prim.min_contact_space
        assert cont_space is not None
        try:
            wire_idx = cont.bottom.index(wire)
        except ValueError: # pragma: no cover
            raise NotImplementedError("Resistor connected from the bottom")
            try:
                wire_idx = cont.top.index(wire)
            except ValueError:
                raise AssertionError("Internal error")
            else:
                cont_enc = cont.min_top_enclosure[wire_idx]
                cont_args = {"top": wire, "x": 0.0, "top_width": res_width}
        else:
            cont_enc = cont.min_bottom_enclosure[wire_idx]
            cont_args = {"bottom": wire, "x": 0.0, "bottom_width": res_width}
        cont_y1 = -0.5*res_length - cont_space - 0.5*cont.width
        cont_y2 = -cont_y1

        wire_ext = cont_space + cont.width + cont_enc.max()

        layout = self.fab.new_layout()

        # Draw indicator layers
        for idx, ind in enumerate(prim.indicator):
            ext = prim.min_indicator_extension[idx]
            layout += self(ind, width=(res_width + 2*ext), height=res_length)

        # Draw wire layer
        mp = _geo.MultiPartShape(
            fullshape=_geo.Rect.from_size(
                width=res_width, height=(res_length + 2*wire_ext),
            ),
            parts = (
                _geo.Rect.from_floats(values=(
                    -0.5*res_width, -0.5*res_length - wire_ext,
                    0.5*res_width, -0.5*res_length,
                )),
                _geo.Rect.from_floats(values=(
                    -0.5*res_width, -0.5*res_length,
                    0.5*res_width, 0.5*res_length,
                )),
                _geo.Rect.from_floats(values=(
                    -0.5*res_width, 0.5*res_length,
                    0.5*res_width, 0.5*res_length + wire_ext,
                )),
            )
        )
        layout.add_shape(layer=wire, net=port1, shape=mp.parts[0])
        layout.add_shape(layer=wire, net=None, shape=mp.parts[1])
        layout.add_shape(layer=wire, net=port2, shape=mp.parts[2])

        # Draw contacts
        # Hack to make sure the bottom wire does not overlap with the resistor part
        # TODO: Should be fixed in MultiPartShape handling
        # layout.add_wire(net=port1, wire=cont, y=cont_y1, **cont_args)
        # layout.add_wire(net=port2, wire=cont, y=cont_y2, **cont_args)
        x = cont_args.pop("x")
        _l_cont = self.fab.layout_primitive(
            prim=cont, portnets={"conn": port1}, **cont_args
        )
        _l_cont.move(dxy=_geo.Point(x=x, y=cont_y1))
        for sl in _l_cont._sublayouts:
            if isinstance(sl, _MaskShapesSubLayout):
                for msl in sl.shapes:
                    if msl.mask == wire.mask:
                        assert isinstance(msl.shape, _geo.Rect)
                        msl._shape = _geo.Rect.from_rect(
                            rect=msl.shape, top=(-0.5*res_length - self.tech.grid)
                        )
        layout += _l_cont
        _l_cont = self.fab.layout_primitive(
            prim=cont, portnets={"conn": port2}, **cont_args
        )
        _l_cont.move(dxy=_geo.Point(x=x, y=cont_y2))
        for sl in _l_cont._sublayouts:
            if isinstance(sl, _MaskShapesSubLayout):
                for msl in sl.shapes:
                    if msl.mask == wire.mask:
                        assert isinstance(msl.shape, _geo.Rect)
                        msl._shape = _geo.Rect.from_rect(
                            rect=msl.shape, bottom=(0.5*res_length + self.tech.grid)
                        )
        layout += _l_cont

        for i, impl in enumerate(prim.implant):
            enc = prim.min_implant_enclosure[i]
            impl_width = res_width + 2*enc.first
            impl_height = res_length + 2*wire_ext + 2*enc.second
            layout.add_shape(
                layer=impl, net=None, shape=_geo.Rect.from_size(width=impl_width, height=impl_height),
            )

        return layout

    def MIMCapacitor(self, prim: _prm.MIMCapacitor, **mimcapargs) -> LayoutT:
        try:
            portnets = mimcapargs.pop("portnets")
        except KeyError:
            top = prim.ports.top
            bottom = prim.ports.bottom
        else:
            top = portnets["top"]
            bottom = portnets["bottom"]

        via = prim.via

        # Params
        top_width: float = mimcapargs["width"]
        top_height: float = mimcapargs["height"]
        connect_up = mimcapargs["bottom_connect_up"]

        # TODO: Allow to specify top of the via layer
        upper_metal = via.top[0]
        assert isinstance(upper_metal, _prm.MetalWire)
        assert upper_metal.pin is not None
        upper_pin: _prm.Marker = upper_metal.pin

        # Compute dimensions
        bottomvia_outerbound: Optional[_geo.ShapeT] = None
        bottomupper_outerwidth: Optional[float] = None
        bottomupper_outerheight: Optional[float] = None
        bottomupper_ringwidth: Optional[float] = None
        if connect_up:
            bottomvia_outerwidth = (
                top_width + 2*prim.min_bottomvia_top_space + 2*via.width
            )
            bottomvia_outerheight = (
                top_height + 2*prim.min_bottomvia_top_space + 2*via.width
            )
            bottomvia_outerbound = _geo.Rect.from_size(
                width=bottomvia_outerwidth, height=bottomvia_outerheight,
            )

            idx = via.bottom.index(prim.bottom)
            enc = via.min_bottom_enclosure[idx].max()
            bottom_width = bottomvia_outerwidth + 2*enc
            bottom_height = bottomvia_outerheight + 2*enc

            enc = via.min_top_enclosure[0].max()
            bottomupper_outerwidth = bottomvia_outerwidth + 2*enc
            bottomupper_outerheight = bottomvia_outerheight + 2*enc
            bottomupper_ringwidth = via.width + 2*enc

            topupper_width = (
                bottomupper_outerwidth - 2*bottomupper_ringwidth - 2*upper_metal.min_space
            )
            topupper_height = (
                bottomupper_outerheight - 2*bottomupper_ringwidth - 2*upper_metal.min_space
            )
        else:
            enc = prim.min_bottom_top_enclosure.max()
            bottom_width = top_width + 2*enc
            bottom_height = top_height + 2*enc

            topupper_width = None
            topupper_height = None

        # Draw the shapes
        layout = self.fab.new_layout()
        via_lay = layout.add_primitive(
            prim=via, bottom=prim.top, portnets={"conn": top},
            bottom_width=top_width, bottom_height=top_height,
            top_width=topupper_width, top_height=topupper_height,
            bottom_enclosure=prim.min_top_via_enclosure,
        )
        via_upmbb = via_lay.bounds(mask=upper_metal.mask)
        layout.add_shape(layer=upper_pin, net=top, shape=via_upmbb)

        shape = _geo.Rect.from_size(width=bottom_width, height=bottom_height)
        layout.add_shape(layer=prim.bottom, net=bottom, shape=shape)

        if connect_up:
            assert bottomvia_outerbound is not None
            assert bottomupper_outerwidth is not None
            assert bottomupper_outerheight is not None
            assert bottomupper_ringwidth is not None

            shape = _geo.RectRing(
                outer_bound=bottomvia_outerbound,
                rect_width=via.width, min_rect_space=via.min_space,
            )
            layout.add_shape(layer=via, net=bottom, shape=shape)

            shape = _geo.Ring(
                outer_bound=_geo.Rect.from_size(
                    width=bottomupper_outerwidth, height=bottomupper_outerheight,
                ),
                ring_width=bottomupper_ringwidth,
            )
            layout.add_shape(layer=upper_metal, net=bottom, shape=shape)
            layout.add_shape(layer=upper_pin, net=bottom, shape=shape)

        bottom_space = (
            prim.min_bottom_space
            if prim.min_bottom_space is not None
            else 0.0
        )
        layout.boundary = _geo.Rect.from_size(
            width=(bottom_width + bottom_space),
            height=(bottom_height + bottom_space),
        )

        return layout

    def Diode(self, prim: _prm.Diode, **diode_params) -> LayoutT:
        try:
            portnets = diode_params.pop("portnets")
        except KeyError:
            an = prim.ports.anode
            cath = prim.ports.cathode
        else:
            an = portnets["anode"]
            cath = portnets["cathode"]

        is_p = any(impl.type_ == _prm.pImpl for impl in prim.implant)

        wirenet_args: Dict[str, Any] = {
            "implant": prim.implant,
            "portnets": {"conn": an if is_p else cath},
        }
        if prim.well is not None:
            wirenet_args.update({
                "well": prim.well,
                "well_net": cath if is_p else an,
            })

        layout = self.fab.new_layout()
        layout.add_primitive(
            prim=prim.wire, extra=prim.indicator, extra_enclosure=prim.min_indicator_enclosure,
            **wirenet_args, **diode_params,
        )

        return layout

    def MOSFET(self, prim: _prm.MOSFET, **mos_params) -> LayoutT:
        l = mos_params["l"]
        w = mos_params["w"]
        gate_encs = mos_params["gateimplant_enclosures"]
        sdw = mos_params["sd_width"]

        try:
            portnets = cast(Mapping[str, _net.NetT], mos_params["portnets"])
        except KeyError:
            portnets = prim.ports

        gate_left = -0.5*l
        gate_right = 0.5*l
        gate_top = 0.5*w
        gate_bottom = -0.5*w

        layout = self.fab.new_layout()

        active = prim.gate.active
        active_width = l + 2*sdw
        active_left = -0.5*active_width
        active_right = 0.5*active_width
        active_bottom = gate_bottom
        active_top = gate_top

        mps = _geo.MultiPartShape(
            fullshape=_geo.Rect.from_size(width=active_width, height=w),
            parts=(
                _geo.Rect(
                    left=active_left, bottom=active_bottom,
                    right=gate_left, top=active_top,
                ),
                _geo.Rect(
                    left=gate_left, bottom =active_bottom,
                    right=gate_right, top=active_top,
                ),
                _geo.Rect(
                    left=gate_right, bottom =active_bottom,
                    right=active_right, top=active_top,
                ),
            )
        )
        layout.add_shape(layer=active, net=portnets["sourcedrain1"], shape=mps.parts[0])
        layout.add_shape(layer=active, net=portnets["bulk"], shape=mps.parts[1])
        layout.add_shape(layer=active, net=portnets["sourcedrain2"], shape=mps.parts[2])

        if len(prim.implant) > 0:
            impl_enc = mos_params["activeimplant_enclosure"]
            for impl in prim.implant:
                if impl in active.implant:
                    layout.add_shape(layer=impl, net=None, shape=_rect(
                        active_left, active_bottom, active_right, active_top,
                        enclosure=impl_enc
                    ))

        poly = prim.gate.poly
        ext = prim.computed.min_polyactive_extension
        poly_left = gate_left
        poly_bottom = gate_bottom - ext
        poly_right = gate_right
        poly_top = gate_top + ext
        layout.add_shape(layer=poly, net=portnets["gate"], shape=_geo.Rect(
            left=poly_left, bottom=poly_bottom, right=poly_right, top=poly_top,
        ))

        if prim.well is not None:
            enc = active.min_well_enclosure[active.well.index(prim.well)]
            layout.add_shape(layer=prim.well, net=portnets["bulk"], shape=_rect(
                active_left, active_bottom, active_right, active_top, enclosure=enc,
            ))

        oxide = prim.gate.oxide
        if oxide is not None:
            enc = getattr(
                prim.gate, "min_gateoxide_enclosure", _prp.Enclosure(self.tech.grid),
            )
            layout.add_shape(layer=oxide, net=None, shape=_rect(
                gate_left, gate_bottom, gate_right, gate_top, enclosure=enc,
            ))
            idx = active.oxide.index(oxide)
            enc = active.min_oxide_enclosure[idx]
            if enc is not None:
                layout.add_shape(layer=oxide, net=None, shape=_rect(
                    active_left, active_bottom, active_right, active_top,
                    enclosure=enc,
                ))
        if prim.gate.inside is not None:
            # TODO: Check is there is an enclosure rule from oxide around active
            # and apply the if so.
            for i, inside in enumerate(prim.gate.inside):
                enc = (
                    prim.gate.min_gateinside_enclosure[i]
                    if prim.gate.min_gateinside_enclosure is not None
                    else _prp.Enclosure(self.tech.grid)
                )
                layout.add_shape(layer=inside, net=None, shape=_rect(
                    gate_left, gate_bottom, gate_right, gate_top, enclosure=enc,
                ))
        for i, impl in enumerate(prim.implant):
            enc = gate_encs[i]
            layout.add_shape(layer=impl, net=None, shape=_rect(
                gate_left, gate_bottom, gate_right, gate_top, enclosure=enc,
            ))

        return layout

    def Bipolar(self, prim: _prm.Bipolar, **deepwell_params) -> LayoutT:
        # Currently it is assumed that fixed layouts are provided by the
        # technology
        raise NotImplementedError("layout generation for Bipolar primitive")


# import at end of file to avoid circular import problems
from .factory_ import LayoutFactory
