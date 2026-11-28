# -*- coding: utf-8 -*-
# CamAlert - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Updating the plugin from Home Assistant (#126).

The release ipk is downloaded from CamAlert's fixed GitHub URL and checked against SHA256SUMS
(camalert_core.selfupdate) in a thread. It is installed only while the receiver is in standby and no recording runs
or starts within 10 minutes; until then the state is "waiting" and the check runs every minute. After `opkg install`
the GUI restarts quietly (no TV wake-up via CEC) and the receiver goes back to standby.
"""
import os
import subprocess
import time
import urllib.request

from twisted.internet import reactor, threads

from . import __version__
from .camalert_core import selfupdate

IPK = "/tmp/camalert-update.ipk"
BACK_TO_STANDBY = "/tmp/camalert-update-standby"  # read by after_restart(): back to standby after the restart
NO_TV_WAKE = "/tmp/powerup_without_waking_tv.txt"  # openATV: do not switch the TV on (CEC) at the restart
RECORDING_MARGIN = 600  # seconds: no install when a recording starts within 10 minutes
CHECK_EVERY = 60
STATE = selfupdate.UpdateState()
_pending = {"version": None, "timer": None}


def log(*args, **kw):
    from .display import log as _log
    _log(*args, **kw)


# --- the parts tests replace -------------------------------------------------------------------------------------
def opener(url):
    req = urllib.request.Request(url, headers={"User-Agent": "CamAlert/%s" % __version__})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(selfupdate.MAX_BYTES + 1)


def run_opkg(path):
    """(ok, last output line) of `opkg install <path>`."""
    p = subprocess.run(["opkg", "install", path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
    out = p.stdout.decode("utf-8", "replace").strip().splitlines()
    return p.returncode == 0, out[-1] if out else ""


def in_standby():
    try:
        from Screens.Standby import inStandby
        return inStandby is not None
    except ImportError:
        return False


def recording_soon(now=None):
    """True while a recording runs or starts within RECORDING_MARGIN (unknown = False)."""
    try:
        import NavigationInstance
        rt = NavigationInstance.instance.RecordTimer
        if rt.isRecording():
            return True
        nxt = rt.getNextRecordingTime()
        now = time.time() if now is None else now
        return nxt > 0 and nxt - now < RECORDING_MARGIN
    except Exception:  # noqa: BLE001 - no record timer on this image: nothing records
        return False


def restart_gui():
    from Screens.Standby import TryQuitMainloop
    from .display import Controller
    Controller.instance.session.open(TryQuitMainloop, 3)


# --- the flow ----------------------------------------------------------------------------------------------------
def start(version):
    """Called on the main thread by the API (#126); the version is already checked."""
    STATE.set("downloading", version)
    log("update to %s: downloading" % version)
    threads.deferToThread(_download, version).addCallbacks(lambda _r: _downloaded(version), _failed)


def _download(version):
    _name, data = selfupdate.fetch("enigma2", version, opener)
    with open(IPK + ".tmp", "wb") as f:
        f.write(data)
    os.replace(IPK + ".tmp", IPK)


def _downloaded(version):
    _pending["version"] = version
    try_install()


def ready():
    return in_standby() and not recording_soon()


def try_install():
    """Installs the downloaded release when the receiver is idle, else waits (state "waiting")."""
    version = _pending["version"]
    if version is None:
        return
    if not ready():
        if STATE.state != "waiting":
            log("update to %s: waiting for standby without a recording" % version)
        STATE.set("waiting", version)
        _schedule()
        return
    _pending["version"] = None
    STATE.set("installing", version)
    log("update to %s: installing" % version)
    threads.deferToThread(run_opkg, IPK).addCallbacks(lambda r: _installed(version, r), _failed)


def _schedule():
    t = _pending.get("timer")
    if t is not None and t.active():
        return
    _pending["timer"] = reactor.callLater(CHECK_EVERY, try_install)


def _installed(version, result):
    ok, line = result
    try:
        os.remove(IPK)
    except OSError:
        pass
    if not ok:
        _failed_text("opkg: %s" % line)
        return
    log("update to %s: installed, restarting the GUI" % version)
    for path, text in ((BACK_TO_STANDBY, version), (NO_TV_WAKE, "True")):
        try:
            with open(path, "w") as f:
                f.write(text)
        except OSError:
            pass
    restart_gui()


def _failed(err):
    _failed_text(err.getErrorMessage() if hasattr(err, "getErrorMessage") else str(err))


def _failed_text(text):
    _pending["version"] = None
    STATE.set("failed", error=text[:200])
    log("update failed:", text, level="error")


def after_restart(session):
    """At plugin start: after an update from Home Assistant, go back to standby (the receiver was in standby)."""
    if not os.path.exists(BACK_TO_STANDBY):
        return False
    try:
        os.remove(BACK_TO_STANDBY)
    except OSError:
        pass
    log("updated to %s by Home Assistant" % __version__)
    if not in_standby():
        from Screens.Standby import Standby
        session.open(Standby)
    return True
