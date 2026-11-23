#!/usr/bin/env python3
# Lists all translatable strings _("...") in the plugin source. Copyright (C) 2026 CamAlert developers, GPL v2.
import ast
import glob
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..", "src", "CamAlert")


def strings():
    found = []
    for p in sorted(glob.glob(os.path.join(ROOT, "*.py"))):
        for m in re.finditer(r'\b_\(("(?:[^"\\]|\\.)*")\)', open(p, encoding="utf-8").read()):
            s = ast.literal_eval(m.group(1))
            if s not in found:
                found.append(s)
    return found


def pot():
    out = ['msgid ""', 'msgstr ""', '"Content-Type: text/plain; charset=UTF-8\\n"', ""]
    for s in strings():
        out += ["msgid %s" % _q(s), 'msgstr ""', ""]
    return "\n".join(out)


def _q(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


if __name__ == "__main__":
    sys.stdout.write(pot())
