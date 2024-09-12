# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from itertools import product
from typing import List, Tuple, Dict, Optional, Any, cast
import pya

from pdkmaster import typing as _typ
from pdkmaster.technology import geometry as _geo, property_ as _prp, primitive as _prm
from pdkmaster.design import circuit as _ckt, layout as _lay
from pdkmaster.dispatch import PrimitiveDispatcher

from .export import export2db


__all__ = ["PCellLibrary"]


# Some notes about use of pya.PCellDeclarationHelper
# Internal klayout code does not seem to like it when assigning value to field with names
# other than a parameter name. It seems to be OK if it happens in __init__() so for the
# moment we will use a vals dict to store values.
# When a parameter is defined the type of the field (e.g. obj.param) varies between
# different methods. In such case the type of the parameter may need to be defined as Any.

# Currently the types in PCellDeclarationHelper are not annotated
_TypeDouble: int = pya.PCellDeclarationHelper.TypeDouble # type: ignore
_TypeInt: int = pya.PCellDeclarationHelper.TypeInt # type: ignore
_TypeBoolean: int = pya.PCellDeclarationHelper.TypeBoolean # type: ignore


class _MOSFET(pya.PCellDeclarationHelper):
    def __init__(self, *,
        layoutfab: _lay.LayoutFactory, gds_layers: _typ.GDSLayerSpecDict,
        mosfet: _prm.MOSFET,
    ):
        self._layoutfab = layoutfab
        self._gds_layers = gds_layers
        self._mosfet = mosfet
        super().__init__()

        self.param("_w",  _TypeDouble, "Width", unit="µm", default=mosfet.computed.min_w)
        self._w: float
        self.param("_l",  _TypeDouble, "Length", unit="µm", default=mosfet.computed.min_l)
        self._l: float

    def display_text_impl(self):
        # Provide a descriptive text for the cell
        return f"{self._mosfet.name}(w={self._w:1.3f}, l={self._l:1.3f})"

    def coerce_parameters_impl(self):
        mosfet = self._mosfet
        l = self._l
        w = self._w

        min_l = mosfet.computed.min_l
        if l < (min_l - _geo.epsilon):
            self._l = min_l

        min_w = mosfet.computed.min_w
        if w < (min_w - _geo.epsilon):
            self._w = min_w

    def produce_impl(self):
        mosfet = self._mosfet

        lay = self._layoutfab.layout_primitive(mosfet, l=self._l, w=self._w)

        export2db(lay,
            gds_layers=self._gds_layers,
            pya_cell=self.cell,
            merge=True,
        )


