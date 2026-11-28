"""Kodi player: JSON-RPC (TCP port 9090, HTTP or over ssh) for state, volume and windows.

Real cameras: the player's own. Fake cameras (#77, needs ssh): the fake go2rtc runs on the Kodi device itself
(127.0.0.1) and the runner points the add-on at it through the API's /camalert/setup (#122: a local address is
always accepted), then sends the original go2rtc address back the same way. No screenshots (Kodi's TakeScreenshot
opens a dialog without a configured folder) and no PTZ on Kodi (it would move a real camera).
The chime setting is read over ssh when available; 'all' (rings for normal requests too) means skip.
"""
import re
import time

from .. import fakes, transport
from ..errors import SafetyError, Skip
from ..profiles import secret
from .camalert import CamAlert
from .enigma2 import Box

SETTINGS_XML = "/storage/.kodi/userdata/addon_data/service.camalert/settings.xml"
HOME = 10000


def jsonrpc_for(profile, environ=None, shell=None):
    kind = profile["jsonrpc"]
    if kind == "tcp":
        return transport.TcpJsonRpc(profile["host"], profile["jsonrpc_port"])
    if kind == "http":
        return transport.HttpJsonRpc("http://%s:%d/jsonrpc" % (profile["host"], profile["jsonrpc_port"]),
                                     secret(profile["jsonrpc_user_env"], environ),
                                     secret(profile["jsonrpc_password_env"], environ))
    return transport.SshJsonRpc(shell or transport.Ssh(profile["ssh"]), profile["jsonrpc_port"])


def setting_value(xml, key):
    m = re.search(r'<setting id="%s"[^>]*?(?:/>|>([^<]*)</setting>)' % re.escape(key), xml or "")
    return (m.group(1) or "") if m else None


