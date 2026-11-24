"""Docs tests (#24, #47, #36 part): generated blocks up to date, links and anchors resolve, every page reachable
from docs/index.md, glossary words only (no forbidden synonyms, "player" when Kodi is meant), Kodi 19 everywhere."""
import glob
import json
import os
import re
import unittest

import _paths

ROOT = _paths.ROOT
_paths.tools()
import docs as gen  # noqa: E402  (tools/docs.py)

LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE = re.compile(r"^```.*?^```", re.S | re.M)
GENERATED = re.compile(r"<!-- BEGIN generated: (\w+).*?<!-- END generated: \1 -->", re.S)
# pages that may say "receiver" freely: the Enigma2 page and the developer pages
RECEIVER_OK_PAGES = ("docs/players/enigma2.md", "docs/dev/")
RECEIVER_OK = re.compile(r"Enigma2 receivers?|receivers? (?:or|and|/) Kodi|receivers / Kodi|`receiver`|"
                         r"Enigma2 \w+ receivers?", re.I)


def rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def doc_files():
    files = [os.path.join(ROOT, "README.md")] + sorted(glob.glob(os.path.join(ROOT, "docs", "**", "*.md"), recursive=True))
    files += sorted(glob.glob(os.path.join(ROOT, "**", "DEVELOPMENT.md"), recursive=True))
    files += [os.path.join(ROOT, p) for p in ("tests/README.md", "core/i18n/README.md", "homeassistant/blueprints/README.md",
                                              "CHANGELOG.md")]
    return [f for f in files if os.path.isfile(f) and "/dist/" not in f and "/.venv" not in f]


def prose(text):
    """Text without code blocks, inline code and generated blocks."""
    text = FENCE.sub("", text)
    return re.sub(r"`[^`\n]*`", "", text)


def slug(heading):
    """GitHub's anchor of a heading."""
    h = re.sub(r"[*_`]|\[([^\]]*)\]\([^)]*\)", lambda m: m.group(1) or "", heading.strip()).lower()
    h = re.sub(r"[^\w\- ]", "", h, flags=re.U)
    return h.replace(" ", "-")


def anchors(path):
    out, seen = set(), {}
    for line in FENCE.sub("", open(path, encoding="utf-8").read()).splitlines():
        m = re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)
        if m:
            s = slug(m.group(1))
            n = seen.get(s, 0)
            seen[s] = n + 1
            out.add(s if n == 0 else "%s-%d" % (s, n))
    return out


def links(path):
    text = FENCE.sub("", open(path, encoding="utf-8").read())
    text = re.sub(r"`[^`\n]*`", "", text)
    return LINK.findall(text)


