"""The run per device: preconditions -> snapshot (on disk) -> mute (verified) -> wake -> prepare -> scenarios,
and in `finally` always restore. Also `--restore last` and `--dry-run`."""
import datetime
import os
import signal
import time

from . import report as report_mod
from . import scenarios as sc
from .adapters.enigma2 import Enigma2
from .adapters.ha import HomeAssistant
from .adapters.kodi import Kodi
from .errors import SafetyError, Skip
from .fakes import CAMERAS, NAMES, ROOT
from .profiles import secret
from .safety import preconditions
from .state import Store

REPORTS = os.path.join(ROOT, "reports")


class Timeout(Exception):
    pass


def make_device(profile, environ=None):
    return (Enigma2 if profile["type"] == "enigma2" else Kodi)(profile, environ)


def make_ha(ha_cfg, environ=None):
    token = secret(ha_cfg.get("token_env"), environ)
    return HomeAssistant(ha_cfg["url"], token) if ha_cfg.get("url") and token else None


class Runner(object):
    def __init__(self, devices, ha_cfg, options, reports=REPORTS, environ=None, factory=make_device, ha=None,
                 now=None, sleep=time.sleep, clock=time.time, log=print, use_alarm=True):
        self.devices, self.options, self.reports, self.environ = devices, options, reports, environ
        self.factory, self.sleep, self.clock, self.log, self.use_alarm = factory, sleep, clock, log, use_alarm
        self.ha = ha if ha is not None else make_ha(ha_cfg, environ)
        self.now = now or datetime.datetime.now
        self.store = Store(reports)
        self.folder = os.path.join(reports, self.store.run_id)
        self.words = {}

    # --- privacy of the report -------------------------------------------------------------------------------------
    def hide_words(self, profile):
        self.words[profile["host"]] = "<%s>" % profile["name"]
        if profile.get("ssh"):
            self.words[profile["ssh"]] = "<ssh:%s>" % profile["name"]
        for key in ("token_env", "openwebif_user_env", "openwebif_password_env", "jsonrpc_user_env",
                    "jsonrpc_password_env"):
            value = secret(profile.get(key), self.environ)
            if value:
                self.words[value] = "<secret>"

    def cameras(self, dev, profile, fake):
        """(names, colours or None). Real cameras are named cam1.. in the report."""
        if fake:
            return list(NAMES), dict(CAMERAS)
        names = list(profile["real_cameras"]) or dev.camalert.camera_names()[:4]
        if not names:
            raise Skip("the player lists no cameras")
        for i, n in enumerate(names):
            self.words[n] = "cam%d" % (i + 1)
        return names, None

    # --- one device ------------------------------------------------------------------------------------------------
    def run_device(self, name, selected):
        profile = self.devices[name]
        self.hide_words(profile)
        res = {"device": name, "type": profile["type"], "status": "passed", "reason": "", "preconditions": [],
               "scenarios": [], "restore": []}
        try:
            dev = self.factory(profile, self.environ)
            n = self.now()
            info = dev.info(time.time())
        except Exception as e:  # noqa: BLE001
            return dict(res, status="skipped", reason="not reachable: %s" % e)
        checks = preconditions(profile, info, n.hour * 60 + n.minute, self.options, self.ha)
        res["preconditions"] = [c.as_dict() for c in checks]
        failed = [c for c in checks if not c.ok]
        if failed:
            return dict(res, status="skipped", reason="; ".join("%s (%s)" % (c.name, c.detail) for c in failed))
        fake = profile["cameras"] == "fake"
        if self.options.get("dry_run"):
            snap = dev.snapshot()
            res["plan"] = {"cameras": profile["cameras"], "scenarios": selected, "standby": info.get("standby"),
                           "volume": snap.get("volume"), "muted": snap.get("muted"), "dnd": snap.get("dnd")}
            return dict(res, status="dry-run")
        state = self.store.device(name, profile["type"])
        state["before"] = dev.snapshot()
        self.store.save()
        save = self.store.save
        self._alarm(profile["timeout"])
        try:
            res["mute"] = dev.mute(state, save)
            if not dev.verify_quiet():
                raise SafetyError("device does not report muted / volume 0")
            if info.get("standby"):
                dev.wake(state, save)
                if not dev.verify_quiet():
                    raise SafetyError("not muted after waking up")
            dev.prepare(state, save, fake)
            if dev.camalert.status().get("dnd"):
                dev.camalert.set_dnd(False)
            if not dev.verify_quiet():
                raise SafetyError("not muted after preparing")
            res["test_flag"] = dev.camalert.supports_test_flag()
            cams, colours = self.cameras(dev, profile, fake)
            ctx = sc.Context(dev, state, cams, colours, dev.geometry_settings(state), self._shooter(dev, name),
                             self.ha, self.sleep, self.clock)
            for s in selected:
                self.log("  %s: %s ..." % (name, s))
                first = len(ctx.shot.files)
                r = sc.run(s, ctx)
                r.screenshots = ctx.shot.files[first:]
                res["scenarios"].append(r.as_dict())
                self.log("  %s: %s %s" % (name, s, r.status))
            if any(r["status"] == "failed" for r in res["scenarios"]):
                res["status"] = "failed"
        except Skip as e:
            res.update(status="skipped", reason=str(e))
        except (SafetyError, Timeout, Exception) as e:  # noqa: BLE001 - always restore
            res.update(status="error", reason="%s: %s" % (e.__class__.__name__, e))
        finally:
            self._alarm(0)
            res["restore"] = self.restore_state(dev, state)
            res["notes"] = list(state["notes"])
        if res["restore"] and res["status"] != "error":
            res.update(status="error", reason="restore problems")
        return res

    def restore_state(self, dev, state):
        problems = dev.restore(state)
        state["problems"], state["restored"] = problems, not problems
        self.store.save()
        return problems

    def _alarm(self, seconds):
        if not self.use_alarm or not hasattr(signal, "SIGALRM"):
            return

        def boom(*_a):
            raise Timeout("global device timeout")
        signal.signal(signal.SIGALRM, boom)
        signal.alarm(int(seconds))

    def _shooter(self, dev, name):
        folder = os.path.join(self.folder, "screenshots")
        files = []

        def shot(label):
            data = dev.screenshot()
            os.makedirs(folder, exist_ok=True)
            fn = "%s-%s.png" % (name, label)
            with open(os.path.join(folder, fn), "wb") as f:
                f.write(data)
            files.append("screenshots/" + fn)
            return data
        shot.files = files
        return shot

    # --- the whole run ---------------------------------------------------------------------------------------------
    def run(self, names, selected):
        """selected: a list of scenarios for every device, or {device: [scenarios]}."""
        results = []
        for name in names:
            self.log("%s:" % name)
            res = self.run_device(name, selected[name] if isinstance(selected, dict) else selected)
            self.log("%s: %s %s" % (name, res["status"], res.get("reason", "")))
            results.append(res)
        data = {"run": self.store.run_id, "dry_run": bool(self.options.get("dry_run")), "devices": results}
        return report_mod.write(self.folder, data, self.words)


def restore_last(devices, reports=REPORTS, environ=None, factory=make_device, log=print, which="last"):
    """Restores every device of a run that is not marked restored. Returns the list of remaining problems."""
    try:
        store = Store.load(reports, which)
    except (OSError, ValueError, KeyError):
        log("no earlier run to restore")
        return []
    problems = []
    for st in store.pending():
        name = st["device"]
        if name not in devices:
            problems.append("%s: no profile" % name)
            continue
        dev = factory(devices[name], environ)
        found = dev.restore(st)
        st["problems"], st["restored"] = found, not found
        store.save()
        log("%s: %s" % (name, "restored" if not found else "; ".join(found)))
        problems += ["%s: %s" % (name, p) for p in found]
    if not store.pending():
        log("nothing left to restore in run %s" % store.run_id)
    return problems
