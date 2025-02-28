# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
import os
from pathlib import Path
from textwrap import dedent
from typing import Tuple, Dict, Iterable, Collection, Union, Optional, Callable

from doit.action import BaseAction, CmdAction

from pdkmaster.typing import MultiT, cast_MultiT, OptMultiT, cast_OptMultiT
from pdkmaster.task import get_var_env, OpenPDKTree, TaskManager as _PDKMasterTaskManager
from pdkmaster.technology import technology_ as _tch
from pdkmaster.design import library as _lbry


__all__ = [
    "LibertyCornerDataT",
    "AVTScriptAction",
    "RTLTaskT", "LibertyTaskT", "TaskManager",
]


LibertyCornerDataT = Dict[str, Dict[str, Tuple[float, float, Collection[Path]]]]


class AVTScriptAction(BaseAction):
    def __init__(self, *, avt_script: str, work_dir: Path, mkdirs: MultiT[Path]=(), avt_shell: Optional[str]=None):
        if avt_shell is None:
            avt_shell = get_var_env("avt_shell", default="/bin/env avt_shell")

        self.script = avt_script
        self._work_dir = work_dir
        self.mkdirs = cast_MultiT(mkdirs)
        self.avt_shell = avt_shell

        self.out = None
        self.err = None
        self.result = None
        self.values = {}

    def execute(self, out=None, err=None): # pragma: no cover
        # Create new action on every new call so we can always write
        # the script to the stdin of the subprocess.
        for d in (self._work_dir, *self.mkdirs):
            d.mkdir(parents=True, exist_ok=True)

        pr, pw = os.pipe()
        fpw = os.fdopen(pw, "w")
        fpw.write(self.script)
        fpw.close()

        action = CmdAction(self.avt_shell, stdin=pr, cwd=self._work_dir)

        r = action.execute(out=out, err=err)
        self.values = action.values
        self.result = action.result
        self.out = action.out
        self.err = action.err
        return r


