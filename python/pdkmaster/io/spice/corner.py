# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
"This module provides support classes to define the SPICE simulation corners."
from typing import Tuple, Dict, Iterable

from ...typing import MultiT, cast_MultiT

@dataty
"""CornerSetT is a set of corner names.
corner names that are present in the same set are conflicting with each other
e.g. ("typ", "ff", "ss") means one can use either "typ", "ff", "ss" in a SPICE
simulation
"""
class CornerSet(Tuple[str, ...]):
    def __init__(self, __iterable: MultiT[str]):
        super().__init__(cast_MultiT(__iterable))


"""CornerFileSets
"""
class SpiceLibCorners(Dict[Tuple[str, ...], Tuple[CornerSet]]):
    def __init__(self, __iterable: Iterable[Tuple[]])
