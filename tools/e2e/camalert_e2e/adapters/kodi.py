"""Kodi player: JSON-RPC (TCP port 9090, HTTP or over ssh) for state, volume and windows.

v1.0 uses the player's own (real) cameras: Kodi add-on settings cannot be changed through JSON-RPC, so there are no
fake cameras, no screenshots (they would show a camera picture) and no PTZ on Kodi (it would move a real camera).
The chime setting is read over ssh when available; 'all' (rings for normal requests too) means skip.
"""
import re
import time

from .. import transport
from ..errors import SafetyError, Skip
from ..profiles import secret
from .camalert import CamAlert

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

    def __init__(self, profile, environ=None, http=transport.http, rpc=None, shell=None, sleep=time.sleep):
        self.p, self.sleep = profile, sleep
        if shell is None and profile.get("ssh"):
            shell = transport.Ssh(profile["ssh"])
        self.shell = shell
        self.rpc = rpc or jsonrpc_for(profile, environ, shell)
        self.camalert = CamAlert(profile["host"], profile["camalert_port"], secret(profile["token_env"], environ), http,
                                 sleep=sleep)
        self.box = None

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

    def mute(self, state, save):
        """Application.SetMute takes a boolean (no toggle); read back. Volume 0 if mute is not confirmed."""
        ch = state["changes"]
        if self.app()["muted"]:
            ch["mute"] = "already"
            save()
            return "already muted"
        ch["mute"] = "pending"
        save()
        self.rpc.call("Application.SetMute", {"mute": True})
        if self.app()["muted"]:
            ch["mute"] = "mute"
            save()
            return "muted"
        ch["mute"] = "volume0"
        save()
        self.rpc.call("Application.SetVolume", {"volume": 0})
        if int(self.app()["volume"]) == 0:
            return "volume 0 (mute not confirmed)"
        raise SafetyError("could not mute or set the volume to 0")

    def verify_quiet(self):
        a = self.app()
        return bool(a["muted"]) or int(a["volume"]) == 0

    def wake(self, state, save):
        raise Skip("Kodi has no standby wake-up in the runner")

    def chime(self):
        """The chime setting ('off', 'high', 'all') or None when it cannot be read (no ssh)."""
        if self.shell is None:
            return None
        value = setting_value(self.shell.run("cat %s 2>/dev/null; true" % SETTINGS_XML), "chime")
        return value or "off"

    def prepare(self, state, save, fake):
        if fake:
            raise Skip("fake cameras are Enigma2 only in v1.0")
        chime = self.chime()
        state["notes"].append("chime setting: %s" % (chime or "unknown (no ssh)"))
        if chime == "all":
            raise Skip("chime rings for every request (chime = all)")

    def restore(self, state):
        problems = []
        before = state["before"]

        def attempt(what, fn):
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                problems.append("%s: %s" % (what, e))

        attempt("hide", self.camalert.hide)
        if "dnd" in before:
            attempt("dnd", lambda: self._restore_dnd(before["dnd"]))
        attempt("volume", lambda: self.rpc.call("Application.SetVolume", {"volume": before["volume"]}))
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
