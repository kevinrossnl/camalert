"""camalert_core.present + camalert_core.i18n: event-list codes with translated labels, dates, key hints (#41)."""
import ast
import glob
import os
import re
import time
import unittest

import _paths

_paths.core()
from camalert_core import i18n, keymap, present as p  # noqa: E402

EN = i18n.no_translation


def upper(text):
    """A fake translation: shows which texts went through tr."""
    return text.upper()


class TestEventValues(unittest.TestCase):
    def test_codes_have_labels(self):
        self.assertEqual(p.PRIORITIES, ("normal", "high", "alarm"))
        self.assertEqual(set(p.SOURCES) - {"wake"}, set(__import__("camalert_core.events", fromlist=["x"]).SOURCES))
        for table in (p.SOURCE_LABELS, p.PRIORITY_LABELS, p.RESULT_LABELS, p.REASON_LABELS):
            self.assertTrue(all(isinstance(v, str) and v for v in table.values()))
        self.assertEqual(p.source_label("frigate", upper), "FRIGATE")
        self.assertEqual(p.priority_label("high", EN), "High")
        self.assertEqual(p.result_label("ignore", upper), "IGNORED")
        self.assertEqual(p.source_label("other", upper), "other")  # unknown codes are shown as they are
        self.assertEqual(p.result_label(None, upper), "")

    def test_reasons(self):
        self.assertEqual(p.reason("dnd"), "dnd")
        self.assertEqual(p.reason("cooldown", 30), "cooldown:30")
        with self.assertRaises(ValueError):
            p.reason("nonsense")
        self.assertEqual(p.parse_reason("cooldown:30"), ("cooldown", 30))
        self.assertEqual(p.parse_reason("cooldown:x"), ("cooldown", 0))
        self.assertEqual(p.parse_reason("dnd:1"), ("dnd", None))
        self.assertEqual(p.parse_reason(""), (None, None))
        self.assertEqual(p.parse_reason("cooldown (45 s)"), ("cooldown", 45))   # English of older players
        self.assertEqual(p.parse_reason("cooldown (? s)"), ("cooldown", 0))
        self.assertEqual(p.parse_reason("Do not disturb"), ("dnd", None))
        self.assertEqual(p.parse_reason("something else"), ("something else", None))
        self.assertEqual(p.reason_label("cooldown:30", EN), "Cooldown (30 s)")
        self.assertEqual(p.reason_label("outside_hours", upper), "OUTSIDE THE CHOSEN TIMES")
        self.assertEqual(p.reason_label(None, upper), "")
        self.assertEqual(p.reason_label("weird", upper), "weird")
        self.assertTrue(set(p.LEGACY_REASONS.values()) <= set(p.REASONS))

    def test_every_reason_the_players_set_today_has_a_code(self):
        """Every reason the players set (codes since #41; English texts before) maps to a code."""
        texts = set()
        for path in glob.glob(os.path.join(_paths.ENIGMA2, "*.py")) + glob.glob(os.path.join(_paths.KODI_LIB, "*.py")):
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign):
                    continue
                targets = [t for x in node.targets for t in (x.elts if isinstance(x, ast.Tuple) else [x])]
                if not any(isinstance(t, ast.Attribute) and t.attr == "reason" for t in targets):
                    continue
                keys = {id(n.slice) for n in ast.walk(node.value) if isinstance(n, ast.Subscript)}
                for n in ast.walk(node.value):
                    if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in keys and \
                            n.value not in ("", "ignore", "error"):
                        texts.add(n.value)
        self.assertIn("dnd", texts)
        for t in texts:
            self.assertIn(p.parse_reason(t)[0], p.REASONS, t)

    def test_dates(self):
        self.assertEqual(p.date_format("nl"), "%d-%m-%Y")
        self.assertEqual(p.date_format("de_DE"), "%d.%m.%Y")
        self.assertEqual(p.date_format("fr-FR"), "%d/%m/%Y")
        self.assertEqual(p.date_format(None), "%d/%m/%Y")
        ts = time.mktime((2026, 11, 24, 14, 3, 5, 0, 0, -1))
        self.assertEqual(p.event_time(ts, "nl"), "24-11-2026 14:03:05")
        self.assertEqual(p.event_time(ts, "pl"), "24.11.2026 14:03:05")
        self.assertEqual(p.event_time(ts, date=False), "14:03:05")
        self.assertEqual(p.event_time(ts, fmt="%Y-%m-%d"), "2026-11-24 14:03:05")

    def test_event_line_and_details(self):
        ts = time.mktime((2026, 11, 24, 14, 3, 5, 0, 0, -1))
        e = {"time": ts, "camera": "garden", "label": "Person", "source": "frigate", "priority": "high",
             "action": "ignore", "reason": "cooldown:30"}
        self.assertEqual(p.event_line(e, upper), "14:03:05  garden · Person  (FRIGATE, HIGH) -> IGNORED")
        mark = lambda t: "[%s]" % t  # noqa: E731 - a fake translation that keeps placeholders
        rows = p.event_details(e, mark, "de")
        self.assertEqual(rows[0], ("[Time]", "24.11.2026 14:03:05"))
        self.assertEqual([r[0] for r in rows], ["[Time]", "[Camera]", "[Source]", "[Priority]", "[Result]", "[Reason]"])
        self.assertEqual(rows[1:], [("[Camera]", "garden · Person"), ("[Source]", "[Frigate]"), ("[Priority]", "[High]"),
                                    ("[Result]", "[Ignored]"), ("[Reason]", "[Cooldown (30 s)]")])
        e2 = dict(e, label="", reason="")
        self.assertEqual(len(p.event_details(e2, EN)), 5)
        self.assertEqual(p.event_details(e2, EN)[1], ("Camera", "garden"))


