# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
def _sanitize_name(name):
    return name.replace("(", "[").replace(")", "]")