class TestDocs(unittest.TestCase):
    def test_generated_blocks_are_up_to_date(self):
        self.assertEqual(gen.main(["check"]), 0, "run: python3 tools/docs.py update")

    def test_key_table_matches_the_core_key_map(self):
        text = open(os.path.join(ROOT, "docs", "user", "keys.md"), encoding="utf-8").read()
        self.assertIn(gen.keys_block(), text)
        self.assertIn("| live | GREEN / PLAY | GREEN / PLAY / ▲ |", text)  # tour, #2

    def test_glossary_matches_core(self):
        text = open(os.path.join(ROOT, "docs", "user", "glossary.md"), encoding="utf-8").read()
        g = json.load(open(os.path.join(ROOT, "core", "i18n", "glossary.json"), encoding="utf-8"))
        for t in g["terms"]:
            self.assertTrue(t.get("definition"), t["id"])
            self.assertIn("| **%s** | %s |" % (t["en"], t["definition"]), text)
            for lang in gen.LANGS:
                self.assertIn(t[lang], text, (t["id"], lang))

    def test_relative_links_and_anchors_resolve(self):
        bad = []
        for path in doc_files():
            for url in links(path):
                if re.match(r"^[a-z][a-z0-9+.-]*:", url) or url.startswith("//"):
                    continue  # external links: not checked here (nightly at most, #36)
                target, _, frag = url.partition("#")
                full = os.path.normpath(os.path.join(os.path.dirname(path), target)) if target else path
                if not os.path.exists(full):
                    bad.append("%s: %s (missing)" % (rel(path), url))
                elif frag and full.endswith(".md") and frag not in anchors(full):
                    bad.append("%s: %s (no such heading)" % (rel(path), url))
        self.assertEqual(bad, [])

    def test_every_page_is_reachable_from_the_index(self):
        start = os.path.join(ROOT, "docs", "index.md")
        seen, todo = {start}, [start]
        while todo:
            path = todo.pop()
            for url in links(path):
                target = url.partition("#")[0]
                if not target or re.match(r"^[a-z]+:", target):
                    continue
                full = os.path.normpath(os.path.join(os.path.dirname(path), target))
                if full.endswith(".md") and full.startswith(os.path.join(ROOT, "docs")) and full not in seen \
                        and os.path.exists(full):
                    seen.add(full)
                    todo.append(full)
        pages = {p for p in glob.glob(os.path.join(ROOT, "docs", "**", "*.md"), recursive=True)
                 if os.path.basename(p) != "DEVELOPMENT.md"}
        self.assertEqual(sorted(rel(p) for p in pages - seen), [])

    def test_no_forbidden_synonyms(self):
        g = json.load(open(os.path.join(ROOT, "core", "i18n", "glossary.json"), encoding="utf-8"))
        rules = [(re.compile(r["pattern"], 0 if r.get("case") else re.I), r["use"]) for r in g["forbidden"]["en"]]
        bad = []
        for path in doc_files():
            if path.endswith("CHANGELOG.md"):
                continue  # history
            text = re.sub(r"~~[^~]*~~", "", prose(open(path, encoding="utf-8").read()))
            for i, line in enumerate(text.splitlines(), 1):
                for pat, use in rules:
                    if pat.search(line):
                        bad.append("%s: %r -> use %r" % (rel(path), pat.search(line).group(0), use))
        self.assertEqual(bad, [])

    def test_player_not_receiver_where_kodi_is_meant(self):
        bad = []
        for path in doc_files():
            r = rel(path)
            if r.startswith(RECEIVER_OK_PAGES) or r.endswith("DEVELOPMENT.md") or not (r.startswith("docs/") or r == "README.md"):
                continue
            text = GENERATED.sub("", prose(open(path, encoding="utf-8").read()))
            for i, line in enumerate(text.splitlines(), 1):
                rest = RECEIVER_OK.sub("", line)
                if re.search(r"\breceivers?\b", rest, re.I):
                    bad.append("%s: %s" % (r, line.strip()[:100]))
        self.assertEqual(bad, [])

    def test_development_md_files_name_existing_files(self):
        """#36: the file tables and commands in the DEVELOPMENT.md files name files that exist (one DEVELOPMENT.md per folder)."""
        names = sorted(rel(p) for p in glob.glob(os.path.join(ROOT, "**", "DEVELOPMENT.md"), recursive=True)
                       if "/dist/" not in p and "/.venv" not in p)
        self.assertEqual(names, ["DEVELOPMENT.md", "core/DEVELOPMENT.md", "custom_components/DEVELOPMENT.md", "docs/DEVELOPMENT.md",
                                 "players/enigma2/DEVELOPMENT.md", "players/kodi/DEVELOPMENT.md"])
        token = re.compile(r"`([\w./-]+\.(?:py|md|json|yaml|yml|xml|po|sh|wav|txt))`")
        import subprocess
        tracked = subprocess.check_output(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT).decode().split()
        bad = []
        for name in names:
            for path in token.findall(open(os.path.join(ROOT, name), encoding="utf-8").read()):
                path = re.sub(r"^(\.\./)+", "", path)
                if not any(f == path or f.endswith("/" + path) for f in tracked):
                    bad.append("%s: %s" % (name, path))
        self.assertEqual(bad, [])

    def test_kodi_minimum_version_is_19_everywhere(self):
        addon = open(os.path.join(_paths.KODI, "service.camalert", "addon.xml"), encoding="utf-8").read()
        self.assertIn('<import addon="xbmc.python" version="3.0.0"/>', addon)  # 3.0.0 = Kodi 19 Matrix
        claims = []
        for path in doc_files():
            for m in re.finditer(r"Kodi (\d+)(?: \(\w+\))? (?:or newer|or later|\+)", open(path, encoding="utf-8").read()):
                claims.append((rel(path), m.group(1)))
        self.assertTrue(claims)
        self.assertEqual([c for c in claims if c[1] != "19"], [])


if __name__ == "__main__":
    unittest.main()