class _MOSFETFingers(pya.PCellDeclarationHelper):
    def __init__(self, *,
        layoutfab: _lay.LayoutFactory, gds_layers: _typ.GDSLayerSpecDict,
        mosfet: _prm.MOSFET,
    ):
        self._layoutfab = layoutfab
        self._gds_layers = gds_layers
        self._mosfet = mosfet

        diff = mosfet.gate.active
        cont: Optional[_prm.Via] = None
        for via in layoutfab.tech.primitives.__iter_type__(_prm.Via):
            if diff in via.bottom:
                cont = via
                break
        assert cont is not None
        self._cont = cont

        self._min_l = mosfet.computed.min_l
        idx = cont.bottom.index(diff)
        enc = cont.min_bottom_enclosure[idx].max()
        self._min_w = max(
            mosfet.computed.min_w,
            cont.width + 2*enc,
        )

        super().__init__()

        self.param("_w",  _TypeDouble, "Width", unit="µm", default=mosfet.computed.min_w)
        self._w: float
        self.param("_l",  _TypeDouble, "Length", unit="µm", default=mosfet.computed.min_l)
        self._l: float

        self.param("_fingers", _TypeInt, "Finger", default=2)
        self._fingers: int
        self.param("_left", _TypeBoolean, "Left cont.", default=True)
        self._left: bool
        self.param("_in", _TypeBoolean, "Inner cont.", default=True)
        self._in: bool
        self.param("_right", _TypeBoolean, "Right cont.", default=True)
        self._right: bool

    def display_text_impl(self):
        # Provide a descriptive text for the cell
        return f"{self._mosfet.name}(w={self._w:1.3f}, l={self._l:1.3f}, m={self._fingers})"

    def coerce_parameters_impl(self):
        mosfet = self._mosfet
        l = self._l
        min_l = self._min_l
        w = self._w
        min_w = self._min_w

        if l < (min_l - _geo.epsilon):
            self._l = min_l
        if w < (min_w - _geo.epsilon):
            self._w = min_w

    def produce_impl(self):
        layoutfab = self._layoutfab
        mosfet = self._mosfet
        cont = self._cont

        l = self._l
        w = self._w
        fingers = self._fingers
        leftch = self._left
        inch = self._in
        rightch = self._right

        cktfab = _ckt.CircuitFactory(tech=layoutfab.tech)

        ckt = cktfab.new_circuit(name="trans")
        layouter = layoutfab.new_circuitlayouter(circuit=ckt, boundary=None)

        def get_spec(i: int):
            inst = ckt.instantiate(mosfet, name=f"mos{i}", l=l, w=w)
            vl = cont if (((i == 0) and leftch) or ((i > 0) and inch)) else None
            vr = cont if (
                ((i < (fingers - 1)) and inch)
                or ((i == (fingers - 1)) and rightch)
            ) else None
            return _lay.MOSFETInstSpec(inst=inst, contact_left=vl, contact_right=vr)
        specs = tuple(get_spec(i) for i in range(fingers))

        ckt.new_net(name="g", external=False, childports=(
            *(spec.inst.ports["gate"] for spec in specs),
        ))
        ckt.new_net(name="sd", external=False, childports=(
            *(spec.inst.ports["sourcedrain1"] for spec in specs),
            *(spec.inst.ports["sourcedrain2"] for spec in specs),
        ))
        ckt.new_net(name="b", external=False, childports=(
            *(spec.inst.ports["bulk"] for spec in specs),
        ))

        layout = layouter.transistors_layout(trans_specs=specs)

        export2db(layout,
            gds_layers=self._gds_layers,
            pya_cell=self.cell,
            merge=True,
        )