class Kodi(object):
    kind = "kodi"
    screenshots = False  # no screenshot over JSON-RPC (TakeScreenshot opens a dialog without a folder)

    def __init__(self, profile, environ=None, http=transport.http, rpc=None, shell=None, sleep=time.sleep, box=None):
        self.p, self.sleep = profile, sleep
        if shell is None and profile.get("ssh"):
            shell = transport.Ssh(profile["ssh"])
        self.shell = shell
        self.rpc = rpc or jsonrpc_for(profile, environ, shell)
        self.camalert = CamAlert(profile["host"], profile["camalert_port"], secret(profile["token_env"], environ), http,
                                 sleep=sleep)
        self.box = box if box is not None else (Box(shell) if shell is not None else None)

    def app(self):
        return self.rpc.call("Application.GetProperties", {"properties": ["volume", "muted"]})

    def window(self):
        w = self.rpc.call("GUI.GetProperties", {"properties": ["currentwindow"]})["currentwindow"]
        return {"id": int(w.get("id", 0)), "label": w.get("label", "")}

    def info(self, now):
        players = self.rpc.call("Player.GetActivePlayers") or []
        recording = False
        try:
            recording = bool((self.rpc.call("PVR.GetProperties", {"properties": ["recording"]}) or {})
                             .get("recording"))
        except transport.TransportError:
            pass  # no PVR
        return {"standby": False, "recording": recording, "timer_soon": 0, "playing": len(players)}

    def snapshot(self):
        a, status = self.app(), self.camalert.status()
        return {"volume": int(a["volume"]), "muted": bool(a["muted"]), "window": self.window(),
                "dnd": bool(status.get("dnd")), "settings": {}}

    def wake(self, state, save):
        raise Skip("Kodi has no standby wake-up in the runner")

    def chime(self):
        """The chime setting ('off', 'high', 'all') or None when it cannot be read (no ssh)."""
        if self.shell is None:
            return None
        value = setting_value(self.shell.run("cat %s 2>/dev/null; true" % SETTINGS_XML), "chime")
        return value or "off"

    def prepare(self, state, save, fake):
        chime = self.chime()
        state["notes"].append("chime setting: %s" % (chime or "unknown (no ssh)"))
        if chime == "all":
            raise Skip("chime rings for every request (chime = all)")
        if fake:
            self._fake_cameras(state, save)

    def _fake_cameras(self, state, save):
        """#77: the fake go2rtc on the Kodi device and the add-on pointed at it (/camalert/setup)."""
        if self.box is None:
            raise Skip("fake cameras need ssh")
        if "setup" not in (self.camalert.status().get("capabilities") or []):
            raise Skip("fake cameras on Kodi need CamAlert 1.3 or newer (/camalert/setup)")
        original = setting_value(self.shell.run("cat %s 2>/dev/null; true" % SETTINGS_XML), "server")
        if not original:
            raise Skip("no go2rtc address to put back afterwards")
        ch = state["changes"]
        ch["server"] = original
        save()
        port = self.p["fake_go2rtc_port"]
        self.box.upload("go2rtc.py", fakes.go2rtc_source())
        ch.setdefault("processes", {})["go2rtc"] = self.box.start("go2rtc.py", "--port %d" % port)
        save()
        for _ in range(10):
            try:
                if fakes.NAMES[0] in self.box.fetch("http://127.0.0.1:%d/api/streams" % port):
                    break
            except transport.TransportError:
                pass
            self.sleep(0.5)
        else:
            raise SafetyError("fake go2rtc did not start on the Kodi device")
        self._setup("http://127.0.0.1:%d" % port)
        for _ in range(20):
            if fakes.NAMES[0] in self.camalert.camera_names():
                return
            self.sleep(0.5)
        raise SafetyError("the add-on does not list the fake cameras")

    def _setup(self, server):
        code, out = self.camalert.action("setup", server=server)
        if code != 200 or not (isinstance(out, dict) and out.get("result")):
            raise SafetyError("setup %s refused (%s)" % (server, out.get("error") if isinstance(out, dict) else code))

    def restore(self, state):
        problems = []
        before = state["before"]

        def attempt(what, fn):
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                problems.append("%s: %s" % (what, e))

        ch = state.get("changes") or {}
        attempt("hide", self.camalert.hide)
        if ch.get("server"):
            def server():
                self._setup(ch["server"])
                for _ in range(20):
                    if setting_value(self.shell.run("cat %s 2>/dev/null; true" % SETTINGS_XML), "server") == ch["server"]:
                        return
                    self.sleep(0.5)
                raise SafetyError("go2rtc address not back in the add-on settings")
            attempt("go2rtc address", server)
        for name, pid in sorted((ch.get("processes") or {}).items()):
            attempt("stop fake %s" % name, lambda pid=pid: self.box.stop(pid))
        if ch.get("processes"):
            attempt("remove fake files", self.box.cleanup)
        if "dnd" in before:
            attempt("dnd", lambda: self._restore_dnd(before["dnd"]))
        # only put back what differs: the runner never mutes (#102), so normally nothing is sent here
        now = {}
        attempt("volume read", lambda: now.update(self.app()))
        if int(now.get("volume", before["volume"])) != before["volume"]:
            attempt("volume", lambda: self.rpc.call("Application.SetVolume", {"volume": before["volume"]}))
        if bool(now.get("muted", before["muted"])) != before["muted"]:
            attempt("mute", lambda: self.rpc.call("Application.SetMute", {"mute": before["muted"]}))

        def check():
            a = self.app()
            if int(a["volume"]) != before["volume"] or bool(a["muted"]) != before["muted"]:
                raise SafetyError("volume/mute differ after restore")
        attempt("volume check", check)

        def window():
            self.sleep(1)
            if before.get("window", {}).get("id") == HOME and self.window()["id"] != HOME:
                self.rpc.call("GUI.ActivateWindow", {"window": "home"})
        attempt("window", window)
        return problems

    def _restore_dnd(self, dnd):
        if bool(self.camalert.status().get("dnd")) != dnd:
            self.camalert.set_dnd(dnd)

    def screenshot(self):
        return None

    def geometry_settings(self, state):
        return {}
