"""The master translation catalogue (core/i18n, tools/i18n/i18n.py, #38/#43): every format is generated from it and
checked for missing translations, placeholders, forbidden synonyms, tone and glossary terms."""
import os
import unittest

import _paths

_paths.add(os.path.join(_paths.TOOLS, "i18n"), _paths.TOOLS)
import i18n  # noqa: E402


class TestCatalogue(unittest.TestCase):
    def test_no_problems(self):
        self.assertEqual(i18n.problems(), [], "run: python3 tools/i18n/i18n.py update / build, then translate")

    def test_glossary(self):
        g = i18n.glossary()
        langs = ("en",) + i18n.LANGS
        self.assertEqual(len({"priority" if t["id"].startswith("priority_") else t["id"] for t in g["terms"]}), 20)
        for t in g["terms"]:
            self.assertTrue(all(t.get(lang) for lang in langs), t["id"])
        self.assertEqual(g["tone"], {"nl": "je", "de": "du", "fr": "vous", "it": "impersonal", "pl": "impersonal"})
        self.assertEqual(set(g["forbidden"]), set(langs))

    def problems_with(self, lang, msgid, text, where=None):
        """problems() with one translation replaced."""
        load, real = i18n.load, {}

        def fake(lng):
            cat = real.setdefault(lng, load(lng))
            if lng == lang:
                cat = dict(cat)
                cat[("", msgid)] = text
            return cat
        i18n.load = fake
        try:
            return [p for p in i18n.problems() if not p.startswith("not up to date")]
        finally:
            i18n.load = load

    def test_forbidden_synonym_fails(self):
        cases = [("nl", "Photo window", "Foto-venster"), ("de", "Notification", "Nur Hinweis"),
                 ("fr", "Tour: seconds per camera", "Tournée : secondes par caméra"),
                 ("pl", "Photo window", "Okno zdjęć"), ("de", "Address of your go2rtc server, e.g. http://192.168.1.10:1984",
                                                          "Adresse Ihres go2rtc-Servers, z. B. http://192.168.1.10:1984"),
                 ("nl", "Ignore normal requests while the receiver is recording.",
                  "Normale verzoeken negeren terwijl u een opname maakt.")]
        for lang, msgid, text in cases:
            with self.subTest(lang=lang, text=text):
                self.assertTrue(any("uses" in p for p in self.problems_with(lang, msgid, text)))

    def test_old_kodi_labels_are_refused(self):
        """#60 / #56: the Kodi labels that differed from the glossary are refused in English sources too."""
        import json
        import re
        with open(os.path.join(_paths.ROOT, "core", "i18n", "glossary.json"), encoding="utf-8") as f:
            rules = json.load(f)["forbidden"]["en"]
        for old in ("Recent events", "Switch to live stream", "Notification only"):
            with self.subTest(old=old):
                self.assertTrue(any(re.search(r["pattern"], old, re.I) for r in rules))

    def test_placeholder_mismatch_fails_in_every_format(self):
        cases = [("nl", "%s: snapshot %d ms", "%s: foto ms"),                       # Enigma2 + Kodi
                 ("de", "Show {camera}", "Kamera anzeigen")]                         # Home Assistant
        for lang, msgid, text in cases:
            with self.subTest(msgid=msgid):
                found = self.problems_with(lang, msgid, text)
                self.assertTrue(any("placeholders differ" in p for p in found), found)
        found = self.problems_with("fr", "%s: snapshot %d ms", "")
        self.assertTrue(any("missing translation" in p for p in found))

    def test_glossary_term_verbatim(self):
        found = self.problems_with("it", "Display mode", "Visualizzazione")
        self.assertTrue(any("glossary term" in p for p in found), found)
        found = self.problems_with("de", "Volume during live view (%)", "Lautstärke beim Live-Video (%)")
        self.assertTrue(any("contains the term" in p for p in found), found)

    def test_placeholders(self):
        self.assertEqual(i18n.placeholders("%s at %(cam)s {camera} [%key:common::x%] %d"),
                         sorted(["%s", "%(cam)s", "{camera}", "[%key:common::x%]", "%d"]))

    def test_lookup_prefers_context(self):
        cat = {("", "Normal"): "Normale", ("kodi", "Normal"): "K", ("kodi:30231", "Normal"): "Normal"}
        self.assertEqual(i18n.lookup(cat, "kodi:30231", "Normal"), "Normal")
        self.assertEqual(i18n.lookup(cat, "kodi:30140", "Normal"), "K")
        self.assertEqual(i18n.lookup(cat, "e2", "Normal"), "Normale")
        self.assertIsNone(i18n.lookup(cat, "e2", "Other"))

    def test_kodi_ids_stay(self):
        """Ids of the en_gb strings.po are the Kodi source: every translated file has the same ids in the same order."""
        en = [i for i, _s in i18n.kodi_source()]
        self.assertTrue(all(i >= 30000 for i in en))
        for lang in i18n.LANGS:
            ids = [int(c[1:]) for c, _i, _s, _x in i18n.read_po(i18n._kodi_path(lang))]
            self.assertEqual(ids, en, lang)


if __name__ == "__main__":
    unittest.main()
