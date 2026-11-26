"""Enigma2 receiver: OpenWebif (state, volume, settings, OSD screenshot) and ssh (fake cameras on the receiver).

Lessons from the screenshot session (#1 phase 6): OpenWebif `/api/vol?set=mute` is a TOGGLE, so the state is always
read back; `/grab?mode=osd` has no video layer (no TV picture). No temporary API token (it would block Home
Assistant): instead the runner turns off what can make sound or reach other systems (chime, webhook, triggers)
through OpenWebif `saveconfig`, and restores the saved values afterwards.
"""
import time

from .. import fakes, transport
from ..errors import SafetyError, Skip
from ..profiles import secret
from .camalert import CamAlert

PREFIX = "config.plugins.camalert."
BOX_DIR = "/tmp/camalert-e2e"
DEVICES_FILE = "/etc/enigma2/camalert_devices.conf"
DEVICES_BACKUP = DEVICES_FILE + ".e2e-backup"

# Settings changed for every run: nothing rings, nothing reaches Home Assistant, no real trigger interferes, no rule
# hides a test request. Restored from the snapshot afterwards.
SAFE_SETTINGS = {"chime": "off", "ha_webhook": "", "cooldown": "", "limit_hours": False, "skip_playing": "off",
                 "skip_recording": False, "alarm_wake": False, "frigate_enabled": False, "foscam_enabled": False}
TIMER_MARGIN = 30 * 60
KEY_EXIT = 174
OSD_BUSY = 50  # opaque OSD samples (every 8th pixel) that mean a menu, dialog or CamAlert screen is open


def config_text(value):
    return ("true" if value else "false") if isinstance(value, bool) else str(value)


def restore_text(key, original, defaults):
    """The value to send to saveconfig to get `original` back. /api/settings shows booleans as 'True'/'False',
    but saveconfig only takes exactly 'true' as true (anything else is false): found on a real receiver."""
    default = defaults.get(key, "")
    if original is None:
        return config_text(default)
    if isinstance(default, bool):
        return "true" if str(original).strip().lower() in ("true", "1", "yes", "on") else "false"
    return original


def same_setting(a, b):
    return a == b or (a is not None and b is not None and str(a).lower() == str(b).lower())


class Box(object):
    """What the runner does on the receiver through ssh (replaced by a fake in the unit tests)."""

    def __init__(self, shell):
        self.shell = shell

    def upload(self, name, text):
        self.shell.run("mkdir -p %s && cat > %s/%s" % (BOX_DIR, BOX_DIR, name), text)

    def start(self, name, args):
        out = self.shell.run("cd %s && (nohup python3 %s %s > %s.log 2>&1 & echo $!)" % (BOX_DIR, name, args, name))
        return int(out.strip().splitlines()[-1])

    def stop(self, pid):
        self.shell.run("kill %d 2>/dev/null; sleep 1; kill -0 %d 2>/dev/null && echo running || echo stopped"
                       % (pid, pid), check=False)

    def fetch(self, url):
        """GET a URL on the receiver itself (the fakes listen on 127.0.0.1 only)."""
        code = "import urllib.request as u,sys;sys.stdout.write(u.urlopen(%r,timeout=5).read().decode())" % url
        return self.shell.run("python3 -c %s" % transport.quote(code))

    def swap_devices(self):
        """Moves the real camera devices file aside (on the receiver, never copied off it) and writes the fake one.
        Returns 'existed' or 'absent'. Refuses when an old backup is still there (restore that first)."""
        out = self.shell.run("if [ -e %s ]; then echo backup-exists; elif [ -e %s ]; then cp -p %s %s && echo existed;"
                             " else echo absent; fi" % (DEVICES_BACKUP, DEVICES_FILE, DEVICES_FILE, DEVICES_BACKUP))
        how = out.strip()
        if how == "backup-exists":
            raise Skip("an old devices backup is still on the receiver: run --restore last first")
        return how

    def write_devices(self, content):
        self.shell.run("cat > %s && chmod 600 %s" % (DEVICES_FILE, DEVICES_FILE), content)

    def restore_devices(self, how):
        if how == "existed":
            self.shell.run("[ -e %s ] && cp -p %s %s && rm -f %s; true" % (DEVICES_BACKUP, DEVICES_BACKUP,
                                                                           DEVICES_FILE, DEVICES_BACKUP))
        elif how == "absent":
            self.shell.run("rm -f %s" % DEVICES_FILE)
        out = self.shell.run("[ -e %s ] && echo left || echo ok" % DEVICES_BACKUP).strip()
        return out == "ok"

    def cleanup(self):
        self.shell.run("rm -rf %s" % BOX_DIR, check=False)

    def read_ptz_calls(self):
        return self.shell.run("cat %s/ptz-calls.txt 2>/dev/null; true" % BOX_DIR)


