#!/usr/bin/env python3
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""One master translation catalogue for every user-facing text (#38, #43). Format: core/i18n/README.md.

    python3 tools/i18n/i18n.py update   refresh core/i18n/<lang>.po from the English sources (new texts get an
                                        empty msgstr, unused ones are dropped), then write every output
    python3 tools/i18n/i18n.py build    write the outputs only
    python3 tools/i18n/i18n.py check    exit 1 if a translation is missing, a placeholder differs, a forbidden
                                        synonym or tone is used, a glossary term is not used verbatim, or an
                                        output is not up to date (tests/test_i18n.py runs this)

English sources (where a text is written):
    e2    _("...") in players/enigma2/CamAlert/*.py and N_("...") in core/camalert_core (tools/strings.py)
    kodi  players/kodi/service.camalert/resources/language/resource.language.en_gb/strings.po (ids >= 30000;
          an id never changes meaning; N_() texts of the core get ids from KODI_CORE_IDS automatically)
    ha    custom_components/camalert/strings.json
Outputs (generated, do not edit by hand): po/CamAlert.pot, po/<lang>.po, Kodi resource.language.<ll_cc>/strings.po,
custom_components/camalert/translations/<lang>.json (en.json = strings.json).
"""
import ast
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import strings as e2strings  # noqa: E402

CAT = os.path.join(ROOT, "core", "i18n")
PO = os.path.join(ROOT, "po")
KODI_LANG = os.path.join(ROOT, "players", "kodi", "service.camalert", "resources", "language")
HA = os.path.join(ROOT, "custom_components", "camalert")
LANGS = ("nl", "de", "fr", "it", "pl")
KODI_CODES = {"en": "en_gb", "nl": "nl_nl", "de": "de_de", "fr": "fr_fr", "it": "it_it", "pl": "pl_pl"}
LANG_NAMES = {"en": "English", "nl": "Dutch", "de": "German", "fr": "French", "it": "Italian", "pl": "Polish"}
KODI_CORE_IDS = range(30500, 30700)  # Kodi ids for the core's N_() texts (#41), assigned by `update`
PLACEHOLDER = re.compile(r"%\([a-z_]+\)[sd]|%[sd]|\{[a-z_]+\}|\[%key:[^%]+%\]")


# --- po files -----------------------------------------------------------------------------------------------------
def q(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t") + '"'


def read_po(path):
    """[(msgctxt, msgid, msgstr, [comment lines])] in file order (the header entry is skipped)."""
    out, cur, field, comments = [], None, None, []
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines() + [""]
    for line in lines:
        s = line.strip()
        if s.startswith("#"):
            comments.append(line)
            continue
        m = re.match(r"^(msgctxt|msgid|msgstr) (\".*\")$", s)
        if m:
            if m.group(1) in ("msgctxt", "msgid") and cur is not None and "msgstr" in cur:
                out.append(cur)
                cur = None
            if cur is None:
                cur, comments = {"comments": comments}, []
            field = m.group(1)
            cur[field] = ast.literal_eval(m.group(2))
        elif s.startswith('"') and cur is not None and field:
            cur[field] += ast.literal_eval(s)
        elif not s:
            if cur is not None and "msgstr" in cur:
                out.append(cur)
            cur, field = None, None
            comments = [] if not s else comments
    return [(e.get("msgctxt", ""), e["msgid"], e["msgstr"], e["comments"]) for e in out if e["msgid"]]


def kodi_source():
    """[(id, English)] of the Kodi en_gb strings.po."""
    path = os.path.join(KODI_LANG, "resource.language.en_gb", "strings.po")
    return [(int(c[1:]), i) for c, i, _s, _c in read_po(path)]


def leaves(d, prefix=()):
    for k, v in d.items():
        if isinstance(v, dict):
            for x in leaves(v, prefix + (k,)):
                yield x
        else:
            yield ".".join(prefix + (k,)), v


def ha_source():
    with open(os.path.join(HA, "strings.json"), encoding="utf-8") as f:
        return json.load(f)


def core_texts():
    return e2strings.core_strings()


# --- the catalogue ----------------------------------------------------------------------------------------------------
def sources():
    """[(where, msgid)]: every English text, where = 'e2' | 'kodi:<id>' | 'ha:<path>' (in order)."""
    out = [("e2", s) for s in e2strings.strings() if s]
    out += [("kodi:%d" % i, s) for i, s in kodi_source()]
    out += [("ha:" + p, s) for p, s in leaves(ha_source()) if not s.startswith("[%key:")]
    return out


def load(lang):
    """{(msgctxt, msgid): msgstr} of core/i18n/<lang>.po ({} if missing)."""
    path = os.path.join(CAT, lang + ".po")
    if not os.path.exists(path):
        return {}
    return {(c, i): s for c, i, s, _x in read_po(path)}


def lookup(cat, where, msgid):
    """Translation of msgid at a place: context 'kodi:30231' / 'ha:<path>' first, then 'kodi' / 'ha' / 'e2', then
    the shared entry (no context). None if missing or empty."""
    target = where.split(":", 1)[0]
    for ctx in (where, target, ""):
        if cat.get((ctx, msgid)):
            return cat[(ctx, msgid)]
    return None


def write_catalogue(lang, cat, src):
    """core/i18n/<lang>.po: shared entries in source order with #: references, then context overrides."""
    refs, order = {}, []
    for where, msgid in src:
        if msgid not in refs:
            refs[msgid] = []
            order.append(msgid)
        refs[msgid].append(where)
    out = ['# CamAlert master catalogue - %s (generated order; edit msgstr only, see core/i18n/README.md)'
           % LANG_NAMES[lang], 'msgid ""', 'msgstr ""', q("Content-Type: text/plain; charset=UTF-8\n"),
           q("Language: %s\n" % lang), ""]
    for msgid in order:
        out.append("#: " + " ".join(sorted(set(r.split(":")[0] if r == "e2" else r for r in refs[msgid]),
                                           key=_refkey)))
        out += ["msgid " + q(msgid), "msgstr " + q(cat.get(("", msgid), "")), ""]
    used = {(w, m) for w, m in src} | {(w.split(":")[0], m) for w, m in src}
    for (ctx, msgid), text in sorted(cat.items()):
        if ctx and (ctx, msgid) in used:
            out += ["msgctxt " + q(ctx), "msgid " + q(msgid), "msgstr " + q(text), ""]
    _write(os.path.join(CAT, lang + ".po"), "\n".join(out))


def _refkey(r):
    head, _sep, tail = r.partition(":")
    return ({"e2": 0, "kodi": 1, "ha": 2}.get(head, 3), int(tail) if tail.isdigit() else 0, tail)


# --- outputs ----------------------------------------------------------------------------------------------------------
def outputs():
    """{path: text} of every generated file."""
    out = {os.path.join(PO, "CamAlert.pot"): e2strings.pot()}
    e2 = [s for s in e2strings.strings() if s]
    kodi = kodi_source()
    ha = ha_source()
    out[os.path.join(HA, "translations", "en.json")] = _json(ha)
    for lang in LANGS:
        cat = load(lang)
        lines = ['msgid ""', 'msgstr ""', q("Content-Type: text/plain; charset=UTF-8\n"), q("Language: %s\n" % lang), ""]
        for s in e2:
            lines += ["msgid " + q(s), "msgstr " + q(lookup(cat, "e2", s) or ""), ""]
        out[os.path.join(PO, lang + ".po")] = "\n".join(lines)
        out[_kodi_path(lang)] = kodi_po(lang, kodi, lambda i, s: lookup(cat, "kodi:%d" % i, s) or "")
        out[os.path.join(HA, "translations", lang + ".json")] = _json(_ha_tree(ha, cat))
    return out


def _kodi_path(lang):
    return os.path.join(KODI_LANG, "resource.language.%s" % KODI_CODES[lang], "strings.po")


def kodi_po(lang, entries, tr):
    code = KODI_CODES[lang]
    lines = ["# CamAlert for Kodi - %s" % LANG_NAMES[lang], "# Copyright (C) 2026 CamAlert developers. GPL v2.",
             'msgid ""', 'msgstr ""', q("Content-Type: text/plain; charset=UTF-8\n"), q("Language: %s\n" % code), ""]
    for i, s in entries:
        lines += ['msgctxt "#%d"' % i, "msgid " + q(s), "msgstr " + q(tr(i, s) if lang != "en" else ""), ""]
    return "\n".join(lines)


def _ha_tree(d, cat, prefix=()):
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = _ha_tree(v, cat, prefix + (k,))
        elif v.startswith("[%key:"):
            out[k] = v
        else:
            out[k] = lookup(cat, "ha:" + ".".join(prefix + (k,)), v) or ""
    return out


def _json(d):
    return json.dumps(d, indent=2, ensure_ascii=False) + "\n"


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def assign_kodi_core_ids():
    """Gives every core N_() text an id in KODI_CORE_IDS in the Kodi en_gb strings.po (existing ids are kept;
    an id whose text the core no longer has is kept too, so its meaning never changes). Returns True if changed."""
    entries = kodi_source()
    have = {s for i, s in entries if i in KODI_CORE_IDS}
    used = {i for i, _s in entries}
    new = [s for s in core_texts() if s not in have]
    if not new:
        return False
    free = (i for i in KODI_CORE_IDS if i not in used)
    for s in new:
        entries.append((next(free), s))
    _write(_kodi_path_en(), kodi_po("en", sorted(entries), None))
    return True


def _kodi_path_en():
    return os.path.join(KODI_LANG, "resource.language.en_gb", "strings.po")


# --- checks -----------------------------------------------------------------------------------------------------------
def glossary():
    with open(os.path.join(CAT, "glossary.json"), encoding="utf-8") as f:
        return json.load(f)


def placeholders(s):
    return sorted(PLACEHOLDER.findall(s))


def problems():
    """Every problem as a text line (empty list = all good)."""
    src = sources()
    g = glossary()
    found = []
    terms = {t["en"].lower(): t for t in g["terms"]}
    contained = [(re.compile(r"\b%s\b" % re.escape(t["en"]), re.I), t) for t in g["terms"] if not t.get("exact_only")]
    for lang in ("en",) + LANGS:
        cat = load(lang) if lang != "en" else {}
        rules = [(re.compile(r["pattern"], 0 if r.get("case") else re.I), r) for r in g["forbidden"].get(lang, [])]
        known = set()
        for where, msgid in src:
            text = msgid if lang == "en" else lookup(cat, where, msgid)
            known.add(msgid)
            if text is None:
                found.append("%s: missing translation for %r (%s)" % (lang, msgid, where))
                continue
            if lang != "en" and placeholders(text) != placeholders(msgid):
                found.append("%s: placeholders differ in %r -> %r (%s)" % (lang, msgid, text, where))
            if lang != "en" and msgid.count("\n") != text.count("\n"):
                found.append("%s: line breaks differ in %r (%s)" % (lang, msgid, where))
            for rx, r in rules:
                if rx.search(text):
                    found.append("%s: %r uses %r, use %r (%s)" % (lang, text, rx.pattern, r["use"], where))
            t = terms.get(msgid.strip().lower())
            if t and lang != "en" and text.lower() != t[lang].lower():
                found.append("%s: glossary term %r must be %r, not %r (%s)" % (lang, msgid, t[lang], text, where))
            if lang in g.get("contains_languages", ()):
                for rx, term in contained:
                    if rx.search(msgid) and term[lang].lower() not in text.lower():
                        found.append("%s: %r contains the term %r: use %r in %r (%s)"
                                     % (lang, msgid, term["en"], term[lang], text, where))
            known.add(msgid)
        if lang != "en":
            keys = {(w, m) for w, m in src} | {(w.split(":")[0], m) for w, m in src} | {("", m) for m in known}
            for (ctx, msgid) in sorted(cat):
                if (ctx, msgid) not in keys:
                    found.append("%s: unused catalogue entry %r %r (run update)" % (lang, ctx, msgid))
    have = {s for i, s in kodi_source() if i in KODI_CORE_IDS}
    found += ["kodi: core text without an id in %d-%d: %r (run update)" % (KODI_CORE_IDS[0], KODI_CORE_IDS[-1], s)
              for s in core_texts() if s not in have]
    for path, text in sorted(outputs().items()):
        try:
            with open(path, encoding="utf-8") as f:
                same = f.read() == text
        except IOError:
            same = False
        if not same:
            found.append("not up to date: %s (run python3 tools/i18n/i18n.py build)" % os.path.relpath(path, ROOT))
    return found


def update():
    assign_kodi_core_ids()
    src = sources()
    for lang in LANGS:
        cat = load(lang)
        write_catalogue(lang, cat, src)
    build()


def build():
    for path, text in outputs().items():
        _write(path, text)


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "check"
    if cmd == "update":
        update()
    elif cmd == "build":
        build()
    elif cmd != "check":
        sys.stderr.write(__doc__)
        return 2
    p = problems()
    for line in p:
        print(line)
    print("i18n: %d problems" % len(p))
    return 1 if p else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
