#!/usr/bin/env python3
# Lists all translatable strings: _("...") in the plugin source and N_("...") in the shared core (texts the core
# hands to the players, #41). Copyright (C) 2026 CamAlert developers, GPL v2.
# Translations live in the master catalogue core/i18n/ (tools/i18n/i18n.py), not in po/ (generated).
import ast
import glob
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..", "players", "enigma2", "CamAlert")
CORE = os.path.join(os.path.dirname(__file__), "..", "core", "camalert_core")


def _scan(paths, marker):
    found = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            text = f.read()
        for m in re.finditer(r'(?<![\w.])' + marker + r'\(\s*("(?:[^"\\]|\\.)*")\s*\)', text):
            s = ast.literal_eval(m.group(1))
            if s not in found:
                found.append(s)
    return found


def core_strings():
    """N_("...") texts of the core, in file order."""
    paths = sorted(glob.glob(os.path.join(CORE, "*.py")) + glob.glob(os.path.join(CORE, "*", "*.py")))
    return _scan(paths, "N_")


def strings():
    found = _scan(sorted(glob.glob(os.path.join(ROOT, "*.py"))), "_")
    return found + [s for s in core_strings() if s not in found]


def pot():
    out = ['msgid ""', 'msgstr ""', '"Content-Type: text/plain; charset=UTF-8\\n"', ""]
    for s in strings():
        out += ["msgid %s" % _q(s), 'msgstr ""', ""]
    return "\n".join(out)


def _q(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


if __name__ == "__main__":
    sys.stdout.write(pot())
