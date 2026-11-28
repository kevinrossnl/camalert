# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Updating a player from Home Assistant (#126): which file to fetch, from where, and how to check it.

The player only ever downloads CamAlert's own GitHub release (a fixed URL, never one a caller chooses), only a
version newer than the installed one, and only a file whose SHA-256 is listed in the release's SHA256SUMS. How the
file is installed is up to the player (opkg, Kodi add-on folder, Android package installer).
"""
import hashlib
import re

from .update import version_tuple

REPO = "kevinrossnl/camalert"
RELEASE_BASE = "https://github.com/%s/releases/download/v%%s/" % REPO
SUMS = "SHA256SUMS"
ASSETS = {
    "enigma2": "enigma2-plugin-extensions-camalert_%s_all.ipk",
    "kodi": "service.camalert-%s.zip",
    "androidtv": "camalert-androidtv-%s.apk",
}
STATES = ("idle", "downloading", "installing", "waiting", "failed")
MAX_BYTES = 64 * 1024 * 1024  # an ipk or zip is < 1 MB, the APK about 7 MB
VERSION = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}$")


class UpdateError(Exception):
    """The update is refused or failed; str(e) is a short English reason for the log and Home Assistant."""


def check_request(current, version, allowed=True):
    """The version to install, or UpdateError: updates off, not a plain X.Y.Z version, or not newer."""
    if not allowed:
        raise UpdateError("updates from Home Assistant are off")
    v = str(version or "").strip().lstrip("vV")
    if not VERSION.match(v):
        raise UpdateError("invalid version")
    if version_tuple(v) <= version_tuple(current):
        raise UpdateError("not newer than the installed version")
    return v


def asset_name(platform, version):
    if platform not in ASSETS:
        raise UpdateError("no update file for this player")
    return ASSETS[platform] % version


def asset_url(platform, version):
    """The fixed download address of the release file for this player."""
    return RELEASE_BASE % version + asset_name(platform, version)


def sums_url(version):
    return RELEASE_BASE % version + SUMS


def parse_sums(text):
    """{file name: sha256 (lower case)} from a `sha256sum` listing ("<hash>  <name>" or "<hash> *<name>")."""
    out = {}
    for line in (text or "").splitlines():
        m = re.match(r"^([0-9a-fA-F]{64})\s+\*?(\S.*?)\s*$", line)
        if m:
            out[m.group(2)] = m.group(1).lower()
    return out


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def fetch(platform, version, opener):
    """(file name, bytes) of the checked release file. opener(url) returns the body as bytes (it may follow
    GitHub's redirect to its download host; the address it starts from is always the fixed release URL)."""
    name = asset_name(platform, version)
    sums = parse_sums(opener(sums_url(version)).decode("utf-8", "replace"))
    want = sums.get(name)
    if not want:
        raise UpdateError("%s is not listed in %s" % (name, SUMS))
    data = opener(asset_url(platform, version))
    if not data or len(data) > MAX_BYTES:
        raise UpdateError("download has an unexpected size")
    if sha256(data) != want:
        raise UpdateError("checksum does not match")
    return name, data


class UpdateState(object):
    """What the player reports in /camalert/status while it updates: update_state, update_version, update_error."""

    def __init__(self):
        self.state, self.version, self.error = "idle", None, None

    def set(self, state, version=None, error=None):
        if state not in STATES:
            raise ValueError(state)
        self.state = state
        if version is not None:
            self.version = version
        self.error = error if state == "failed" else None
        return self

    def busy(self):
        return self.state in ("downloading", "installing", "waiting")

    def as_status(self):
        return {"update_state": self.state, "update_version": self.version, "update_error": self.error}
