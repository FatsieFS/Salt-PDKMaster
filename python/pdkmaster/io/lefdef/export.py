# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0

from textwrap import dedent
from typing import Optional, Tuple, Callable, Iterable, Union

from ...technology import (
    primitive as prm, technology_ as tch,
)


__all__ = ["LEFExporter"]


class LEFExporter:
    def __init__(self, *,
        tech: tch.Technology,
        site_width: float, site_height: float,
        use_nwell: bool=False,
        use_pwell: bool=False,
        bottom_metal_horizontal: bool=True,
        site_name: str="Site",
        metals: Optional[Iterable[prm.MetalWire]]=None,
        vias: Optional[Iterable[prm.Via]]=None,
        layer_name_cb: Callable[[Union[prm.MetalWire, prm.Via]], str]=lambda p: p.name,
        via_name_cb: Optional[Callable[[prm.MetalWire, prm.Via, prm.MetalWire], str]]=None,
        metals_sheetres: Optional[Iterable[float]]=None,
        pitches: Optional[Iterable[float]]=None
    ):
        if via_name_cb is None:
            class CB:
                def __init__(self, cb):
                    self.cb = cb

                def name(self, bmetal: prm.MetalWire, via: prm.Via, tmetal: prm.MetalWire):
                    cb = self.cb
                    return f"{cb(bmetal)}_{cb(via)}_{cb(tmetal)}"
            via_name_cb = CB(layer_name_cb).name
        self.tech = tech
        self.use_nwell = use_nwell
        self.use_pwell = use_pwell
        self.bottom_metal_horizontal = bottom_metal_horizontal
        self.site_name = site_name
        self.site_width = site_width
        self.site_height = site_height
        if metals is None:
            self.metals = metals = tuple(filter(
                lambda p: not isinstance(p, prm.MIMTop),
                self.tech.primitives.__iter_type__(prm.MetalWire),
            ))
        else:
            self.metals = metals = tuple(metals)
        if vias is None:
            self.vias = vias = tuple(self.tech.primitives.__iter_type__(prm.Via))
        else:
            self.vias = vias = tuple(vias)
        self.layer_name_cb = layer_name_cb
        self.via_name_cb = via_name_cb
        self.metals_sheetres = tuple(metals_sheetres) if metals_sheetres is not None else None
        if pitches is None:
            self.pitches = [
                max(
                    vias[i].width/2 + vias[i].min_top_enclosure[0].max()
                    + metals[i].min_space + metals[i].min_width,
                    vias[i+1].width/2 + vias[i+1].min_bottom_enclosure[0].max()
                    + metals[i].min_space + metals[i].min_width,
                ) for i in range(len(metals)-1)
            ] + [
                vias[-1].width/2 + vias[-1].min_top_enclosure[0].max()
                + metals[-1].min_space + metals[-1].min_width
            ]
        else:
            self.pitches = tuple(pitches)

    def __call__(self):
        return {
            "techlef": self._techlef(),
        }

    def _gen_layer_via(self, via: prm.Via, name: str):
        result_string = dedent(f"""
            LAYER {name}
                TYPE CUT ;

        """)
        if via.min_space is not None:
            result_string += f"    SPACING {via.min_space:.5f} ;\n"
        result_string += f"END {name}\n"
        return result_string

    def _gen_layer_metal(self,
        metal: prm.MetalWire, name: str, routing_horizontal: bool, pitch: float,
        sheetres: Optional[float]=None,
    ):
        result_string = dedent(f"""
            LAYER {name}
                TYPE ROUTING ;
                DIRECTION {"HORIZONTAL" if routing_horizontal else "VERTICAL"} ;
                PITCH {pitch:.5f} ;

        """)

        result_string += f"    WIDTH {metal.min_width:.5f} ;\n"
        result_string += f"    SPACING {metal.min_space:.5f} ;\n"
        if metal.min_area is not None:
            result_string += f"    AREA {metal.min_area:.5f} ;\n"
        if sheetres is not None:
            result_string += f"    RESISTANCE RPERSQ {sheetres} ;\n"
        result_string += f"    ANTENNAMODEL OXIDE1 ;\n"
        result_string += f"END {name}\n\n"
        return result_string
    
    def _gen_viarule(self, bmetal: prm.MetalWire, via: prm.Via, tmetal: prm.MetalWire):
        bmetal_enc = via.min_bottom_enclosure[0].min()
        bmetal_enc_both_sides = via.min_bottom_enclosure[0].max()
        tmetal_enc = via.min_top_enclosure[0].min()
        tmetal_enc_both_sides = via.min_top_enclosure[0].max()
        result_string = dedent(f"""
            VIARULE {self.via_name_cb(bmetal, via, tmetal)} GENERATE
                LAYER {self.layer_name_cb(bmetal)} ;
                    ENCLOSURE {bmetal_enc_both_sides:.5f} {bmetal_enc:.5f} ;
                LAYER {self.layer_name_cb(via)} ;
                    RECT {-via.width/2:.5f} {-via.width/2:.5f} {via.width/2:.5f} {via.width/2:.5f} ;
                    SPACING {via.min_space:.5f} BY {via.min_space:.5f} ;
                LAYER {self.layer_name_cb(tmetal)} ;
                    ENCLOSURE {tmetal_enc_both_sides:.5f} {tmetal_enc:.5f} ;
            END {self.via_name_cb(bmetal, via, tmetal)}

        """)
        return result_string

    def _gen_via(self,
        name: str, bmetal: prm.MetalWire, via: prm.Via, tmetal: prm.MetalWire,
        bmetal_dims: Tuple[float, float], via_dims: Tuple[float, float],
        tmetal_dims: Tuple[float, float],
    ):
        result_string = dedent(f"""
            VIA {name} DEFAULT
]                LAYER {self.layer_name_cb(bmetal)} ;
                    RECT {-bmetal_dims[0]/2:.5f} {-bmetal_dims[1]/2:.5f} {bmetal_dims[0]/2:.5f} {bmetal_dims[1]/2:.5f} ;
                LAYER {self.layer_name_cb(via)} ;
                    RECT {-via_dims[0]/2:.5f} {-via_dims[1]/2:.5f} {via_dims[0]/2:.5f} {via_dims[1]/2:.5f} ;
                LAYER {self.layer_name_cb(tmetal)} ;
                    RECT {-tmetal_dims[0]/2:.5f} {-tmetal_dims[1]/2:.5f} {tmetal_dims[0]/2:.5f} {tmetal_dims[1]/2:.5f} ;
            END {name}

        """)

        return result_string

    def _techlef(self):
        tlef_string = dedent(f"""
            VERSION 5.7 ;
            UNITS
                DATABASE MICRONS 1000 ;
            END UNITS
            MANUFACTURINGGRID {self.tech.grid:.5f} ;
        """)

        if self.use_nwell:
            nwell_name = "nwell"
            for well in self.tech.primitives.__iter_type__(prm.Well):
                if well.type_ == prm.nImpl:
                    nwell_name = well.name
                    break
            tlef_string += dedent(f"""
                LAYER {nwell_name}
                    TYPE MASTERSLICE ;
                    PROPERTY LEF58_TYPE "TYPE NWELL ;" ;
                END {nwell_name}
            """)
        if self.use_pwell:
            pwell_name = "pwell"
            for well in self.tech.primitives.__iter_type__(prm.Well):
                if well.type_ == prm.pImpl:
                    pwell_name = well.name
                    break
            tlef_string += dedent(f"""
                LAYER {pwell_name}
                    TYPE MASTERSLICE ;
                    PROPERTY LEF58_TYPE "TYPE PWELL ;" ;
                END {pwell_name}
            """)

        metals = self.metals
        vias = self.vias
        pitches = self.pitches

        for i in range(len(metals)):
            metal = metals[i]
            via = vias[i]
            tlef_string += self._gen_layer_via(via, self.layer_name_cb(via))

            metal_num = i+1
            pitch = pitches[i]
            sheetres = None if self.metals_sheetres is None else self.metals_sheetres[i]
            
            tlef_string += self._gen_layer_metal(
                metal, self.layer_name_cb(metal),
                metal_num%2 == self.bottom_metal_horizontal, pitch, sheetres,
            )

        for i in range(1, len(vias)):
            via = vias[i]
            bmetal = metals[i-1]
            tmetal = metals[i]
            via_name = self.via_name_cb(bmetal, via, tmetal)
            bmetal_enc = via.min_bottom_enclosure[0].min()
            bmetal_enc_both_sides = via.min_bottom_enclosure[0].max()
            tmetal_enc = via.min_top_enclosure[0].min()
            tmetal_enc_both_sides = via.min_top_enclosure[0].max()
            w = via.width
            
            if i == 1:
                tlef_string += self._gen_via(
                    f"{via_name}_square", bmetal, via, tmetal,
                    bmetal_dims=(w, w), via_dims=(w, w), tmetal_dims=(w, w),
                )
            tlef_string += self._gen_via(
                f"{via_name}_HH", bmetal, via, tmetal,
                bmetal_dims=(w+2*bmetal_enc_both_sides, w+2*bmetal_enc), via_dims=(w, w),
                tmetal_dims=(w+2*tmetal_enc_both_sides, w+2*tmetal_enc),
            )
            tlef_string += self._gen_via(
                f"{via_name}_HV", bmetal, via, tmetal,
                bmetal_dims=(w+2*bmetal_enc_both_sides, w+2*bmetal_enc), via_dims=(w, w),
                tmetal_dims=(w+2*tmetal_enc, w+2*tmetal_enc_both_sides),
            )
            tlef_string += self._gen_via(
                f"{via_name}_VH", bmetal, via, tmetal,
                bmetal_dims=(w+2*bmetal_enc, w+2*bmetal_enc_both_sides), via_dims=(w, w),
                tmetal_dims=(w+2*tmetal_enc_both_sides, w+2*tmetal_enc),
            )
            tlef_string += self._gen_via(
                f"{via_name}_VV", bmetal, via, tmetal,
                bmetal_dims=(w+2*bmetal_enc, w+2*bmetal_enc_both_sides), via_dims=(w, w),
                tmetal_dims=(w+2*tmetal_enc, w+2*tmetal_enc_both_sides),
            )

            tlef_string += self._gen_viarule(bmetal, via, tmetal)

        tlef_string += dedent(f"""
            SITE  {self.site_name}
                CLASS       CORE ;
                SYMMETRY    Y ;
                SIZE        {self.site_width:.5f} BY {self.site_height:.5f} ;
            END  {self.site_name}

            END LIBRARY
        """)

        return tlef_string
