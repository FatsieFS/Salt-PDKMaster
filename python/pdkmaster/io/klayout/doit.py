# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
# module for support for doit tasks
from os.path import relpath
from pathlib import Path
from textwrap import dedent
from xml.etree import ElementTree as ET
from typing import Dict, Tuple, Collection, Union, Any, Iterable, Optional, Callable

from doit.action import CmdAction
from pdkmaster.typing import GDSLayerSpecDict
from pdkmaster.task import OpenPDKTree, TaskManager as _PDKMasterTaskManager
from pdkmaster.technology import technology_ as _tch
from pdkmaster.design import library as _lbry

from pdkmaster.io.spice import SpicePrimsParamSpec


__all__ = ["CheckError", "KlayoutExportTaskT", "TaskManager"]


class CheckError(Exception):
    "Exception raised when a DRC or LVS check fails"


class _KlayoutExportTask:
    def __init__(self, *,
        manager: "TaskManager", spice_params_cb: Callable[[], SpicePrimsParamSpec],
        layerprops_filename: Optional[str],
        extra_filedep: Tuple[Union[str, Path], ...], extra_taskdep: Tuple[str, ...],
    ) -> None:
        self._mng = manager
        self._spice_params_cb = spice_params_cb
        self._layerprops = layerprops_filename
        self._extra_filedep = extra_filedep
        self._extra_taskdep = extra_taskdep

    def task_func(self) -> Dict[str, Any]:
        "Creating klayout files"
        mng = self._mng

        return {
            "title": lambda _: self.task_func.__doc__,
            "file_dep": (*self._extra_filedep, *mng._src_deps),
            "task_dep": self._extra_taskdep,
            "targets": self.targets,
            "actions": (
                self._gen_klayout,
            ),
        }

    @property
    def targets(self) -> Iterable[Path]:
        mng = self._mng
        return (
            mng.lyt_file, mng.drc_lydrc_file, mng.extract_lylvs_file, mng.drc_file, mng.drc_script,
            mng.extract_file, mng.extract_script, mng.lvs_file, mng.lvs_script,
        )

    def _gen_klayout(self):
        from pdkmaster.io.klayout import FileExporter

        mng = self._mng

        expo = FileExporter(
            tech=mng.tech, gds_layers=mng.gds_layers, textgds_layers=mng.textgds_layers,
            export_name=mng.pdk_name,
            prims_spiceparams=self._spice_params_cb(),
        )(layerprops=self._layerprops)

        mng._share_dir.mkdir(parents=True, exist_ok=True)
        mng._bin_dir.mkdir(parents=True, exist_ok=True)
        mng._drc_dir.mkdir(parents=True, exist_ok=True)
        mng._lvs_dir.mkdir(parents=True, exist_ok=True)

        # DRC
        with mng.drc_file.open("w") as f:
            f.write(expo["drc"])
        with mng.drc_script.open("w") as f:
            relfile = relpath(mng.drc_file, mng._bin_dir)
            f.write(dedent(f"""
                #!/bin/sh
                d=`dirname $0`
                deck=`realpath $d/{relfile}`

                if [ $# -eq 2  ]; then
                    export SOURCE_FILE=`realpath $1` CELL_NAME= REPORT_FILE=`realpath $2`
                elif [ $# -eq 3  ]; then
                    export SOURCE_FILE=`realpath $1` CELL_NAME="$2" REPORT_FILE=`realpath $3`
                else
                    echo "Usage `basename $0` input_gds [cell_name] report"
                    exit 20
                fi

                klayout -b -r ${{deck}}
            """[1:]))
        mng.drc_script.chmod(0o755)

        # Extract
        with mng.extract_file.open("w") as f:
            f.write(expo["extract"])
        with mng.extract_script.open("w") as f:
            relfile = relpath(mng.extract_file, mng._bin_dir)
            f.write(dedent(f"""
                #!/bin/sh
                d=`dirname $0`
                deck=`realpath $d/{relfile}`

                if [ $# -eq 2  ]; then
                    export SOURCE_FILE=`realpath $1` CELL_NAME= REPORT_FILE=`realpath $2`
                elif [ $# -eq 3  ]; then
                    export SOURCE_FILE=`realpath $1` CELL_NAME="$2" REPORT_FILE=`realpath $3`
                else
                    echo "Usage `basename $0` input_gds [cell_name] spice_out"
                    exit 20
                fi

                klayout -b -r ${{deck}}
            """[1:]))
        mng.extract_script.chmod(0o755)

        # LVS
        with mng.lvs_file.open("w") as f:
            f.write(expo["lvs"])
        with mng.lvs_script.open("w") as f:
            relfile = relpath(mng.lvs_file, mng._bin_dir)
            f.write(dedent(f"""
                #!/bin/sh
                d=`dirname $0`
                deck=`realpath $d/{relfile}`

                if [ $# -eq 3  ]; then
                    export SOURCE_FILE=`realpath $1` CELL_NAME= SPICE_FILE=`realpath $2` REPORT_FILE=`realpath $3`
                elif [ $# -eq 4  ]; then
                    export SOURCE_FILE=`realpath $1` CELL_NAME="$2" SPICE_FILE=`realpath $3` REPORT_FILE=`realpath $4`
                else
                    echo "Usage `basename $0` input_gds [cell_name] input_spice report"
                    exit 20
                fi

                klayout -b -r ${{deck}}
            """[1:]))
        mng.lvs_script.chmod(0o755)

        # klayout technology
        et = ET.ElementTree(expo["ly_drc"])
        et.write(mng.drc_lydrc_file, encoding="utf-8", xml_declaration=True)
        et = ET.ElementTree(expo["ly_extract"])
        et.write(mng.extract_lylvs_file, encoding="utf-8", xml_declaration=True)
        et = ET.ElementTree(expo["ly_tech"])
        et.write(mng.lyt_file, encoding="utf-8", xml_declaration=True)
