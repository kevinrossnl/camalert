#!/usr/bin/env python3
"""Golden listing of the Android TV APK (#64, like tests/build/golden for the ipk and the Kodi zips).

What matters in the APK, without what changes on every dependency update: the files outside res/ (dex files are
counted, not named), our own resources, and from `aapt2 dump badging` the package, SDK levels, permissions,
launcher entries, features and the foreground-service property. The version name is replaced by @VERSION@.

    python3 tools/apk_listing.py check  <apk> [golden]   exit 1 if the listing differs (CI area androidtv)
    python3 tools/apk_listing.py update <apk> [golden]   write the golden file (review the diff!)

aapt2 is taken from $ANDROID_HOME/build-tools/<newest>/aapt2. Copyright (C) 2026 CamAlert developers, GPL v2.
"""
import glob
import os
import re
import subprocess
import sys
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GOLDEN = os.path.join(ROOT, "tests", "build", "golden", "androidtv_apk.txt")
OWN_RES = ("res/drawable/banner.xml", "res/drawable/icon.xml", "res/xml/network_security_config.xml")
BADGING = ("package:", "minSdkVersion:", "targetSdkVersion:", "uses-permission:", "launchable-activity:",
           "leanback-launchable-activity:", "property:", "  uses-feature", "uses-feature", "application-debuggable")


def zip_lines(path):
    with zipfile.ZipFile(path) as z:
        names = sorted(i.filename for i in z.infolist())
    dex = [n for n in names if re.match(r"^classes\d*\.dex$", n)]
    out = ["dex files: %s" % ("yes" if dex else "none")]
    out += ["file %s" % n for n in names if "/" not in n and n not in dex]
    out += ["file %s" % n for n in names if "/" in n and not n.startswith(("res/", "META-INF/"))]
    out += ["res %s" % n for n in OWN_RES if n in names]
    out += ["missing %s" % n for n in OWN_RES if n not in names]
    return out


def aapt2():
    home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or ""
    tools = sorted(glob.glob(os.path.join(home, "build-tools", "*", "aapt2")))
    return tools[-1] if tools else None


def badging_lines(text):
    out = []
    for line in text.splitlines():
        if line.startswith(BADGING):
            line = re.sub(r"versionName='[^']*'", "versionName='@VERSION@'", line)
            line = re.sub(r" platformBuildVersion\w*='[^']*'| compileSdkVersion\w*='[^']*'", "", line)
            out.append("badging " + line.strip())
    return out


def listing(apk, badging=None):
    lines = zip_lines(apk)
    if badging is None:
        tool = aapt2()
        if not tool:
            raise SystemExit("aapt2 not found: set ANDROID_HOME")
        badging = subprocess.check_output([tool, "dump", "badging", apk]).decode("utf-8", "replace")
    return "\n".join(lines + badging_lines(badging)) + "\n"


def main(argv):
    if len(argv) < 3 or argv[1] not in ("check", "update"):
        sys.stderr.write(__doc__)
        return 2
    golden = argv[3] if len(argv) > 3 else GOLDEN
    text = listing(argv[2])
    if argv[1] == "update":
        with open(golden, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("written: %s" % os.path.relpath(golden, ROOT))
        return 0
    with open(golden, encoding="utf-8") as f:
        want = f.read()
    if text != want:
        import difflib
        sys.stdout.writelines(difflib.unified_diff(want.splitlines(True), text.splitlines(True), "golden", "apk"))
        print("APK content changed: if intended, run python3 tools/apk_listing.py update <apk> and review the diff")
        return 1
    print("APK listing matches the golden file")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
