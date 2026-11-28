#!/usr/bin/env python3
"""Smoke test of the Kodi add-on in a real, headless Kodi (#37): nightly on the workstation runner, never per push.

    python3 tests/kodi_container/smoke.py [--kodi kodi] [--keep]

Needs Kodi (Debian/Ubuntu package `kodi`), Xvfb (`xvfb-run`) and python3; the nightly job installs them in a
Debian container. Everything happens in a temporary HOME, so a real Kodi profile is never touched:

1. builds the add-on zip (tools/build_kodi.py) and unpacks it into the temporary Kodi profile, with the web server
   (JSON-RPC over HTTP, port 8080, no login, only 127.0.0.1) switched on in guisettings.xml;
2. starts the fake go2rtc (tests/fakes/go2rtc.py, solid-colour demo cameras) on 127.0.0.1 and Kodi under Xvfb;
3. enables the add-on over JSON-RPC (Kodi disables add-ons it did not install itself), waits for /camalert/status;
4. points the add-on at the fake go2rtc with /camalert/setup (#122: a never set up player accepts it);
5. shows the photo window (`test=1`, no chime), checks /camalert/status (`window`, `screen`) and that Kodi shows a
   dialog, opens the mosaic, hides both and checks `screen` = none;
6. stops Kodi and fails on any Python exception of the add-on in kodi.log.

Exit 0 when every check passed. Prints one line per check. Copyright (C) 2026 CamAlert developers, GPL v2.
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GO2RTC = os.path.join(ROOT, "tests", "fakes", "go2rtc.py")
WEB_PORT, API_PORT, FAKE_PORT = 8080, 8099, 19841
GUISETTINGS = """<settings version="2">
    <setting id="services.webserver">true</setting>
    <setting id="services.webserverport">%d</setting>
    <setting id="services.webserverauthentication">false</setting>
    <setting id="services.webserverusername">kodi</setting>
    <setting id="services.esallinterfaces">false</setting>
    <setting id="addons.unknownsources">true</setting>