class Enigma2(object):
    kind = "enigma2"

    def __init__(self, profile, environ=None, http=transport.http, box=None, sleep=time.sleep):
        self.p, self.http, self.sleep = profile, http, sleep
        self.base = "http://%s:%d" % (profile["host"], profile["openwebif_port"])
        self.headers = transport.basic_auth(secret(profile["openwebif_user_env"], environ),
                                            secret(profile["openwebif_password_env"], environ))
        self.camalert = CamAlert(profile["host"], profile["camalert_port"], secret(profile["token_env"], environ), http,
                                 sleep=sleep)
        if box is None and profile.get("ssh"):
            box = Box(transport.Ssh(profile["ssh"]))
        self.box = box

    # --- OpenWebif ---------------------------------------------------------------------------------------------
    def api(self, path, data=None):
        code, body = self.http(self.base + path, "POST" if data is not None else "GET", data, self.headers)
        if code != 200 or not isinstance(body, dict):
            raise transport.TransportError("OpenWebif %s: status %s" % (path.split("?")[0], code))
        return body

    def vol(self, cmd=None):
        out = self.api("/api/vol" + ("?set=%s" % cmd if cmd else ""))
        return {"volume": int(out.get("current", 0)), "muted": bool(out.get("ismute"))}

    def statusinfo(self):
        s = self.api("/api/statusinfo")
        return {"service": s.get("currservice_serviceref") or "", "volume": int(s.get("volume") or 0),
                "muted": bool(s.get("muted")), "standby": str(s.get("inStandby")).lower() == "true",
                "recording": str(s.get("isRecording")).lower() == "true"}

    def saved_settings(self):
        """{key without prefix: saved text} of the CamAlert settings that differ from their default."""
        out = self.api("/api/settings").get("settings") or []
        pairs = out.items() if isinstance(out, dict) else out
        return {k[len(PREFIX):]: v for k, v in pairs if k.startswith(PREFIX)}

    def set_config(self, key, value):
        out = self.api("/api/saveconfig", {"key": PREFIX + key, "value": config_text(value)})
        if not out.get("result"):
            raise SafetyError("could not change setting %s" % key)

    # --- interface ---------------------------------------------------------------------------------------------
    def info(self, now):
        s = self.statusinfo()
        timers = self.api("/api/timerlist").get("timers") or []
        soon = [t for t in timers if not int(t.get("disabled") or 0)
                and int(t.get("begin") or 0) - TIMER_MARGIN <= now <= int(t.get("end") or 0)]
        return {"standby": s["standby"], "recording": s["recording"], "timer_soon": len(soon), "playing": None,
                "osd_busy": not s["standby"] and self.osd_opaque() > OSD_BUSY}

    def snapshot(self):
        s = self.statusinfo()
        status = self.camalert.status()
        return {"service": s["service"], "volume": s["volume"], "muted": s["muted"], "standby": s["standby"],
                "dnd": bool(status.get("dnd")), "settings": self.saved_settings()}

    def wake(self, state, save):
        state["changes"]["woken"] = True
        save()
        self.api("/api/powerstate?newstate=4")
        for _ in range(20):
            if not self.statusinfo()["standby"]:
                return
            self.sleep(0.5)
        raise SafetyError("receiver did not wake up")

    def prepare(self, state, save, fake):
        """Safe settings, and with fake cameras: the fake go2rtc and PTZ camera on the receiver."""
        ch = state["changes"]
        want = dict(SAFE_SETTINGS)
        if fake:
            if self.box is None:
                raise Skip("fake cameras need ssh")
            want.update({"source": "go2rtc", "server": "http://127.0.0.1:%d" % self.p["fake_go2rtc_port"],
                         "camera": fakes.NAMES[0], "mosaic": ""})
        saved = state["before"]["settings"]
        ch.setdefault("settings", {})
        for key in sorted(want):
            if key not in ch["settings"]:
                ch["settings"][key] = saved.get(key)  # None = was the default
        save()
        for key in sorted(want):
            self.set_config(key, want[key])
        if not fake:
            return
        procs = ch.setdefault("processes", {})
        self.box.upload("go2rtc.py", fakes.go2rtc_source())
        self.box.upload("fake_ptz.py", fakes.ptz_source())
        procs["go2rtc"] = self.box.start("go2rtc.py", "--port %d" % self.p["fake_go2rtc_port"])
        procs["ptz"] = self.box.start("fake_ptz.py", "--port %d --calls %s/ptz-calls.txt"
                                      % (self.p["fake_ptz_port"], BOX_DIR))
        save()
        for _ in range(10):
            try:
                if fakes.NAMES[0] in self.box.fetch("http://127.0.0.1:%d/api/streams" % self.p["fake_go2rtc_port"]):
                    break
            except transport.TransportError:
                pass
            self.sleep(0.5)
        else:
            raise SafetyError("fake go2rtc did not start on the receiver")
        ch["devices_file"] = "pending"
        save()
        try:
            ch["devices_file"] = self.box.swap_devices()
        except Skip:
            ch["devices_file"] = "untouched"
            raise
        finally:
            save()
        self.box.write_devices(fakes.devices_line(self.p["fake_ptz_port"]))

    def restore(self, state):
        """Undo everything in state['changes'] and put back what the snapshot says. Returns a list of problems."""
        problems = []
        before, ch = state["before"], state["changes"]

        def attempt(what, fn):
            try:
                fn()
            except Exception as e:  # noqa: BLE001 - keep restoring the rest
                problems.append("%s: %s" % (what, e))

        attempt("hide", self.camalert.hide)
        attempt("close screens", self.clear_screens)
        if ch.get("devices_file") in ("existed", "absent"):
            def devices():
                if not self.box.restore_devices(ch["devices_file"]):
                    raise SafetyError("devices backup still on the receiver")
            attempt("devices file", devices)
        elif ch.get("devices_file") == "pending":
            problems.append("devices file: state unknown, check %s on the receiver" % DEVICES_BACKUP)
        for name, pid in sorted((ch.get("processes") or {}).items()):
            attempt("stop fake %s" % name, lambda pid=pid: self.box.stop(pid))
        if ch.get("processes"):
            attempt("remove fake files", self.box.cleanup)
        schema = fakes.schema_defaults()
        for key, original in sorted((ch.get("settings") or {}).items()):
            value = restore_text(key, original, schema)
            attempt("setting %s" % key, lambda key=key, value=value: self.set_config(key, value))
        if "dnd" in before:
            attempt("dnd", lambda: self._restore_dnd(before["dnd"]))
        attempt("channel", lambda: self._restore_service(before.get("service")))
        attempt("volume", lambda: self._restore_volume(before))
        if ch.get("woken"):
            attempt("standby", self._standby)
        try:
            after = self.saved_settings()
            wrong = [k for k, orig in (ch.get("settings") or {}).items() if not same_setting(after.get(k), orig)]
            if wrong:
                problems.append("settings differ after restore: %s" % ", ".join(sorted(wrong)))
        except Exception as e:  # noqa: BLE001
            problems.append("settings check: %s" % e)
        return problems

    def _restore_dnd(self, dnd):
        if bool(self.camalert.status().get("dnd")) != dnd:
            self.camalert.set_dnd(dnd)

    def _restore_service(self, ref):
        if ref and self.statusinfo()["service"] != ref:
            self.api("/api/zap?sRef=" + transport.urllib.parse.quote(ref, safe=""))

    def _restore_volume(self, before):
        v = self.vol()
        if v["volume"] != before["volume"]:
            v = self.vol("set%d" % before["volume"])
        if v["muted"] != before["muted"]:
            v = self.vol("mute")  # toggle once and read back
            if v["muted"] != before["muted"]:
                raise SafetyError("mute state could not be restored")

    def _standby(self):
        self.api("/api/powerstate?newstate=5")

    def osd_opaque(self):
        """Number of opaque OSD samples (every 8th pixel); 0 = nothing drawn over the TV picture. Not stored."""
        from .. import geometry
        img = geometry.load(self.screenshot())
        return sum(1 for y in range(0, img.height, 8) for x in range(0, img.width, 8) if img.pixel(x, y)[3] > 128)

    def clear_screens(self):
        """Closes CamAlert screens that hide left open (Enigma2 hide does not close tour/mosaic, #63) with EXIT.
        Only used when the OSD was clear before the run (precondition). Returns the number of EXIT presses."""
        for presses in range(5):
            if self.osd_opaque() <= OSD_BUSY:
                return presses
            if presses == 4:
                break
            self.api("/api/remotecontrol?command=%d" % KEY_EXIT)
            self.sleep(1.5)
        raise SafetyError("screens still open after 4x EXIT")

    def screenshot(self):
        code, data = self.http(self.base + "/grab?format=png&mode=osd", headers=self.headers, raw=True, timeout=20)
        if code != 200 or not data.startswith(b"\x89PNG"):
            raise transport.TransportError("OSD screenshot failed (status %s)" % code)
        return data

    def ptz_calls(self):
        return [x for x in self.box.read_ptz_calls().splitlines() if x.strip()]

    def geometry_settings(self, state):
        d = fakes.schema_defaults()
        saved = state["before"]["settings"]
        return {k: saved.get(k, d[k]) for k in ("position", "size", "title_size", "strip_layout")}