KlayoutExportTaskT = _KlayoutExportTask


class _KlayoutGDSTask:
    def __init__(self, *,
        manager: "TaskManager",
        extra_filedep: Tuple[Union[str, Path], ...], extra_filedep_lib: Dict[str, Tuple[Path, ...]],
        extra_taskdep: Tuple[str, ...],
    ) -> None:
        self._mng = manager
        self._extra_filedep = extra_filedep
        self._extra_filedep_lib = extra_filedep_lib
        self._extra_taskdep = extra_taskdep

    def _gen_gds(self, lib_name):
        from pdkmaster.io.klayout import export2db, merge

        mng = self._mng
        openpdk_tree = mng._openpdk_tree

        lib = mng.lib4name(lib_name)

        # Generate layout for all cells and merge it.
        # Cell may be added during generation
        for cell in lib.cells:
            cell.layout
        merge(lib)

        out_dir = openpdk_tree.views_dir(lib_name=lib_name, view_name="gds")
        out_dir.mkdir(parents=True, exist_ok=True)
        layout = export2db(
            lib, gds_layers=mng.gds_layers, merge=False, add_pin_label=True,
        )
        layout.write(str(out_dir.joinpath(f"{lib_name}.gds")))
        for cell in layout.each_cell():
            assert cell.name != lib_name
            cell.write(str(out_dir.joinpath(f"{cell.name}.gds")))

    def task_func_gds(self):
        """Generate GDSII files"""
        mng = self._mng
        openpdk_tree = mng._openpdk_tree

        for lib_name, cells in mng.cell_list.items():
            gds_dir = openpdk_tree.views_dir(lib_name=lib_name, view_name="gds")
            gds_files = (
                *(gds_dir.joinpath(f"{cell}.gds") for cell in cells),
                gds_dir.joinpath(f"{lib_name}.gds"),
            )

            yield {
                "name": lib_name,
                "doc": f"Creating gds files for {lib_name}",
                "file_dep": (*self._extra_filedep, *self._extra_filedep_lib.get(lib_name, ())),
                "targets": gds_files,
                "actions": (
                    (self._gen_gds, (lib_name,)),
                ),
            }
KLayoutGDSTaskT = _KlayoutGDSTask


