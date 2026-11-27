"""Android's regex engine (ICU) is not the JVM's: some JVM flags compile in the Kotlin unit tests but throw
PatternSyntaxException on a TV. 1.3.0 crashed at start on Fire OS 6 because of (?U) in Discovery.kt."""
import os
import re
import unittest

import _paths  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "players", "androidtv")
# flags / options the JVM knows and Android's ICU regex rejects (or ignores silently)
UNSUPPORTED = (r"\(\?[a-zA-Z]*U", r"UNICODE_CHARACTER_CLASS", r"RegexOption\.CANON_EQ", r"Pattern\.CANON_EQ")


class TestAndroidRegex(unittest.TestCase):
    def test_no_jvm_only_regex_flags(self):
        bad = []
        for base, _dirs, files in os.walk(APP):
            if os.sep + "build" + os.sep in base + os.sep or os.sep + "test" + os.sep in base + os.sep:
                continue
            for name in files:
                if name.endswith((".kt", ".java")):
                    path = os.path.join(base, name)
                    for no, line in enumerate(open(path, encoding="utf-8"), 1):
                        if any(re.search(p, line) for p in UNSUPPORTED):
                            bad.append("%s:%d" % (os.path.relpath(path, ROOT), no))
        self.assertEqual(bad, [], "regex flags that crash on Android (use plain code, see Discovery.clean)")


if __name__ == "__main__":
    unittest.main()
