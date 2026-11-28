# -*- coding: utf-8 -*-
# CamAlert for Kodi. Copyright (C) 2026 CamAlert developers. GPL v2.
"""Updating the add-on from Home Assistant (#126).

The release zip is downloaded from CamAlert's fixed GitHub URL and checked against SHA256SUMS
(camalert_core.selfupdate). It must hold only service.camalert/... with that version in addon.xml. While Kodi
plays something the update waits ("waiting"); then the add-on folder is swapped (the old one goes to Kodi's temp
folder) and Kodi is told to look at its local add-ons again, which restarts the service with the new code.
"""
import io
import os
import re
import shutil
import threading
import time
import urllib.request
import zipfile

from . import ADDON_ID, __version__, kodiapi
from .camalert_core import selfupdate

STATE = selfupdate.UpdateState()
WAIT_STEP = 30  # seconds between checks while something plays
_lock = threading.Lock()


# --- the parts tests replace -------------------------------------------------------------------------------------
def opener(url):
    req = urllib.request.Request(url, headers={"User-Agent": "CamAlert/%s" % __version__})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(selfupdate.MAX_BYTES + 1)


def playing():
    return bool(kodiapi.cond("Player.HasMedia"))


def sleep(seconds):
    """False when Kodi is shutting down (the service stops)."""
    import xbmc
    return not xbmc.Monitor().waitForAbort(seconds)


def reload_addons():
    kodiapi.builtin("UpdateLocalAddons")


# --- checks --------------------------------------------------------------------------------------------------------
def check_zip(data, version):
    """The zip as a ZipFile when it only holds service.camalert/... and its addon.xml has `version`."""
    z = zipfile.ZipFile(io.BytesIO(data))
    prefix = ADDON_ID + "/"
    for name in z.namelist():
        if not name.startswith(prefix) or ".." in name.split("/") or name.startswith("/"):
            raise selfupdate.UpdateError("unexpected file in the zip: %s" % name[:60])
    try:
        xml = z.read(prefix + "addon.xml").decode("utf-8", "replace")
    except KeyError:
        raise selfupdate.UpdateError("addon.xml missing in the zip")
    m = re.search(r'<addon\b[^>]*\bid="%s"[^>]*\bversion="([^"]+)"' % re.escape(ADDON_ID), xml)
    if not m or m.group(1) != version:
        raise selfupdate.UpdateError("the zip holds another version")
    return z


def install(z, version, addon_dir, temp):
    """Unpacks next to the add-on, then swaps folders; the old add-on is kept in temp for this session."""
    new_root = os.path.join(temp, "update-%s" % version)
    shutil.rmtree(new_root, ignore_errors=True)
    z.extractall(new_root)
    old = os.path.join(temp, "previous-%s-%d" % (__version__, int(time.time())))
    shutil.move(addon_dir, old)
    try:
        shutil.move(os.path.join(new_root, ADDON_ID), addon_dir)
    except Exception:
        shutil.move(old, addon_dir)  # put the old one back: Kodi must keep a working add-on
        raise
    shutil.rmtree(new_root, ignore_errors=True)
    return old


# --- the flow ----------------------------------------------------------------------------------------------------
def start(version):
    """Called by the API (#126) with a checked version; works in its own thread."""
    STATE.set("downloading", version)
    kodiapi.log("update to %s: downloading" % version)
    threading.Thread(target=run, args=(version,), name="camalert-update", daemon=True).start()


def run(version):
    if not _lock.acquire(False):
        return
    try:
        _name, data = selfupdate.fetch("kodi", version, opener)
        z = check_zip(data, version)
        while playing():
            if STATE.state != "waiting":
                kodiapi.log("update to %s: waiting until nothing plays" % version)
            STATE.set("waiting", version)
            if not sleep(WAIT_STEP):
                STATE.set("idle")
                return
        STATE.set("installing", version)
        old = install(z, version, kodiapi.addon_path(), kodiapi.temp_dir())
        kodiapi.log("update to %s: installed (previous add-on in %s), reloading" % (version, old))
        reload_addons()
    except Exception as e:  # noqa: BLE001 - reported to Home Assistant, the add-on keeps running
        STATE.set("failed", error=str(e)[:200])
        kodiapi.log("update failed: %s" % e, "error")
    finally:
        _lock.release()
