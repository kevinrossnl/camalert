import os
import re
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from msgfmt import parse_po, make_mo  # noqa: E402
from strings import strings, pot  # noqa: E402

PO = os.path.join(HERE, "..", "po")


class TestTranslations(unittest.TestCase):
    def test_pot_up_to_date(self):
        self.assertEqual(open(os.path.join(PO, "DoorCam.pot"), encoding="utf-8").read(), pot(),
                         "run: python3 tools/strings.py > po/DoorCam.pot")

    def test_every_language_complete_and_placeholders_match(self):
        wanted = [s for s in strings() if s]
        for f in sorted(os.listdir(PO)):
            if not f.endswith(".po"):
                continue
            entries = parse_po(open(os.path.join(PO, f), encoding="utf-8").read())
            for s in wanted:
                self.assertIn(s, entries, "%s: missing %r" % (f, s))
                self.assertEqual(re.findall(r"%[sd]", s), re.findall(r"%[sd]", entries[s]), "%s: placeholders %r" % (f, s))
            self.assertTrue(make_mo(entries).startswith(b"\xde\x12\x04\x95"))


if __name__ == "__main__":
    unittest.main()
