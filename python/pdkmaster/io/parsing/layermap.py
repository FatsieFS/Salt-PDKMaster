# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
__all__ = ["LayerMap"]


class LayerMap:
    def __init__(self, spec):
        self.value = spec

    @staticmethod
    def parse_string(text):
        def filter_line(line):
            s = line.strip()
            return (len(s) > 0) and (s[0] != "#")

        def parse_line(line):
            words = line.split()
            if len(words) != 4:
                raise ValueError(f"Number of words in '{line}' is not 4")
            layer = words[0] if words[1] == "drawing" else f"{words[0]}.{words[1]}"
            gds_layer = (int(words[2]), int(words[3]))
            return (layer, gds_layer)

        return LayerMap(
            tuple(parse_line(line) for line in filter(filter_line, text.splitlines()))
        )