#
# VHDL/Verilog
class _RTLTask:
    "Task for creating verilog/VHDL from spice netlist using HiTAS/Yagle"
    def __init__(self, *,
        manager: "TaskManager", task_name: str, work_dir: Path, override_dir: Optional[Path],
        libs: Tuple[str, ...], spice_model_files: Tuple[Path, ...],
        extra_filedep: Tuple[Union[str, Path], ...], extra_taskdep: Tuple[str, ...],
        avt_shell: Optional[str]=None,
    ) -> None:
        self._mng = manager
        self._task_name = task_name
        self._work_dir = work_dir
        self._override_dir = override_dir
        self._libs = libs
        assert spice_model_files
        self._spice_model_files = spice_model_files
        self._extra_filedep = extra_filedep
        self._extra_taskdep = extra_taskdep
        self._avt_shell = avt_shell

    def _rtl_script(self, lib, lang):
        mng = self._mng
        openpdk_tree = mng._openpdk_tree

        spice_dir = openpdk_tree.views_dir(lib_name=lib, view_name="spice")
        spice_file = spice_dir.joinpath(f"{lib}_baser.spi")
        out_dir = openpdk_tree.views_dir(lib_name=lib, view_name=lang)
        out_dir.mkdir(parents=True, exist_ok=True)

        avt_shell_script = dedent(f"""\
            avt_config simToolModel hspice
            avt_config avtVddName "vdd:iovdd"
            avt_config avtVssName "vss:iovss"
            avt_config yagNoSupply "yes"
        """)
        if mng._spice_models_dir is not None:
            avt_shell_script += f'avt_config avtLibraryDirs "{mng._spice_models_dir}"\n'
        avt_shell_script += "".join(
            f'avt_LoadFile "{spice_model_file}" spice\n'
            for spice_model_file in self._spice_model_files
        ) + f'avt_LoadFile "{spice_file}" spice\n'

        if lang == "verilog":
            suffix = ".v"
            avt_shell_script += dedent("""\
                avt_config avtOutputBehaviorFormat "vlg"
                set suffix v
                set comment "//"
            """)
        elif lang == "vhdl":
            suffix = ".vhdl"
            avt_shell_script += dedent("""\
                avt_config avtOutputBehaviorFormat "vhd"
                set suffix vhd
                set comment "--"
            """)
        else:
            raise NotImplementedError(f"rtl lang {lang}")

        avt_shell_script += "foreach cell {\n"
        cells = mng.cells4lib(lib)
        for cell in cells:
            avt_shell_script += f"    {cell}\n"
        avt_shell_script += dedent(f"""\
            }} {{
                set rtl_file "{out_dir}/${{cell}}{suffix}"
        """)
        avt_shell_script += dedent("""\
                if {[string match "dff*" $cell]} {
                    inf_SetFigureName $cell
                    inf_MarkSignal dff_m "FLIPFLOP+MASTER"
                    inf_MarkSignal dff_s SLAVE
                }
                set out_file "$cell.$suffix"
                yagle $cell
                if [file exists $out_file] {
                    file copy -force $out_file $rtl_file
                } else {
                    set f [open $rtl_file w]
                    puts $f "$comment no model for $cell"
                }
            }
        """)

        return avt_shell_script

    def _rtl_override(self, lib, lang): # pragma: no cover
        """Override some of the verilog file with some hard coded ones.

        Needed as Yagle does not seem to understand the zero/one cell.
        """
        mng = self._mng
        openpdk_tree = mng._openpdk_tree

        if self._override_dir is not None:
            override_lang_dir = self._override_dir.joinpath(lib, lang)
            if override_lang_dir.exists():
                rtl_lang_dir = openpdk_tree.views_dir(lib_name=lib, view_name=lang)
                os.system(f"cp {str(override_lang_dir)}/* {str(rtl_lang_dir)}")

    def task_func(self):
        """Generate VHDL/verilog files"""
        mng = self._mng
        openpdk_tree = mng._openpdk_tree

        langs = ("vhdl", "verilog")

        def rtl_targets(lib: str, lang: str):
            suffix = {
                "vhdl": "vhdl",
                "verilog": "v",
            }[lang]

            tgts = []
            cells = mng.cells4lib(lib)
            out_dir = openpdk_tree.views_dir(lib_name=lib, view_name=lang)
            for cell in cells:
                tgts.append(out_dir.joinpath(f"{cell}.{suffix}"))
            return tuple(tgts)

        def rtl_title(task):
            return f"Creating {task.name[4:]} files"

        for lib in self._libs:
            spice_dir = openpdk_tree.views_dir(lib_name=lib, view_name="spice")
            spice_file = spice_dir.joinpath(f"{lib}_baser.spi")

            docstrings = {
                "vhdl": f"Generate VHDL files for lib {lib}",
                "verilog": f"Generate Verilog files for lib {lib}",
            }
            for lang in langs:
                yield {
                    "name": f"{lib}:{lang}",
                    "doc": docstrings[lang],
                    "title": rtl_title,
                    "file_dep": (*self._spice_model_files, spice_file, *self._extra_filedep),
                    "task_dep": self._extra_taskdep,
                    "targets": rtl_targets(lib, lang),
                    "actions": (
                        AVTScriptAction(
                            avt_script=self._rtl_script(lib, lang), work_dir=self._work_dir,
                            mkdirs=openpdk_tree.views_dir(lib_name=lib, view_name=lang),
                            avt_shell=self._avt_shell,
                        ),
                        (self._rtl_override, (lib, lang)),
                    )
                }
            yield {
                "name": lib,
                "doc": f"Generate RTL files for lib {lib}",
                "task_dep": tuple(f"{self._task_name}:{lib}:{lang}" for lang in langs),
                "actions": None,
            }
        docstrings = {
            "vhdl": f"Generate VHDL files for all libs",
            "verilog": f"Generate Verilog files for all libs",
        }
        for lang in langs:
            yield {
                "name": lang,
                "doc": docstrings[lang],
                "task_dep": tuple(f"{self._task_name}:{lib}:{lang}" for lib in self._libs),
                "actions": None,
            }
RTLTaskT = _RTLTask


