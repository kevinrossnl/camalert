"""Android TV / Fire TV player (#68, #77): adb for the device state and the fake go2rtc, the CamAlert API for the rest.

The runner talks to the device with adb over the network (`adb connect host:port` first; the profile's `adb` is the
adb binary). State: screen on/off (`dumpsys power`), something playing (`dumpsys media_session`), the app in front
(`dumpsys activity`), the music volume (`media volume`). Nothing is muted (#102).

Fake cameras: the fake go2rtc of players/androidtv/testing/fake_go2rtc_on_device.py on the device itself
(127.0.0.1:11984, toybox nc), the app pointed at it with /camalert/setup (#122) and afterwards back to the profile's
`restore_server` (the app's settings are private: the runner cannot read the old address, so the profile names it).
Screenshots: `adb exec-out screencap -p` (the launcher behind CamAlert's window is never kept: the report only holds
geometry checks of solid-colour test frames).
"""
import importlib.util
import os
import re
import subprocess
import tempfile
import time

from .. import transport
from ..errors import SafetyError, Skip
from ..profiles import secret
from .camalert import CamAlert

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
FAKE_TOOL = os.path.join(ROOT, "players", "androidtv", "testing", "fake_go2rtc_on_device.py")
LAUNCHERS = ("com.amazon.tv.launcher", "com.google.android.leanbacklauncher", "com.google.android.tvlauncher",
             "com.google.android.apps.tv.launcherx")


