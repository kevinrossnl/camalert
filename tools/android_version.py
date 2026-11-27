#!/usr/bin/env python3
"""Android versionCode for a CamAlert version (#65): MAJOR*10000 + MINOR*100 + PATCH.

    python3 tools/android_version.py 1.2.0     -> 10200

Every release gets a higher code than the one before, so Android installs it as an update. MINOR and PATCH stay
below 100; debug builds keep versionCode 1. Copyright (C) 2026 CamAlert developers, GPL v2.
"""
import re
import sys


def version_code(version):
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version or "")
    if not m:
        raise ValueError("not a release version X.Y.Z: %r" % version)
    major, minor, patch = (int(x) for x in m.groups())
    if minor >= 100 or patch >= 100:
        raise ValueError("minor and patch must stay below 100: %r" % version)
    code = major * 10000 + minor * 100 + patch
    if code <= 1:
        raise ValueError("version too low for a release: %r" % version)
    return code


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(version_code(sys.argv[1]))