class _ViaArray(pya.PCellDeclarationHelper):
    def __init__(self, *,
        layoutfab: _lay.LayoutFactory, gds_layers: _typ.GDSLayerSpecDict,
        via: _prm.Via,
    ):
        self._layoutfab = layoutfab
        self._gds_layers = gds_layers
        self._via = via
        self._vals = vals = {}
        super().__init__()

        self.param("_enct", _TypeInt, "Sizing", default=0, choices=(
            ("Minimal", 0), ("Enclosure", 1), ("Absolute", 2),
        ))
        self._enct: Any

        self.param("_rows", _TypeInt, "Rows", default = 2)
        self._rows: Any
        self.param("_cols", _TypeInt, "Columns", default = 1)
        self._cols: Any

        enc_choices = (("Wide", 0), ("Tall", 1))

        vals["n_diff"] = None
        choices = tuple((b.name, n) for n, b in enumerate(via.bottom))
        self.param("_b", _TypeInt, "Bottom", default=0, choices=choices, hidden=(len(via.bottom) == 1))
        self._b: Any

        enc = via.min_bottom_enclosure[0]
        hidden = not enc.is_assymetric
        d = 0 if enc.first > enc.second else 1
        self.param(
            "_benc", _TypeInt, "Bottom enclosure", default=d, choices=enc_choices, hidden=hidden,
        )
        self.param(
            "_benc_h", _TypeDouble, "Bot. hor. enclosure", unit="µm",
            default=enc.first, hidden=True,
        )
        self.param(
            "_benc_v", _TypeDouble, "Bot. ver. enclosure", unit="µm",
            default=enc.second, hidden=True,
        )
        self._benc: Any
        self._benc_h: Any
        self._benc_v: Any
        vals["benc"] = enc

        diffs = tuple(p for p in via.bottom if isinstance(p, _prm.WaferWire))
        if diffs:
            assert len(diffs) == 1
            diff = diffs[0]
            vals["n_diff"] = via.bottom.index(diff)
            choices = tuple(
                (im.name, n)
                for n, im in enumerate(diff.implant)
                if im.type_ in (_prm.nImpl, _prm.pImpl)
            )
            self.param(
                "_im", _TypeInt, "Bottom implant", default=0, choices=choices,
                hidden=(vals["n_diff"] != 0),
            )

            enc = diff.min_implant_enclosure[0]
            hidden = not enc.is_assymetric
            d = 0 if enc.first > enc.second else 1
            self.param(
                "_imenc", _TypeInt, "Impl.-diff. enclosure", unit="µm",
                default=d, choices=enc_choices, hidden=hidden,
            )
            self.param(
                "_imenc_h", _TypeDouble, "Impl. hor. enclosure", unit="µm",
                default=enc.first, hidden=True,
            )
            self.param(
                "_imenc_v", _TypeDouble, "Impl. ver. enclosure", unit="µm",
                default=enc.second, hidden=True,
            )
            vals["imenc"] = enc
        else:
            self.param(
                "_im", _TypeInt, "Bottom implant", default=0, hidden=True,
            )
            self.param(
                "_imenc", _TypeInt, "Impl.-diff. enclosure", unit="µm",
                default=0, choices=enc_choices, hidden=True,
            )
            self.param(
                "_imenc_h", _TypeDouble, "Bot. hor. enclosure", unit="µm",
                default=0.0, hidden=True,
            )
            self.param(
                "_imenc_v", _TypeDouble, "Bot. ver. enclosure", unit="µm",
                default=0.0, hidden=True,
            )
        self._im: Any
        self._imenc: Any
        self._imenc_h: Any
        self._imenc_v: Any

        choices = tuple((b.name, n) for n, b in enumerate(via.top))
        self.param("_t", _TypeInt, "Top", default=0, choices=choices, hidden=(len(via.top) == 1))
        self._t: Any

        enc = via.min_top_enclosure[0]
        hidden = not enc.is_assymetric
        d = 0 if enc.first > enc.second else 1
        self.param(
            "_tenc", _TypeInt, "Top enclosure", unit="µm",
            default=d, choices=enc_choices, hidden=hidden,
        )
        self.param(
            "_tenc_h", _TypeDouble, "Top hor. enclosure", unit="µm",
            default=enc.first, hidden=True,
        )
        self.param(
            "_tenc_v", _TypeDouble, "Top ver. enclosure", unit="µm",
            default=enc.second, hidden=True,
        )
        self._tenc: Any
        self._tenc_h: Any
        self._tenc_v: Any
        vals["tenc"] = enc

        benc = via.min_bottom_enclosure[0].max()
        tenc = via.min_top_enclosure[0].max()
        w = via.width + max(2*benc, 2*tenc)
        h = 2*via.width + via.min_space + max(2*benc, 2*tenc)
        self.param(
            "_padw", _TypeDouble, "Pad width", unit="µm", default=w, hidden=True,
        )
        self.param(
            "_padh", _TypeDouble, "Pad height", unit="µm", default=h, hidden=True,
        )
        self._padw: Any
        self._padh: Any

        self.param("_mins", _TypeBoolean, "Min. Space", default=True)
        self._mins: Any
        self.param(
            "_space", _TypeDouble, "Space", unit="µm", default=via.min_space, hidden=True,
        )
        self._space: Any

    def display_text_impl(self):
        via = self._via
        bottom = via.bottom[self._b]
        top = via.top[self._t]
        enct: int = self._enct

        if enct in (0, 1):
            return f"{bottom.name}-{via.name}-{top.name} ({self._rows}X{self._cols})"
        else:
            assert enct == 2
            padw = round(self._padw, 6)
            padh = round(self._padh, 6)
            return f"{bottom.name}-{via.name}-{top.name} ({padw}X{padh})"

    def coerce_parameters_impl(self):
        via = self._via
        enct: int = self._enct
        b: int = self._b
        t: int = self._t
        space = self._space

        if (enct == 2):
            encm = max(via.min_bottom_enclosure[b].max(), via.min_top_enclosure[t].max())
            d = via.width + 2*encm

            padw: float = self._padw
            if d > (padw + _geo.epsilon):
                self._padw = d

            padh: float = self._padh
            d = via.width + 2*encm
            if d > (padh + _geo.epsilon):
                self._padh = d

        if (space < (via.min_space - _geo.epsilon)):
            self._space = via.min_space

    # did not find way yet to test this code from unit test; done interactively in KLayout for now
    def callback_impl(self, name) -> None: # pragma: nocover
        via = self._via
        vals = self._vals
        n_diff = vals["n_diff"]

        b: int = self._b.value
        t: int = self._t.value
        enct = self._enct.value

        if name in ("", "_enct"):
            self._rows.visible = (enct != 2)
            self._cols.visible = (enct != 2)

            enc = via.min_bottom_enclosure[b]
            self._benc.visible = (enct == 0) and enc.is_assymetric
            self._benc_h.visible = (enct == 1)
            self._benc_v.visible = (enct == 1)

            if n_diff is not None:
                im: int = self._im.value

                enc = cast(_prm.WaferWire, via.bottom[n_diff]).min_implant_enclosure[im]
                self._imenc.visible = (n_diff == b) and enc.is_assymetric and (enct == 0)
                self._imenc_h.visible = (n_diff == b) and (enct == 1)
                self._imenc_v.visible = (n_diff == b) and (enct == 1)

            enc = via.min_top_enclosure[t]
            self._tenc.visible = (enct == 0) and enc.is_assymetric
            self._tenc_h.visible = (enct == 1)
            self._tenc_v.visible = (enct == 1)

            self._padw.visible = (enct == 2)
            self._padh.visible = (enct == 2)

        if name in ("", "_b"):
            enc = via.min_bottom_enclosure[b]
            self._benc.visible = (enct == 0) and enc.is_assymetric
            self._benc_h.visible = (enct == 1)
            self._benc_v.visible = (enct == 1)

        if name in ("", "_enct", "_b", "_benc", "_benc_h", "_benc_v"):
            if (enct == 0):
                be: int = self._benc.value
                enc = via.min_bottom_enclosure[b]

                vals["benc"] = enc.wide() if be == 0 else enc.tall()
            elif (enct == 1):
                be_h = self._benc_h.value
                be_v = self._benc_v.value

                vals["benc"] = _prp.Enclosure((be_h, be_v))

        if n_diff is not None:
            if name in ("", "_b"):
                if n_diff == b:
                    self._im.visible = True
                    self._imenc.visible = (enct == 0)
                    self._imenc_h.visible = (enct == 1)
                    self._imenc_v.visible = (enct == 1)
                else:
                    self._im.visible = False
                    self._imenc.visible = False
                    self._imenc_h.visible = False
                    self._imenc_v.visible = False

            if name in ("", "_im", "_imenc", "_imenc_h", "_imenc_v"):
                im = self._im.value

                if n_diff == b:
                    if (enct == 0):
                        imenc = self._imenc.value
                        enc = via.bottom[n_diff].min_implant_enclosure[im]

                        vals["imenc"] = enc.wide() if imenc == 0 else enc.tall()
                    elif (enct == 1):
                        imenc_h = self._imenc_h.value
                        imenc_v = self._imenc_v.value

                        vals["imenc"] = _prp.Enclosure((imenc_h, imenc_v))

        if name in ("", "_t"):
            enc = via.min_top_enclosure[t]
            self._tenc.visible = (enct == 0) and enc.is_assymetric
            self._tenc_h.visible = (enct == 1)
            self._tenc_v.visible = (enct == 1)

        if name in ("", "_tenc", "_tenc_h", "_tenc_v"):
            if (enct == 0):
                te: int = self._tenc.value
                enc = via.min_top_enclosure[t]

                vals["tenc"] = enc.wide() if te == 0 else enc.tall()
            elif (enct == 1):
                te_h = self._tenc_h.value
                te_v = self._tenc_v.value

                vals["tenc"] = _prp.Enclosure((te_h, te_v))

        if name in ("", "_mins"):
            self._space.visible = not self._mins.value

    def produce_impl(self):
        layoutfab = self._layoutfab
        gds_layers = self._gds_layers
        via = self._via
        vals = self._vals

        enct: int = self._enct
        rows: int = self._rows
        cols: int = self._cols
        b: int = self._b
        t: int = self._t
        im: int = self._im
        padw = self._padw
        padh = self._padh
        mins = self._mins
        space = self._space

        args = {}
        if len(via.bottom) > 1:
            args["bottom"] = via.bottom[b]
            if vals["n_diff"] is not None:
                if b == vals["n_diff"]:
                    diff = via.bottom[vals["n_diff"]]
                    assert isinstance(diff, _prm.WaferWire)
                    args["bottom_implant"] = diff.implant[im],
                    if enct in (0, 1):
                        args["bottom_implant_enclosure"] = vals["imenc"]
        if len(via.top) > 1:
            args["top"] = via.top[t]
        if enct in (0, 1):
            args.update({
                "rows": rows,
                "columns": cols,
                "bottom_enclosure": vals["benc"],
                "top_enclosure": vals["tenc"],
            })
        else:
            assert enct == 2
            args.update({
                "bottom_width": padw, "top_width": padw,
                "bottom_height": padh, "top_height": padh,
            })
        if not mins:
            args["space"] = space
        layout = layoutfab.layout_primitive(prim=via, **args)

        export2db(layout,
            gds_layers=gds_layers,
            pya_cell=self.cell,
            merge=True,
        )


