# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
"""The pdkmaster.design.layout module provides classes to represent layout shapes
in a PDKMaster technology. These classes are designed to only allow to create
layout that conform to the technology definition. In order to detect design
shorts as fast as possible shapes are put on nets.

A LayoutFactory class is provided to generate layouts for a certain technology and
it's primitives.

Internally the klayout API is used to represent the shapes and perform manipulations
on them.
"""
from .layout_ import *
from .factory_ import *
from ._circuitlayouter import *
