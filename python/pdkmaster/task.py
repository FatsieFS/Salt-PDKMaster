# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
"""This a module to support creation of tasks to perform certain operation. One the main driver is
common code for doit's dodo.py in sevetal projects.
"""
import os
from pathlib import Path
import abc
from typing import Dict, Collection, Optional, Union, Callable, overload

try:
    import doit
except: # pragma: no cover
    has_doit = False
else:
    has_doit = True

from .technology import technology_ as _tch
from .design import library as _lbry


__all__ = ["get_var_env", "OpenPDKTree", "TaskManager"]


@overload
def get_var_env(name: str, default: None=None) -> Optional[str]:
    ... # pragma: no cover
@overload
def get_var_env(name: str, default: str) -> str:
    ... # pragma: no cover
def get_var_env(name: str, default: Optional[str]=None) -> Optional[str]:
    """Function to get environment which optionally could also provided as doit
    command line argument. When `doit` module is available it's `get_var` function
    will be used to override default or shell environment variable.
    environment variables for default value.
    If os.environ[name.upper()] exists that value will override the
    provided default value.
    """
    try:
        default = os.environ[name.upper()]
    except:
        # Keep the specified default
        pass
    if has_doit:
        ret = doit.get_var(name)
        # get_var returns None all the time if not run inside doit
        return ret if ret is not None else default
    else: # pragma: no cover
        return default


class OpenPDKTree():
    """This is a support class to manage a tree of directory and file names for the ad-hoc standard
    for these files. This is meant to be used by different tasks to agree on placement of certain
    files.
    """
    def __init__(self, *,
        top: Path, pdk_name: str,
    ) -> None:
        self._top = top
        self._pdk_name = pdk_name

        self._tech_dir = top.joinpath(pdk_name, "libs.tech")
        self._ref_dir = top.joinpath(pdk_name, "libs.ref")

    @property
    def top(self) -> Path:
        return self._top
    @property
    def pdk_name(self) -> str:
        return self._pdk_name

    def tool_dir(self, *, tool_name: str) -> Path:
        return self._tech_dir.joinpath(tool_name)

    def views_dir(self, *, lib_name: str, view_name: str) -> Path:
        return self._ref_dir.joinpath(lib_name, view_name)

    def task_func(self):
        """Create open_pdk dir"""
        # This is separate task so we can clean up full open_pdk directory

        return {
            "title": lambda _: "Creating open_pdk directory",
            "targets": (self.top,),
            "actions": (
                (self.top.mkdir, None, dict(parents=True, exist_ok=True)),
            ),
            "clean": (f"rm -fr {str(self.top)}",),
        }


class TaskManager(abc.ABC):
    @abc.abstractmethod
    def __init__(self, *,
        tech_cb: Callable[[], _tch.Technology],
        export_techname: Optional[str],
        lib4name_cb: Callable[[str], _lbry.Library],
        cell_list: Dict[str, Collection[str]],
        top_dir: Path, openpdk_tree: OpenPDKTree,
    ) -> None:
        # We work with callback functions so that technology does not need to be
        # generated as task creation time and only at
        self._tech_cb = tech_cb
        self._export_techname = export_techname
        self._lib4name_cb = lib4name_cb
        self._cell_list = cell_list
        self._top_dir = top_dir
        self._openpdk_tree = openpdk_tree

    @property
    def tech(self) -> _tch.Technology:
        return self._tech_cb()
    @property
    def export_techname(self) -> str:
        name = self._export_techname
        return name if name is not None else self.tech.name
    @property
    def cell_list(self) -> Dict[str, Collection[str]]:
        return self._cell_list

    def lib4name(self, lib_name: str) -> _lbry.Library:
        return self._lib4name_cb(lib_name)
    def cells4lib(self, lib: Union[str, _lbry.Library]):
        if isinstance(lib, _lbry.Library):
            lib = lib.name
        return self._cell_list[lib]
