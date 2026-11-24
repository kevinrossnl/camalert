# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Update check against GitHub releases."""

import json
import re


UPDATE_INTERVAL = 24 * 3600


def version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", (v or "").lstrip("vV"))[:4]) or (0,)


def newer_version(current, latest):
    """The latest release tag if it is newer than the installed version, else None."""
    return latest.lstrip("vV") if latest and version_tuple(latest) > version_tuple(current) else None


def latest_tag(release_json):
    try:
        d = json.loads(release_json)
    except (ValueError, TypeError):
        return None
    return d.get("tag_name") if isinstance(d, dict) and not d.get("draft") and not d.get("prerelease") else None