#
# liberty
class _LibertyTask:
    """Task for creating liberty file from a SPICE netlist

    Currently only standard cells generated using c4m.flexcell are supported.
    """
    def __init__(self, *,
        manager: "TaskManager", work_dir: Path, corner_data: LibertyCornerDataT,
        rtl_task_name: str,
        extra_filedep: Tuple[Union[str, Path], ...], extra_taskdep: Tuple[str, ...],
        avt_shell: Optional[str]=None,
    ) -> None:
        self._mng = manager
        self._work_dir = work_dir
        assert corner_data
        self._libs = tuple(corner_data.keys())
        self._corner_data = corner_data
        self._rtl_task_name = rtl_task_name
        self._extra_filedep = extra_filedep
        self._extra_taskdep = extra_taskdep
        self._avt_shell = avt_shell

    def _liberty_title(self, task):
        lib, corner = task.name[8:].split("_")
        return f"Creating liberty files for library {lib}, corner {corner}"

    def _liberty_script(self,
            lib: str, corner: str, voltage: float, temp: float, model_files: Collection[Path],
        ):
        assert "stdcell" in lib.lower(), "Unsupported lib"

        mng = self._mng
        openpdk_tree = mng._openpdk_tree

        avt_script = dedent(f"""\
            avt_config simToolModel hspice
            avt_config avtVddName "vdd:iovdd"
            avt_config avtVssName "vss:iovss"
            avt_config tasBefig yes
            avt_config tmaDriveCapaout yes
            avt_config avtPowerCalculation yes
            avt_config simSlope 20e-12
            avt_config simPowerSupply {voltage:.2f}
            avt_config simTemperature {temp:.1f}
        """)
        if mng._spice_models_dir is not None:
            avt_script += f'avt_config avtLibraryDirs "{mng._spice_models_dir}"\n'
        avt_script += "".join(
            f'avt_LoadFile "{model_file}" spice\n'
            for model_file in model_files
        )
        spice_file = openpdk_tree.views_dir(lib_name=lib, view_name="spice").joinpath(f"{lib}_baser.spi")
        avt_script += dedent(f"""\
            avt_config tmaLibraryName {lib}_{corner}
            avt_LoadFile {spice_file} spice

            foreach cell {{
        """)
        avt_script += "".join(
            f"    {cell}\n"
            for cell in filter(
                lambda s: s != "Gallery",
                mng.cells4lib(lib),
            )
        )
        verilog_dir = openpdk_tree.views_dir(lib_name=lib, view_name="verilog")
        liberty_dir = openpdk_tree.views_dir(lib_name=lib, view_name="liberty")
        liberty_file_raw = liberty_dir.joinpath(f"{lib}_{corner}_raw.lib")
        avt_script += dedent(f"""\
            }} {{
                set verilogfile {verilog_dir}/$cell.v

                if {{[string match "dff*" $cell]}} {{
                    # TODO: make these settings configurable
                    set beh_fig NULL
                    inf_SetFigureName $cell
                    inf_MarkSignal dff_m "MASTER"
                    inf_MarkSignal dff_s "FLIPFLOP+SLAVE"
                    create_clock -period 3000 clk
                }} elseif {{[string match "*latch*" $cell]}} {{
                    set beh_fig NULL
                }} else {{
                    set beh_fig [avt_LoadBehavior $verilogfile verilog]
                }}
                set tma_fig [tma_abstract [hitas $cell] $beh_fig]

                lappend tma_list $tma_fig
                lappend beh_list $beh_fig
            }}

            lib_drivefile $tma_list $beh_list "{liberty_file_raw}" max
        """)

        return avt_script

    def _fix_lib(self, lib, corner): # pragma: no cover
        import re

        mng = self._mng
        openpdk_tree = mng._openpdk_tree

        cell_pattern = re.compile(r'\s*cell\s*\((?P<cell>\w+)\)\s*\{')
        # area_pattern = re.compile(r'(?P<area>\s*area\s*:\s*)\d+.\d+\s*;')
        qpin_pattern = re.compile(r'\s*pin\s*\(q\)\s*\{')
        clkpin_pattern = re.compile(r'\s*pin\s*\(clk\)\s*\{')

        liberty_dir = openpdk_tree.views_dir(lib_name=lib, view_name="liberty")
        liberty_file_raw = liberty_dir.joinpath(f"{lib}_{corner}_raw.lib")
        liberty_file = liberty_dir.joinpath(f"{lib}_{corner}.lib")
        with liberty_file_raw.open("r") as fin:
            with liberty_file.open("w") as fout:
                is_flipflop = False
                for line in fin:

                    # In current one/zero cells output pins are wrongly seen as inout
                    # TODO: Check if we can fix that during HiTAS/Yagle run
                    line = line.replace("direction : inout", "direction : output")

                    m = cell_pattern.match(line)
                    if m:
                        cell = m.group("cell")
                        is_flipflop = cell.startswith("dff")
                        has_reset = cell.startswith("dffnr")
                        if is_flipflop:
                            fout.write(line)
                            fout.write('        ff (IQ,IQN) {\n')
                            fout.write('            next_state : "i" ;\n')
                            fout.write('            clocked_on : "clk" ;\n')
                            if has_reset:
                                fout.write('            clear : "nrst\'" ;\n')
                            fout.write('        }\n')
                            continue
                    elif is_flipflop:
                        m = qpin_pattern.match(line)
                        if m:
                            fout.write(line)
                            fout.write('            function : "IQ" ;\n')
                            continue

                        m = clkpin_pattern.match(line)
                        if m:
                            fout.write(line)
                            fout.write('            clock : true ;\n')
                            continue

                    fout.write(line)

    def task_func(self):
        """Generate liberty files"""
        mng = self._mng
        openpdk_tree = mng._openpdk_tree

        for lib, data in self._corner_data.items():
            liberty_dir = openpdk_tree.views_dir(lib_name=lib, view_name="liberty")

            for corner, corner_data in data.items():
                model_files = corner_data[2]
                tmp = self._work_dir.joinpath(f"{lib}_{corner}")
                spice_dir = openpdk_tree.views_dir(lib_name=lib, view_name="spice")
                spice_file = spice_dir.joinpath(f"{lib}_baser.spi")
                liberty_file = liberty_dir.joinpath(f"{lib}_{corner}.lib")
                yield {
                    "name": f"{lib}_{corner}",
                    "doc": f"Generate liberty file for {lib}; {corner} corner",
                    "title": self._liberty_title,
                    "file_dep": (
                        *model_files, spice_file, *self._extra_filedep,
                    ),
                    "task_dep": (
                        *self._extra_taskdep,
                        f"spice:{lib}", f"{self._rtl_task_name}:{lib}:verilog",
                    ),
                    "targets": (liberty_file,),
                    "actions": (
                        AVTScriptAction(
                            avt_script=self._liberty_script(lib, corner, *corner_data),
                            work_dir=tmp, mkdirs=(tmp, liberty_dir),
                            avt_shell=self._avt_shell,
                        ),
                        (self._fix_lib, (lib, corner)),
                    ),
                }
