#!/usr/bin/env python3
# Minimal .po -> .mo compiler (no gettext tools needed). Copyright (C) 2026 DoorCam developers, GPL v2.
import ast
import struct
import sys


def parse_po(text):
    entries, msgid, msgstr, section = {}, None, None, None
    for line in text.splitlines() + [""]:
        line = line.strip()
        if line.startswith("msgid "):
            if msgid is not None and msgstr is not None:
                entries[msgid] = msgstr
            msgid, msgstr, section = ast.literal_eval(line[6:]), None, "id"
        elif line.startswith("msgstr "):
            msgstr, section = ast.literal_eval(line[7:]), "str"
        elif line.startswith('"'):
            if section == "id":
                msgid += ast.literal_eval(line)
            elif section == "str":
                msgstr += ast.literal_eval(line)
        elif not line and msgid is not None and msgstr is not None:
            entries[msgid] = msgstr
            msgid = msgstr = section = None
    return {k: v for k, v in entries.items() if v or k == ""}


def make_mo(entries):
    keys = sorted(entries)
    ids = b"".join(k.encode() + b"\0" for k in keys)
    strs = b"".join(entries[k].encode() + b"\0" for k in keys)
    n = len(keys)
    offsets, o = [], 0
    for k in keys:
        offsets.append((len(k.encode()), o)); o += len(k.encode()) + 1
    soffsets, o = [], 0
    for k in keys:
        soffsets.append((len(entries[k].encode()), o)); o += len(entries[k].encode()) + 1
    start = 7 * 4 + 16 * n
    out = struct.pack("Iiiiiii", 0x950412de, 0, n, 7 * 4, 7 * 4 + 8 * n, 0, 0)
    for length, off in offsets:
        out += struct.pack("ii", length, start + off)
    for length, off in soffsets:
        out += struct.pack("ii", length, start + len(ids) + off)
    return out + ids + strs


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as f:
        mo = make_mo(parse_po(f.read()))
    with open(sys.argv[2], "wb") as f:
        f.write(mo)
