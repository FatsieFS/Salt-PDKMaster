# SPDX-License-Identifier: AGPL-3.0-or-later OR GPL-2.0-or-later OR CERN-OHL-S-2.0+ OR Apache-2.0
from .skill_grammar import SkillFile


__all__ = ["DisplayFile"]


#
# Grammar
#
class DisplayFile(SkillFile):
    def grammar_elem_init(self, sessiondata):
        super().grammar_elem_init(sessiondata)
        self.ast = {"DisplayFile": self.ast["SkillFile"]}
        self.value = {"DisplayFile": self.value["SkillFile"]}