</settings>
""" % WEB_PORT


class Checks(object):
    def __init__(self):
        self.failed = []

    def check(self, ok, text):
        print("%s %s" % ("ok  " if ok else "FAIL", text))
        if not ok:
            self.failed.append(text)
        return ok


def http(url, data=None, timeout=10):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method="POST" if body else "GET",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "null")


def rpc(method, params=None):
    out = http("http://127.0.0.1:%d/jsonrpc" % WEB_PORT,
               {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
    if "error" in out:
        raise RuntimeError("%s: %s" % (method, out["error"]))
    return out["result"]


def api(name, **params):
    if params:
        return http("http://127.0.0.1:%d/camalert/%s" % (API_PORT, name), dict(params, test="1"))
    return http("http://127.0.0.1:%d/camalert/%s" % (API_PORT, name))


def wait(fn, timeout, step=1.0):
    end = time.time() + timeout
    while time.time() < end:
        try:
            out = fn()
            if out:
                return out
        except Exception:  # noqa: BLE001 - not up yet
            pass
        time.sleep(step)
    return None


def prepare(home):
    dist = os.path.join(home, "dist")
    subprocess.check_call([sys.executable, os.path.join(ROOT, "tools", "build_kodi.py"), dist],
                          stdout=subprocess.DEVNULL)
    zips = sorted(f for f in os.listdir(dist) if f.startswith("service.camalert-") and f.endswith(".zip"))
    addons = os.path.join(home, ".kodi", "addons")
    os.makedirs(addons)
    with zipfile.ZipFile(os.path.join(dist, zips[-1])) as z:
        z.extractall(addons)
    userdata = os.path.join(home, ".kodi", "userdata")
    os.makedirs(userdata)
    with open(os.path.join(userdata, "guisettings.xml"), "w") as f:
        f.write(GUISETTINGS)
    return zips[-1]


def addon_errors(log_path):
    """Python exceptions of the add-on in kodi.log (lines of a traceback that mention service.camalert)."""
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return ["kodi.log missing"]
    bad = []
    for block in text.split("EXCEPTION Thrown")[1:] + text.split("Traceback (most recent call last)")[1:]:
        head = block[:3000]
        if "service.camalert" in head:
            bad.append(head.strip().splitlines()[-1][:200] if head.strip() else "exception")
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kodi", default="kodi")
    ap.add_argument("--keep", action="store_true", help="keep the temporary Kodi profile (for debugging)")
    a = ap.parse_args(argv)
    for tool in (a.kodi, "xvfb-run"):
        if not shutil.which(tool):
            print("FAIL %s not installed" % tool)
            return 2
    home = tempfile.mkdtemp(prefix="camalert-kodi-")
    c = Checks()
    procs = []
    try:
        print("add-on:", prepare(home))
        env = dict(os.environ, HOME=home)
        procs.append(subprocess.Popen([sys.executable, GO2RTC, "--port", str(FAKE_PORT)],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        kodi = subprocess.Popen(["xvfb-run", "-a", "-s", "-screen 0 1280x720x24", a.kodi, "--standalone"], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setsid)
        procs.append(kodi)
        version = wait(lambda: rpc("Application.GetProperties", {"properties": ["version"]})["version"], 120, 2)
        if not c.check(bool(version), "Kodi answers JSON-RPC (%s)" % (
                "%s.%s" % (version["major"], version["minor"]) if version else "no answer within 120 s")):
            return 1
        rpc("Addons.SetAddonEnabled", {"addonid": "service.camalert", "enabled": True})
        st = wait(lambda: api("status"), 60)
        if not c.check(bool(st), "CamAlert API answers (version %s)" % (st or {}).get("version")):
            return 1
        c.check(st.get("platform") == "kodi" and st.get("screen") == "none", "status: platform kodi, nothing shown")
        out = api("setup", server="http://127.0.0.1:%d" % FAKE_PORT)
        c.check(out.get("result") is True, "/camalert/setup to the fake go2rtc")
        names = wait(lambda: [x["name"] for x in api("cameras").get("cameras") or []], 20)
        c.check(bool(names) and "front_door" in names, "camera list from the fake go2rtc (%s)" % ",".join(names or []))
        before = rpc("GUI.GetProperties", {"properties": ["currentwindow"]})["currentwindow"]["id"]
        out = api("show", cam="front_door", mode="photo", sec=30, priority="normal")
        c.check(out.get("result") is True, "show front_door (photo window, test=1)")
        st = wait(lambda: (lambda s: s if s.get("screen") == "photo" else None)(api("status")), 15, 0.5)
        c.check(bool(st) and st.get("window") == "front_door", "status: photo window with front_door")
        now = rpc("GUI.GetProperties", {"properties": ["currentwindow"]})["currentwindow"]["id"]
        c.check(now != before or bool(st), "Kodi shows the CamAlert window (window %s -> %s)" % (before, now))
        api("hide")
        c.check(bool(wait(lambda: api("status").get("screen") == "none", 10, 0.5)), "hide: nothing shown")
        out = api("mosaic", cam="front_door,garden,driveway,back_door", sec=30)
        c.check(out.get("result") is True, "mosaic of the four demo cameras")
        c.check(bool(wait(lambda: api("status").get("screen") == "mosaic", 15, 0.5)), "status: mosaic")
        api("hide")
        c.check(bool(wait(lambda: api("status").get("screen") == "none", 10, 0.5)), "hide: mosaic closed")
        try:
            rpc("Application.Quit")
        except Exception:  # noqa: BLE001 - Kodi may close the connection while quitting
            pass
        try:
            kodi.wait(30)
        except subprocess.TimeoutExpired:
            pass
        errors = addon_errors(os.path.join(home, ".kodi", "temp", "kodi.log"))
        c.check(not errors, "no add-on exception in kodi.log%s" % (": " + "; ".join(errors[:3]) if errors else ""))
        return 1 if c.failed else 0
    finally:
        for p in procs:
            if p.poll() is None:
                try:
                    os.killpg(os.getpgid(p.pid), signal.SIGTERM) if p is procs[-1] else p.terminate()
                except (OSError, ProcessLookupError):
                    p.terminate()
                try:
                    p.wait(10)
                except subprocess.TimeoutExpired:
                    p.kill()
        if a.keep:
            print("Kodi profile kept in", home)
        else:
            shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