LibertyTaskT = _LibertyTask


class TaskManager(_PDKMasterTaskManager):
    def __init__(self, *,
        tech_cb: Callable[[], _tch.Technology],
        lib4name_cb: Callable[[str], _lbry.Library],
        cell_list: Dict[str, Collection[str]],
        top_dir: Path, openpdk_tree: OpenPDKTree,
        spice_models_dir: Optional[Path]=None,
    ) -> None:
        super().__init__(
            tech_cb=tech_cb, lib4name_cb=lib4name_cb, cell_list=cell_list,
            top_dir=top_dir, openpdk_tree=openpdk_tree,
        )
        self._tech_dir = tech_dir = openpdk_tree.tool_dir(tool_name="klayout")
        self._drc_dir = tech_dir.joinpath("drc")
        self._lvs_dir = tech_dir.joinpath("lvs")
        self._share_dir = tech_dir.joinpath("share")
        self._bin_dir = tech_dir.joinpath("bin")
        self._spice_models_dir = spice_models_dir

        self._src_deps = (Path(__file__))

    @property
    def out_dir_drc(self) -> Path:
        return self._top_dir.joinpath("drc")
    @property
    def out_dir_lvs(self) -> Path:
        return self._top_dir.joinpath("lvs")

    def create_rtl_task(self, *,
        task_name: str="rtl", work_dir: Path, override_dir: Optional[Path]=None, libs: OptMultiT[str]=None,
        spice_model_files: MultiT[Path],
        extra_filedep: Iterable[Union[str, Path]]=(), extra_taskdep: Iterable[str]=(),
    ) -> RTLTaskT:
        libs = cast_OptMultiT(libs)
        if libs is None:
            libs = tuple(self.cell_list.keys())
        assert libs

        return _RTLTask(
            manager=self, task_name=task_name, work_dir=work_dir, override_dir=override_dir, libs=libs,
            spice_model_files=cast_MultiT(spice_model_files),
            extra_filedep=tuple(extra_filedep), extra_taskdep=tuple(extra_taskdep),
        )

    def create_liberty_task(self, *,
        work_dir: Path, corner_data: LibertyCornerDataT,
        rtl_task_name: str="rtl",
        extra_filedep: Iterable[Union[str, Path]]=(), extra_taskdep: Iterable[str]=(),
    ) -> LibertyTaskT:
        return _LibertyTask(
            manager=self, work_dir=work_dir, corner_data=corner_data,
            rtl_task_name=rtl_task_name,
            extra_filedep=tuple(extra_filedep), extra_taskdep=tuple(extra_taskdep),
        )
