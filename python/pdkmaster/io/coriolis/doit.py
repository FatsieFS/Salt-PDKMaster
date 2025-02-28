# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
# module for support for coriolis related doit tasks
import sys
from pathlib import Path
from shutil import rmtree, copytree
from typing import Dict, Tuple, Collection, Callable, Any

from pdkmaster.task import OpenPDKTree, TaskManager as _PDKMasterTaskManager
from pdkmaster.design import library as _lbry
from pdkmaster.technology import technology_ as _tch


__all__ = ["UpstreamPDKTaskT", "TaskManager"]


class UpstreamPDKTaskT:
    def __init__(self, *,
        manager: "TaskManager", alliancectk_co_dir: Path, openpdk_task: str,
        extra_filedep: Tuple[Path, ...], extra_taskdep: Tuple[str, ...],
    ):
        self._mng = manager
        self._co_dir = alliancectk_co_dir
        self._openpdk_task = openpdk_task
        self._extra_filedep = extra_filedep
        self._extra_taskdep = extra_taskdep

    def _copy_pdk(self):
        "Copy PDK into the upstream"
        mng = self._mng
        tree = mng._openpdk_tree
        co_dir = self._co_dir
        pdkmaster_dir = co_dir.joinpath("pdkmaster")
        tech_dir = pdkmaster_dir.joinpath(mng.pdk_name)

        if not pdkmaster_dir.exists():
            raise RuntimeError(f"{pdkmaster_dir} does not exists; maybe a git submodule need to be initialized")

        if tech_dir.exists():
            rmtree(tech_dir)
        
        copytree(src=tree.pdk_dir, dst=tech_dir)

        print("Files copied; need to submit it now", sys.stderr)
        
    def task_func(self) -> Dict[str, Any]:
        "Copy PDK into upstream repository"
        mng = self._mng
        tree = mng._openpdk_tree

        co_dir = self._co_dir

        return {
            "title": lambda _: self.task_func.__doc__,
            "file_dep": self._extra_filedep,
            "task_dep": (self._openpdk_task, *self._extra_taskdep),
            "targets": (co_dir.joinpath(tree.pdk_name),),
            "actions": (
                self._copy_pdk,
            ),
        }


class TaskManager(_PDKMasterTaskManager):
    def __init__(self, *,
        tech_cb: Callable[[], _tch.Technology], lib4name_cb: Callable[[str], _lbry.Library],
        cell_list: Dict[str, Collection[str]],
        top_dir: Path, openpdk_tree: OpenPDKTree,
    ) -> None:
        super().__init__(
            tech_cb=tech_cb, lib4name_cb=lib4name_cb,
            cell_list=cell_list, top_dir=top_dir, openpdk_tree=openpdk_tree,
        )

    def create_upstreampdk_task(self, *,
        alliancectk_co_dir: Path, openpdk_task: str,
        extra_filedep: Tuple[Path, ...]=(), extra_taskdep: Tuple[str, ...]=(),
    ) -> UpstreamPDKTaskT:
        return UpstreamPDKTaskT(
            manager=self, alliancectk_co_dir=alliancectk_co_dir, openpdk_task=openpdk_task,
            extra_filedep=extra_filedep, extra_taskdep=extra_taskdep,
        )