class _KLayoutDRCTask:
    def __init__(self, *,
        manager: "TaskManager",
        waive_func: Optional[Callable[[str, str, ET.Element], bool]],
        extra_filedep: Tuple[Union[str, Path], ...],
        extra_taskdep: Tuple[str, ...],
    ) -> None:
        self._mng = manager
        self._waive_func = waive_func
        self._extra_filedep = extra_filedep
        self._extra_taskdep = extra_taskdep


    def task_func_drc(self):
        "Run drc checks per library"
        mng = self._mng

        for lib, cells in mng.cell_list.items():
            # If there exist a Gallery cell then do only DRC on that cell by default
            gallery_cells = tuple(filter(lambda s: s.endswith("Gallery"), cells))
            if gallery_cells:
                cells = gallery_cells

            repfiles = tuple(mng.out_dir_drc.joinpath(lib, f"{cell}.rep") for cell in cells)

            yield {
                "name": f"{lib}",
                "doc": f"Assembling DRC results for lib",
                "file_dep": repfiles,
                "actions": (),
            }

    def _run_drc(self, lib: str, cell: str, gdsfile: Path, drcrep: Path):
        mng = self._mng

        drcrep.parent.mkdir(parents=True, exist_ok=True)

        try:
            CmdAction(
                f"{str(mng.drc_script)} {str(gdsfile)} {cell} {str(drcrep)}",
            ).execute()
        except: # pragma: no cover
            ok = False
        else:
            top: ET.Element = ET.parse(drcrep).getroot()
            items = top.find("items")
            assert items is not None
            ok = True
            for item in items.iterfind("item"): # pragma: no cover
                cat = item.find("category")
                assert cat is not None
                if (
                    (self._waive_func is not None)
                    and self._waive_func(lib, cell, cat)
                ):
                    continue
                ok = False
                break
        if not ok: # pragma: no cover
            raise CheckError(f"DRC of {lib}/{cell} failed!")

    def task_func_drccells(self):
        """DRC check task for each cell in each library"""
        mng = self._mng
        openpdk_tree = mng._openpdk_tree

        for lib, cells in mng.cell_list.items():
            gds_dir = openpdk_tree.views_dir(lib_name=lib, view_name="gds")
            gdsfile = gds_dir.joinpath(f"{lib}.gds")

            for cell in cells:
                drcrep = mng.out_dir_drc.joinpath(lib, f"{cell}.rep")

                yield {
                    "name": f"{lib}:{cell}",
                    "doc": f"Running DRC check for lib {lib} cell {cell}",
                    "file_dep": (
                        *self._extra_filedep,
                        mng.drc_script, gdsfile,
                        *mng._src_deps,
                    ),
                    "targets": (drcrep,),
                    "actions": (
                        (self._run_drc, (lib, cell, gdsfile, drcrep)),
                    )
                }
KLayoutDRCTaskT = _KLayoutDRCTask


class _KLayoutLVSTask:
    def __init__(self, *,
        manager: "TaskManager",
        extra_filedep: Tuple[Union[str, Path], ...],
        extra_taskdep: Tuple[str, ...],
    ) -> None:
        self._mng = manager
        self._extra_filedep = extra_filedep
        self._extra_taskdep = extra_taskdep

    def task_func_lvs(self):
        "Run lvs checks"
        mng = self._mng

        for lib, cells in mng.cell_list.items():
            # Only run LVS on Gallery cell if it exists
            gallery_cells = tuple(filter(lambda s: s.endswith("Gallery"), cells))
            if gallery_cells:
                cells = gallery_cells

            lvsdbfiles = tuple(
                mng.out_dir_lvs.joinpath(lib, f"{cell}.lvsdb") for cell in cells
            )
            yield {
                "name": lib,
                "doc": f"Running LVS check for lib {lib}",
                "file_dep": lvsdbfiles,
                "actions": (),
            }

    def _run_lvs(self, lib: str, cell: str, gdsfile: Path, spicefile: Path, lvsdb: Path):
        mng = self._mng

        lvsdb.parent.mkdir(parents=True, exist_ok=True)

        try:
            ok = CmdAction(
                f"{str(mng.lvs_script)} {str(gdsfile)} {cell} {str(spicefile)} {str(lvsdb)}",
            ).execute() is None
        except: # pragma: no cover
            ok = False
        if not ok:
            raise CheckError(f"LVS of {lib}/{cell} failed!")

    def task_func_lvscells(self):
        """LVS check for each cell in each library"""
        mng = self._mng
        openpdk_tree = mng._openpdk_tree

        for lib, cells in mng.cell_list.items():
            gds_dir = openpdk_tree.views_dir(lib_name=lib, view_name="gds")
            spice_dir = openpdk_tree.views_dir(lib_name=lib, view_name="spice")

            gdsfile = gds_dir.joinpath(f"{lib}.gds")
            spicefile = spice_dir.joinpath(f"{lib}_lvs.spi")
            for cell in cells:
                lvsdbfile = mng.out_dir_lvs.joinpath(lib, f"{cell}.lvsdb")

                yield {
                    "name": f"{lib}:{cell}",
                    "doc": f"Running DRC check for lib {lib} cell {cell}",
                    "file_dep": (*self._extra_filedep, gdsfile, spicefile),
                    "task_dep": ("klayout",),
                    "targets": (lvsdbfile,),
                    "actions": (
                        (self._run_lvs, (lib, cell, gdsfile, spicefile, lvsdbfile)),
                    ),
                }
KLayoutLVSTaskT = _KLayoutLVSTask