class _Resistor(pya.PCellDeclarationHelper):
    def __init__(self, *,
        layoutfab: _lay.LayoutFactory, gds_layers: _typ.GDSLayerSpecDict,
        res: _prm.Resistor,
    ):
        self._layoutfab = layoutfab
        self._gds_layers = gds_layers
        self._res = res
        super().__init__()

        self.param("_w",  _TypeDouble, "Width", unit="µm", default=res.min_width)
        self._w: float
        self.param("_l",  _TypeDouble, "Length", unit="µm", default=res.min_length)
        self._l: float

    def display_text_impl(self):
        # Provide a descriptive text for the cell
        return f"{self._res.name}(w={self._w:1.3f}, l={self._l:1.3f})"

    def coerce_parameters_impl(self):
        res = self._res
        l = self._l
        w = self._w

        min_l = res.min_length
        if l < (min_l - _geo.epsilon):
            self._l = min_l

        min_w = res.min_width
        if w < (min_w - _geo.epsilon):
            self._w = min_w

    def produce_impl(self):
        res = self._res

        lay = self._layoutfab.layout_primitive(res, length=self._l, width=self._w)

        export2db(lay,
            gds_layers=self._gds_layers,
            pya_cell=self.cell,
            merge=True,
        )


class _PCellGenerator(PrimitiveDispatcher):
    def __init__(self, *, pya_lib: "PCellLibrary"):
        self._pya_lib = pya_lib
        self._pya_layout = pya_lib.layout()
        super().__init__()

    def __call__(self, prim: _prm.PrimitiveT) -> None:
        super().__call__(prim)

    def register(self, helper: pya.PCellDeclarationHelper, *, name: str):
        self._pya_layout.register_pcell(name, helper)

    # By default do nothing
    def _Primitive(self, prim: _prm.PrimitiveT) -> None:
        pass

    def Via(self, prim: _prm.Via):
        bottom_args: List[Tuple[str, Dict[str, Any]]] = []
        def add_bottom(*,
            bot: _prm.ViaBottom, enc: _prp.Enclosure,
            impl: Optional[_prm.Implant]=None, impl_enc: Optional[_prp.Enclosure]=None,
        ):
            b_args = {"bottom": bot} if len(prim.bottom) != 1 else {}
            if not enc.is_assymetric:
                args = (
                    (f"_{bot.name}", b_args),
                )
            else:
                args = (
                    (f"_{bot.name}$W", {**b_args, "bottom_enclosure": enc.wide()}),
                    (f"_{bot.name}$T", {**b_args, "bottom_enclosure": enc.tall()}),
                )
            if not impl:
                bottom_args.extend(args)
            else:
                assert isinstance(bot, _prm.WaferWire)
                assert impl_enc is not None
                if not impl_enc.is_assymetric:
                    bottom_args.extend((
                        (arg[0] + f"${impl.name}", {**arg[1], "bottom_implant": impl})
                        for arg in args
                    ))
                else:
                    bottom_args.extend((
                        (arg[0] + f"${impl.name}$W", {
                            **arg[1],
                            "bottom_implant": impl,
                            "bottom_implant_enclosure": impl_enc.wide(),
                        })
                        for arg in args
                    ))
                    bottom_args.extend((
                        (arg[0] + f"${impl.name}$T", {
                            **arg[1],
                            "bottom_implant": impl,
                            "bottom_implant_enclosure": impl_enc.tall(),
                        })
                        for arg in args
                    ))
        for i, bot in enumerate(prim.bottom):
            if not isinstance(bot, _prm.Resistor):
                enc = prim.min_bottom_enclosure[i]

                add_bottom(bot=bot, enc=enc)
                if isinstance(bot, _prm.WaferWire):
                    for i2, impl in enumerate(bot.implant):
                        if impl.type_ in (_prm.nImpl, _prm.pImpl):
                            add_bottom(
                                bot=bot, enc=enc,
                                impl=impl, impl_enc=bot.min_implant_enclosure[i2],
                            )

        top_args: List[Tuple[str, Dict[str, Any]]] = []
        def add_top(*, top: _prm.ViaTop, enc: _prp.Enclosure):
            t_args = {"top": top} if len(prim.top) != 1 else {}
            if not enc.is_assymetric:
                top_args.append((f"_{top.name}", t_args))
            else:
                top_args.extend((
                    (f"_{top.name}$W", {**t_args, "top_enclosure": enc.wide()}),
                    (f"_{top.name}$T", {**t_args, "top_enclosure": enc.tall()}),
                ))
        for i, top in enumerate(prim.top):
            if not isinstance(top, _prm.Resistor):
                enc = prim.min_top_enclosure[i]
                add_top(top=top, enc=enc)

        for barg, targ in product(bottom_args, top_args):
            name = prim.name + barg[0] + targ[0]
            cell = self._pya_layout.create_cell(name)
            lay = self._pya_lib._layoutfab.layout_primitive(
                prim=prim, **barg[1], **targ[1],
            )
            export2db(lay,
                gds_layers=self._pya_lib._gds_layers,
                pya_cell=cell,
                merge=True,
            )

        h = _ViaArray(
            layoutfab=self._pya_lib._layoutfab, gds_layers=self._pya_lib._gds_layers,
            via=prim,
        )
        self.register(h, name=f"{prim.name}$array")

    def Resistor(self, prim: _prm.Resistor):
        layoutfab = self._pya_lib._layoutfab
        gds_layers = self._pya_lib._gds_layers

        h = _Resistor(layoutfab=layoutfab, gds_layers=gds_layers, res=prim)
        self.register(h, name=prim.name)

    def MOSFET(self, prim: _prm.MOSFET) -> None:
        layoutfab = self._pya_lib._layoutfab
        gds_layers = self._pya_lib._gds_layers

        h = _MOSFET(
            layoutfab=layoutfab, gds_layers=gds_layers, mosfet=prim,
        )
        self.register(h, name=prim.name)

        h = _MOSFETFingers(
            layoutfab=layoutfab, gds_layers=gds_layers, mosfet=prim,
        )
        self.register(h, name=f"{prim.name}$fingers")


class PCellLibrary(pya.Library):
    def __init__(self, *,
        name: str, layoutfab: _lay.LayoutFactory, gds_layers: _typ.GDSLayerSpecDict,
    ):
        self._layoutfab = layoutfab
        self._gds_layers = gds_layers
        tech = layoutfab.tech
        self.description = f"PDKMaster based primitive library for {tech.name}"

        gen = _PCellGenerator(pya_lib=self)
        for prim in tech.primitives:
            gen(prim)

        self.register(name)