def _fake_tool():
    spec = importlib.util.spec_from_file_location("camalert_e2e_fake_on_device", FAKE_TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Adb(object):
    """adb against one device (replaced by a fake in the unit tests)."""

    def __init__(self, serial, adb="adb", run=subprocess.run):
        self.serial, self.adb, self.run = serial, adb, run

    def _call(self, args, binary=False):
        out = self.run([self.adb] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        data = out.stdout or b""
        return data if binary else data.decode("utf-8", "replace")

    def connect(self):
        text = self._call(["connect", self.serial])
        if "connected" not in text:
            raise transport.TransportError("adb connect %s: %s" % (self.serial, text.strip()))

    def shell(self, cmd):
        return self._call(["-s", self.serial, "shell", cmd])

    def push(self, local, remote):
        self._call(["-s", self.serial, "push", local, remote])

    def screencap(self):
        data = self._call(["-s", self.serial, "exec-out", "screencap", "-p"], binary=True)
        if not data.startswith(b"\x89PNG"):
            raise transport.TransportError("screencap gave no PNG")
        return data


def parse_volume(text):
    m = re.search(r"volume is (\d+)", text or "")
    return int(m.group(1)) if m else None


def parse_awake(text):
    m = re.search(r"mWakefulness=(\w+)", text or "")
    return (m.group(1) == "Awake") if m else True


def parse_playing(text):
    """Number of media sessions in state PLAYING (3)."""
    return len(re.findall(r"state=PlaybackState \{state=3\b", text or ""))


def parse_front(text):
    m = re.search(r"mResumedActivity: ActivityRecord\{\S+ \S+ ([\w.]+)/", text or "")
    return m.group(1) if m else ""


class AndroidTv(object):
    kind = "androidtv"
    screenshots = True

    def __init__(self, profile, environ=None, http=transport.http, adb=None, sleep=time.sleep):
        self.p, self.sleep = profile, sleep
        self.adb = adb or Adb("%s:%d" % (profile["host"], profile["adb_port"]), profile["adb"])
        self.camalert = CamAlert(profile["host"], profile["camalert_port"], secret(profile["token_env"], environ), http,
                                 sleep=sleep)
        self.box = None
        self._connected = False

    def _sh(self, cmd):
        if not self._connected:
            self.adb.connect()
            self._connected = True
        return self.adb.shell(cmd)

    def volume(self):
        return parse_volume(self._sh("media volume --stream 3 --get"))

    def front(self):
        return parse_front(self._sh("dumpsys activity activities | grep -m1 mResumedActivity"))

    def info(self, now):
        awake = parse_awake(self._sh("dumpsys power | grep -m1 mWakefulness="))
        return {"standby": not awake, "recording": False, "timer_soon": 0,
                "playing": parse_playing(self._sh("dumpsys media_session")), "osd_busy": False}

    def snapshot(self):
        status = self.camalert.status()
        return {"volume": self.volume(), "muted": False, "front": self.front(), "dnd": bool(status.get("dnd")),
                "settings": {}}

    def wake(self, state, save):
        state["changes"]["woken"] = True
        save()
        self._sh("input keyevent KEYCODE_WAKEUP")
        for _ in range(20):
            if parse_awake(self._sh("dumpsys power | grep -m1 mWakefulness=")):
                return
            self.sleep(0.5)
        raise SafetyError("device did not wake up")

    def prepare(self, state, save, fake):
        if not fake:
            return
        if "setup" not in (self.camalert.status().get("capabilities") or []):
            raise Skip("fake cameras on Android TV need CamAlert 1.3 or newer (/camalert/setup)")
        if not self.p.get("restore_server"):
            raise Skip("fake cameras need restore_server in the profile (the app's go2rtc address)")
        tool = _fake_tool()
        ch = state["changes"]
        ch["server"] = self.p["restore_server"]
        ch["fake_go2rtc"] = True
        save()
        self._sh(tool.stop_command())
        with tempfile.TemporaryDirectory() as d:
            tool.files(d, unreachable="")
            self._sh("mkdir -p %s" % tool.DIR)
            self.adb.push(d + "/.", tool.DIR + "/")
        self._sh(tool.start_command())
        self._setup("http://127.0.0.1:%d" % tool.PORT)
        from .. import fakes
        for _ in range(20):
            if fakes.NAMES[0] in self.camalert.camera_names():
                return
            self.sleep(0.5)
        raise SafetyError("the app does not list the fake cameras")

    def _setup(self, server):
        code, out = self.camalert.action("setup", server=server)
        if code != 200 or not (isinstance(out, dict) and out.get("result")):
            raise SafetyError("setup %s refused (%s)" % (server, out.get("error") if isinstance(out, dict) else code))

    def restore(self, state):
        problems = []
        before, ch = state["before"], state.get("changes") or {}

        def attempt(what, fn):
            try:
                fn()
            except Exception as e:  # noqa: BLE001 - keep restoring the rest
                problems.append("%s: %s" % (what, e))

        attempt("hide", self.camalert.hide)
        if ch.get("server"):
            attempt("go2rtc address", lambda: self._setup(ch["server"]))
        if ch.get("fake_go2rtc"):
            attempt("stop fake go2rtc", lambda: self._sh(_fake_tool().stop_command()))
        if "dnd" in before:
            attempt("dnd", lambda: self._restore_dnd(before["dnd"]))

        def volume():
            now = self.volume()
            if before.get("volume") is not None and now is not None and now != before["volume"]:
                self._sh("media volume --stream 3 --set %d" % before["volume"])
        attempt("volume", volume)

        def front():
            self.sleep(1)
            if before.get("front") in LAUNCHERS and self.front() not in LAUNCHERS:
                self._sh("input keyevent KEYCODE_HOME")
        attempt("app in front", front)
        if ch.get("woken"):
            attempt("sleep", lambda: self._sh("input keyevent KEYCODE_SLEEP"))
        return problems

    def _restore_dnd(self, dnd):
        if bool(self.camalert.status().get("dnd")) != dnd:
            self.camalert.set_dnd(dnd)

    def screenshot(self):
        return self.adb.screencap()

    def geometry_settings(self, state):
        from .. import fakes
        d, st = fakes.schema_defaults(), self.camalert.status()
        return {k: st.get(k) or d[k] for k in ("position", "size", "title_size", "strip_layout")}