class TestKeyHints(unittest.TestCase):
    def test_hints_follow_the_key_map(self):
        for player in keymap.PLAYERS:
            for context, items in p.HINTS.items():
                for actions, _label in items:
                    for a in actions:
                        # every action in a hint exists in the key map of some player (no invented actions)
                        self.assertTrue(any(a in keymap.KEYMAP[x][context] for x in keymap.PLAYERS), (context, a))
                for key in (k for keys in keymap.KEYMAP[player][context].values() for k in keys):
                    action = keymap.action_for(player, context, key)
                    shown = any(action in acts for acts, _l in items)
                    if shown and action != "pass":
                        self.assertIn(key, p.KEY_NAMES[player], (player, context, key))

    def test_enigma2_hints(self):
        self.assertEqual(p.key_hint("enigma2", "window", EN), "OK = live   ◀ ▶ = other camera   EXIT = close")
        self.assertEqual(p.key_hint("enigma2", "window", EN, ptz_key="blue", has_ptz=True),
                         "OK = live   ◀ ▶ = other camera   BLUE = camera control   EXIT = close")
        self.assertEqual(p.key_hint("enigma2", "ptz", EN, ptz_key="yellow"),
                         "▲ ▼ ◀ ▶ = move   CH+ CH- = zoom   OK = home position   EXIT/YELLOW = end camera control")
        self.assertEqual(p.key_hint("enigma2", "tour", upper), "◀ ▶ = OTHER CAMERA   OK = PAUSE   GREEN/PLAY = LIVE   EXIT = CLOSE")
        self.assertEqual(p.key_hint("enigma2", "mosaic", EN), "OK/EXIT = close")
        self.assertEqual(p.key_hint("enigma2", "live", EN), "")

    def test_kodi_hints(self):
        self.assertEqual(p.key_hint("kodi", "window", EN), "OK = live   ◀ ▶ = other camera   BACK = close")
        self.assertEqual(p.key_hint("kodi", "window", EN, ptz_key="off", has_ptz=True),
                         "OK = live   ◀ ▶ = other camera   MENU/INFO = camera control   BACK = close")
        self.assertEqual(p.key_hint("kodi", "ptz", EN, glyphs=False),
                         "^ v < > = move   CH+ CH- = zoom   OK = home position   BACK/MENU = end camera control")
        self.assertEqual(p.key_hint("kodi", "mosaic", EN), "BACK/STOP = close")
        self.assertIn("PAUSE/PLAY = pause", p.key_hint("kodi", "live", EN))

    def test_tour_status(self):
        self.assertEqual(p.tour_status("Garden", 2, 5, False, EN), "Garden   (2/5, tour)")
        self.assertEqual(p.tour_status("Garden", 2, 5, True, upper), "Garden   (2/5, PAUSED)")


class TestI18n(unittest.TestCase):
    PO = ('msgctxt "#30010"\nmsgid "Normal"\nmsgstr ""\n\nmsgctxt "#30501"\nmsgid "Normal"\nmsgstr ""\n\n'
          'msgctxt "#30020"\nmsgid "Say \\"hi\\""\nmsgstr ""\n\nmsgctxt "#30012"\nmsgid "Say \\"hi\\""\nmsgstr ""\n\n'
          'msgctxt "#30600"\nmsgid "Two"\nmsgstr ""\n\nmsgctxt "#30550"\nmsgid "Two"\nmsgstr ""\n')

    def test_n_and_kodi_ids(self):
        self.assertEqual(i18n.N_("x"), "x")
        ids = i18n.kodi_ids(self.PO)
        self.assertEqual(ids, {"Normal": 30501, 'Say "hi"': 30012, "Two": 30550})

    def test_kodi_translator(self):
        strings = {30501: "Normaal", 30012: ""}
        tr = i18n.kodi_translator(strings.get, {"Normal": 30501, "Empty": 30012})
        self.assertEqual((tr("Normal"), tr("Empty"), tr("Other")), ("Normaal", "Empty", "Other"))

        def broken(_i):
            raise RuntimeError("no add-on")
        self.assertEqual(i18n.kodi_translator(broken, {"Normal": 30501})("Normal"), "Normal")

    def test_every_core_text_has_a_kodi_id_in_the_core_block(self):
        path = os.path.join(_paths.KODI_ADDON, "resources", "language", "resource.language.en_gb", "strings.po")
        with open(path, encoding="utf-8") as f:
            ids = i18n.kodi_ids(f.read())
        texts = list(p.SOURCE_LABELS.values()) + list(p.RESULT_LABELS.values()) + list(p.REASON_LABELS.values()) + \
            [label for items in p.HINTS.values() for _a, label in items] + list(p.COLOUR_NAMES.values())
        for t in texts:
            self.assertTrue(i18n.KODI_CORE_IDS[0] <= ids[t] < i18n.KODI_CORE_IDS[1], t)


if __name__ == "__main__":
    unittest.main()
