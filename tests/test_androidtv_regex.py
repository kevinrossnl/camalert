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


class TestAndroidApiLevel(unittest.TestCase):
    """minSdk is 25 (Android 7.1, Fire OS 6) and the build has no core library desugaring: Java APIs from Android 8
    (API 26) compile and pass the JVM tests, then crash on the Fire TV (NoClassDefFoundError). 1.3.x used
    java.util.Base64 for ONVIF and java.time for UniFi's Retry-After."""
    API26 = (r"\bjava\.util\.Base64\b", r"\bjava\.time\.", r"\bjava\.nio\.file\.", r"\bjava\.util\.function\.",
             r"\bjava\.util\.stream\.", r"\bjava\.lang\.invoke\.")

    def test_no_android8_java_apis(self):
        bad = []
        for base, _dirs, files in os.walk(APP):
            if os.sep + "build" + os.sep in base + os.sep or os.sep + "test" + os.sep in base + os.sep:
                continue
            for name in files:
                if name.endswith((".kt", ".java")):
                    path = os.path.join(base, name)
                    for no, line in enumerate(open(path, encoding="utf-8"), 1):
                        code = line.split("//")[0]
                        if code.lstrip().startswith(("*", "/*")):  # KDoc / block comment
                            continue
                        if any(re.search(p, code) for p in self.API26):
                            bad.append("%s:%d" % (os.path.relpath(path, ROOT), no))
        self.assertEqual(bad, [], "Java APIs from Android 8+ crash on Android 7 (minSdk 25): use HttpAuth.base64, "
                                  "SimpleDateFormat, plain loops")


if __name__ == "__main__":
    unittest.main()
