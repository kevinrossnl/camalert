#!/usr/bin/env python3
"""Generated parts of the docs (#47): key table, glossary and settings table come from core, never by hand.

    python3 tools/docs.py update    rewrite the generated blocks
    python3 tools/docs.py check     exit 1 if a generated block is out of date (tests/test_docs.py runs this)

A generated block sits between  <!-- BEGIN generated: <name> (tools/docs.py) -->  and  <!-- END generated: <name> -->
in a Markdown file; everything outside the markers is written by hand.
Sources: core/camalert_core/keymap.py + present.py (keys), core/i18n/glossary.json (glossary),
core/camalert_core/schema.py (settings). Copyright (C) 2026 CamAlert developers, GPL v2.
"""
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "core"))
from camalert_core import keymap, present, schema  # noqa: E402

LANGS = ("nl", "de", "fr", "it", "pl")
PLAYER_NAMES = {"enigma2": "Enigma2", "kodi": "Kodi", "androidtv": "Android TV"}
KEY_COLUMNS = ("enigma2", "kodi", "androidtv")  # column order of the key table
CONTEXT_TITLES = {"window": "Photo window and multi-camera window", "ptz": "Camera control (PTZ)", "tour": "Tour",
                  "mosaic": "Mosaic", "live": "Live view",
                  "actions": "Action menu (Android TV: MENU)"}
SECTION_TITLES = {"general": "General", "display": "Display", "rules": "Rules", "triggers": "Triggers",
                  "camera_control": "Camera control", "home_assistant": "Home Assistant / MQTT", "api": "API",
                  "channels": "Channel list (Enigma2)", "log": "Log and diagnostics"}


def _tr(text):
    return text


def _keys(player, context, action):
    names = []
    for key in keymap.KEYMAP[player][context].get(action, ()):
        name = present.KEY_NAMES[player].get(key)
        if name and name not in names:
            names.append(name)
    return " / ".join(names)


def keys_block():
    out = []
    cols = [p for p in KEY_COLUMNS if p in keymap.KEYMAP]
    empty = ["–"] * len(cols)
    for context in keymap.CONTEXTS:
        out += ["### " + CONTEXT_TITLES[context], "", "| Action | %s |" % " | ".join(PLAYER_NAMES[p] for p in cols),
                "|---|" + "---|" * len(cols)]
        for actions, label in present.HINTS[context]:
            row = []
            for player in cols:
                cell = ", ".join(x for x in (_keys(player, context, a) for a in actions) if x)
                if actions == ("ptz",):
                    cell = "PTZ colour key" + (" / " + cell if cell else "")
                if actions == ("leave",):
                    cell += " / PTZ colour key"
                row.append(cell or "–")
            if row != empty:
                out.append("| %s | %s |" % (label, " | ".join(row)))
        if context == "live":
            out.append("| (Enigma2: the camera is a normal channel; zap away or wait) | %s |" % " | ".join(empty))
        if any(keymap.KEYMAP[p][context].get("pass") for p in cols):
            out.append("| keep working | %s |" % " | ".join(["volume, mute"] * len(cols)))
        out.append("")
    out += ["Kodi's skin fonts have no ◀ ▶: its on-screen hints show `< >` and `^ v` instead.",
            "The *PTZ colour key* is the colour key chosen in *Camera control (PTZ) key* (default BLUE); it only",
            "switches camera control on for cameras with PTZ. Fire TV remotes have no colour keys: there MENU",
            "switches camera control on, FF/REW zoom and PLAY/PAUSE starts live view in the tour.", ""]
    return "\n".join(out)


def _avoid(pattern):
    p = pattern.replace("\\b", "").replace("-?", "-").replace("s?", "(s)")
    return re.sub(r"[\\^$]", "", p)


def glossary_block():
    g = json.load(open(os.path.join(ROOT, "core", "i18n", "glossary.json"), encoding="utf-8"))
    out = ["| Term | Meaning | " + " | ".join(LANGS) + " |", "|---|---|" + "---|" * len(LANGS)]
    for t in g["terms"]:
        out.append("| **%s** | %s | %s |" % (t["en"], t["definition"], " | ".join(t[lang] for lang in LANGS)))
    out += ["", "Do not use (the docs test and the translation check refuse them):", ""]
    for rule in g["forbidden"].get("en", []):
        out.append("- ~~%s~~ → *%s*" % (_avoid(rule["pattern"]), rule["use"]))
    out += ["- *receiver* when Kodi is meant too → *player* (\"Enigma2 receiver\" is fine)", "",
            "Tone of the translations: " + ", ".join("%s *%s*" % (k, v) for k, v in g["tone"].items()) + ".", ""]
    return "\n".join(out)


def _default(s):
    if s.type == "bool":
        return "Yes" if s.default else "No"
    if s.default in ("", None):
        return "–"
    if s.type == "password":
        return "–"
    text = "`%s`%s" % (s.default, (" " + s.unit) if s.unit and s.unit != "%" else (s.unit or ""))
    # a player with its own default (#67), e.g. live volume 0 on Android TV
    own = ["%s: `%s`" % (PLAYER_NAMES[p], v) for p, v in sorted(s.defaults.items()) if p in s.platforms]
    return text + ("".join(" (%s)" % o for o in own))


def _values(s):
    if s.choices:
        return " / ".join("`%s`" % c for c in s.choices)
    if s.min is not None:
        step = (", step %s" % s.step) if s.step and s.step != 1 else ""
        return "%s–%s%s" % (s.min, s.max, step)
    return ""


def settings_block():
    out = []
    for section in schema.SECTIONS:
        rows = [s for s in schema.SETTINGS if s.section == section and s.level != "internal" and s.label]
        if not rows:
            continue
        out += ["### " + SECTION_TITLES[section], "", "| Setting | Default | Values | Level | Players | What it does |",
                "|---|---|---|---|---|---|"]
        for s in rows:
            players = "all" if set(s.platforms) == set(schema.PLATFORMS) else ", ".join(PLAYER_NAMES[p] for p in s.platforms)
            help_text = (s.help or "").replace("|", "\\|").replace("%s", "the camera file")
            out.append("| %s | %s | %s | %s | %s | %s |" % (s.label, _default(s), _values(s), s.level, players, help_text))
        out.append("")
    return "\n".join(out)


BLOCKS = {
    "docs/user/keys.md": {"keys": keys_block},
    "docs/user/glossary.md": {"glossary": glossary_block},
    "docs/user/settings.md": {"settings": settings_block},
}
BEGIN = "<!-- BEGIN generated: %s (tools/docs.py) -->"
END = "<!-- END generated: %s -->"


def render(path, text):
    for name, fn in BLOCKS[path].items():
        b, e = BEGIN % name, END % name
        if b not in text or e not in text:
            raise ValueError("%s: markers for %s missing" % (path, name))
        head, rest = text.split(b, 1)
        _, tail = rest.split(e, 1)
        text = head + b + "\n" + fn() + e + tail
    return text


def main(argv):
    mode = argv[0] if argv else "check"
    stale = []
    for rel in sorted(BLOCKS):
        path = os.path.join(ROOT, rel)
        text = open(path, encoding="utf-8").read()
        new = render(rel, text)
        if new != text:
            stale.append(rel)
            if mode == "update":
                open(path, "w", encoding="utf-8").write(new)
    for rel in stale:
        print(("updated " if mode == "update" else "out of date (run tools/docs.py update): ") + rel)
    return 1 if stale and mode != "update" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
