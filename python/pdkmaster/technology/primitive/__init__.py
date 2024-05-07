# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
"""The primitive defines the building blocks a technology

API Notes:
    This module provides several type aliases which names end with a T. No backwards
        compatibility is guaranteed for any else than type annotations.
"""
from ._core import *
from ._derived import *
from .layers import *
from .conductors import *
from .devices import *
from .rules import *