class TaskManager(_PDKMasterTaskManager):
    def __init__(self, *,
        tech_cb: Callable[[], _tch.Technology],
        lib4name_cb: Callable[[str], _lbry.Library],
        cell_list: Dict[str, Collection[str]],
        top_dir: Path, openpdk_tree: OpenPDKTree,
        gdslayers_cb: Callable[[], GDSLayerSpecDict],
        textgdslayers_cb: Callable[[], GDSLayerSpecDict]=(lambda: {}),
        task_name_drc: str="drc", task_name_lvs: str="lvs",
    ) -> None:
        super().__init__(
            tech_cb=tech_cb, lib4name_cb=lib4name_cb, cell_list=cell_list,
            top_dir=top_dir, openpdk_tree=openpdk_tree,
        )
        self._gdslayer_cb = gdslayers_cb
        self._textgdslayer_cb = textgdslayers_cb
        self._task_name_drc = task_name_drc
        self._task_name_lvs = task_name_lvs
        klayout_dir = openpdk_tree.tool_dir(tool_name="klayout")
        self._tech_dir = tech_dir = klayout_dir.joinpath("tech", self.pdk_name)
        self._drc_dir = tech_dir.joinpath("drc")
        self._lvs_dir = tech_dir.joinpath("lvs")
        self._share_dir = klayout_dir.joinpath("share")
        self._bin_dir = klayout_dir.joinpath("bin")

        from . import export
        self._src_deps = (__file__, export.__file__)

    @property
    def gds_layers(self) -> GDSLayerSpecDict:
        return self._gdslayer_cb()
    @property
    def textgds_layers(self) -> GDSLayerSpecDict:
        return self._textgdslayer_cb()

    @property
    def lyt_file(self) -> Path:
        return self._tech_dir.joinpath(f"{self.pdk_name}.lyt")
    @property
    def drc_lydrc_file(self) -> Path:
        return self._drc_dir.joinpath("DRC.lydrc")
    @property
    def extract_lylvs_file(self) -> Path:
        return self._lvs_dir.joinpath("Extract.lylvs")
    @property
    def drc_file(self) -> Path:
        return self._share_dir.joinpath(f"{self.pdk_name}.drc")
    @property
    def drc_script(self) -> Path:
        return self._bin_dir.joinpath(f"drc_{self.pdk_name}")
    @property
    def extract_file(self) -> Path:
        return self._share_dir.joinpath(f"{self.pdk_name}_extract.lvs")
    @property
    def extract_script(self) -> Path:
        return self._bin_dir.joinpath(f"extract_{self.pdk_name}")
    @property
    def lvs_file(self) -> Path:
        return self._share_dir.joinpath(f"{self.pdk_name}.lvs")
    @property
    def lvs_script(self) -> Path:
        return self._bin_dir.joinpath(f"lvs_{self.pdk_name}")

    @property
    def out_dir_drc(self) -> Path:
        return self._top_dir.joinpath("drc")
    @property
    def out_dir_lvs(self) -> Path:
        return self._top_dir.joinpath("lvs")
    
    def create_export_task(self, *,
        spice_params_cb: Callable[[], SpicePrimsParamSpec], layerprops_filename: Optional[str]=None,
        extra_filedep: Iterable[Union[str, Path]]=(), extra_taskdep: Iterable[str]=(),
    ) -> KlayoutExportTaskT:
        return _KlayoutExportTask(
            manager=self, spice_params_cb=spice_params_cb, layerprops_filename=layerprops_filename,
            extra_filedep=tuple(extra_filedep), extra_taskdep=tuple(extra_taskdep),
        )

    def create_gds_task(self, *,
        extra_filedep: Iterable[Union[str, Path]]=(),
        extra_filedep_lib: Dict[str, Tuple[Path, ...]]={},
        extra_taskdep: Iterable[str]=(),
    ) -> KLayoutGDSTaskT:
        return _KlayoutGDSTask(
            manager=self, extra_filedep=tuple(extra_filedep), extra_filedep_lib=extra_filedep_lib,
            extra_taskdep=tuple(extra_taskdep),
        )

    def create_drc_task(self, *,
        waive_func: Optional[Callable[[str, str, ET.Element], bool]]=None,
        extra_filedep: Iterable[Union[str, Path]]=(),
        extra_taskdep: Iterable[str]=(),
    ) -> KLayoutDRCTaskT:
        return _KLayoutDRCTask(
            manager=self, waive_func=waive_func,
            extra_filedep=tuple(extra_filedep), extra_taskdep=tuple(extra_taskdep),
        )

    def create_lvs_task(self, *,
        extra_filedep: Iterable[Union[str, Path]]=(),
        extra_taskdep: Iterable[str]=(),
    ) -> KLayoutLVSTaskT:
        return _KLayoutLVSTask(
            manager=self,
            extra_filedep=tuple(extra_filedep), extra_taskdep=tuple(extra_taskdep),
        )

    def task_func_signoff(self):
        "Run all DRC and LVS checks"
        return {
            "task_dep": (self._task_name_drc, self._task_name_lvs),
            "actions": tuple(),
            "clean": (f"rm -fr {self.out_dir_drc} {self.out_dir_lvs}",),
        }
