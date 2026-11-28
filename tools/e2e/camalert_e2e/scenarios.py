"""Scenarios. v1.0 (#35): show (photo), strip, mosaic, tour, dnd, ptz (fake camera only), ha (optional).
v1.1/1.3 (#77): alarm_wake (Enigma2, never on a quiet device; standby is restored), chime_muted (a test request is
tagged "test" and the chime is off), mqtt (the broker of the profile file), settings (window position, #84),
kodi_resume (a paused film plays on after CamAlert; needs `resume_file` in the profile).

Each scenario gets a Context and returns a Result; the runner hides CamAlert after every scenario. State is checked
first (/camalert/status, Kodi windows), screenshots only with fake cameras (OSD only, solid colours).
"""
import time

from . import geometry
from .errors import Skip
from .fakes import PTZ_CAMERA

CORE = ("show", "strip", "mosaic", "tour", "dnd", "ptz", "ha")
EXTRA = ("alarm_wake", "chime_muted", "mqtt", "settings", "kodi_resume")
ALL = CORE + EXTRA


class Result(object):
    def __init__(self, name):
        self.name, self.status, self.checks, self.seconds, self.screenshots = name, "passed", [], 0.0, []

    def check(self, ok, text):
        self.checks.append({"ok": bool(ok), "detail": text})
        if not ok:
            self.status = "failed"
        return ok

    def as_dict(self):
        return {"name": self.name, "status": self.status, "checks": self.checks, "seconds": round(self.seconds, 1),
                "screenshots": self.screenshots}


class Context(object):
    def __init__(self, device, state, cams, colours, settings, shot=None, ha=None, sleep=time.sleep,
                 clock=time.time, mqtt=None, save=None):
        self.device, self.camalert, self.state = device, device.camalert, state
        self.cams, self.colours, self.settings = cams, colours, settings
        self.shot, self.ha, self.sleep, self.clock = shot, ha, sleep, clock
        self.mqtt, self.save = mqtt, save or (lambda: None)

    def change_setting(self, key, value):
        """Enigma2: a player setting for this scenario; the original goes into the state first, so the runner's
        restore (and `--restore last` after a crash) puts it back."""
        if self.device.kind != "enigma2":
            raise Skip("settings are only changed on Enigma2 receivers")
        ch = self.state.setdefault("changes", {}).setdefault("settings", {})
        if key not in ch:
            ch[key] = (self.state.get("before") or {}).get("settings", {}).get(key)
            self.save()
        self.device.set_config(key, value)

    @property
    def fake(self):
        return self.colours is not None

    @property
    def shots(self):
        """Fake cameras and a device that can take screenshots (Kodi cannot, #77)."""
        return self.fake and self.shot is not None and getattr(self.device, "screenshots", True)

    def wait_window(self, want, timeout=10.0):
        """Polls /camalert/status until window == want; returns the last value."""
        end = self.clock() + timeout
        while True:
            got = self.camalert.status().get("window")
            if got == want or self.clock() >= end:
                return got
            self.sleep(1.0)

    def wait_screen(self, want, timeout=10.0):
        """Polls /camalert/status until screen == want (#63); returns the last value, None for a player that does
        not report "screen" yet (older than 1.0)."""
        end = self.clock() + timeout
        while True:
            got = self.camalert.status().get("screen")
            if got is None or got == want or self.clock() >= end:
                return got
            self.sleep(1.0)

    def check_screen(self, r, want, what, timeout=10.0):
        """A check that status "screen" becomes `want`; nothing for a player without "screen"."""
        got = self.wait_screen(want, timeout)
        if got is not None:
            r.check(got == want, "status screen = %s (%s)" % (got, what))
        return got

    def screenshot(self, label):
        if not self.shots:
            return None
        return geometry.load(self.shot(label))


def _answer(r, code, out, want_result=True):
    ok = code == 200 and isinstance(out, dict) and out.get("result") is want_result
    r.check(ok, "API answer %s %s" % (code, {k: out.get(k) for k in ("result", "action", "dnd")}
                                       if isinstance(out, dict) else out))
    return ok


def show(ctx, r):
    cam = ctx.cams[0]
    if not _answer(r, *ctx.camalert.action("show", cam=cam, mode="photo", sec=20, priority="normal", label="E2E")):
        return
    r.check(ctx.wait_window(cam) == cam, "status window = first camera")
    ctx.check_screen(r, "photo", "photo window")
    if ctx.shots:
        # the window appears before its picture is loaded (seen on a real receiver): try a few screenshots
        for attempt in range(5):
            ok, detail = geometry.check_photo(ctx.screenshot("show"), cam, ctx.colours[cam], ctx.settings)
            if ok:
                break
            ctx.sleep(1.5)
        r.check(ok, detail)
    ctx.camalert.hide()
    r.check(ctx.wait_window(None) is None, "hidden again")
    ctx.check_screen(r, "none", "hide closed the photo window")


def strip(ctx, r):
    if len(ctx.cams) < 2:
        raise Skip("needs 2 cameras")
    cams = ctx.cams[:2]
    if not _answer(r, *ctx.camalert.action("show", cam=",".join(cams), mode="strip", sec=20, priority="normal")):
        return
    r.check(ctx.wait_window(",".join(cams)) == ",".join(cams), "status window = both cameras")
    ctx.check_screen(r, "strip", "multi-camera window")
    if ctx.shots:
        # like the photo window: the tiles appear before their pictures are loaded (seen on a real receiver)
        for attempt in range(5):
            img = ctx.screenshot("strip")
            ok, detail = geometry.check_tiles(img, cams, ctx.colours,
                                              geometry.strip_rects(2, ctx.settings, img.width, img.height))
            if ok:
                break
            ctx.sleep(1.5)
        r.check(ok, detail)
    ctx.camalert.hide()
    r.check(ctx.wait_window(None) is None, "hidden again")
    ctx.check_screen(r, "none", "hide closed the multi-camera window")


def _kodi_window(ctx):
    return ctx.device.window()["id"] if ctx.device.kind == "kodi" else None


def mosaic(ctx, r):
    cams = ctx.cams[:4]
    before = _kodi_window(ctx)
    if not _answer(r, *ctx.camalert.action("mosaic", cam=",".join(cams), sec=30)):
        return
    ctx.sleep(3)
    ctx.check_screen(r, "mosaic", "mosaic open")
    if before is not None:
        r.check(_kodi_window(ctx) != before, "Kodi shows another window")
    img = ctx.screenshot("mosaic")
    if img is not None:
        r.check(*geometry.check_tiles(img, cams, ctx.colours, geometry.mosaic_rects(len(cams), img.width, img.height)))
    ctx.camalert.hide()
    ctx.sleep(2)
    ctx.check_screen(r, "none", "hide closed the mosaic")
    if before is not None:
        r.check(_kodi_window(ctx) == before, "Kodi window back")


def tour(ctx, r):
    if len(ctx.cams) < 2:
        raise Skip("needs 2 cameras")
    cams = ctx.cams[:2]
    if not _answer(r, *ctx.camalert.action("tour", cam=",".join(cams), interval=3)):
        return
    ctx.sleep(1.5)
    ctx.check_screen(r, "tour", "tour open")
    first = ctx.screenshot("tour-1")
    ctx.sleep(3.5)
    second = ctx.screenshot("tour-2")
    if first is not None and second is not None:
        a = geometry.colours_on_screen(first, ctx.colours)
        b = geometry.colours_on_screen(second, ctx.colours)
        r.check(len(a) == 1 and len(b) == 1 and a != b and set(a + b) <= set(cams),
                "tour changed camera: %s -> %s" % (",".join(a) or "-", ",".join(b) or "-"))
    ctx.camalert.hide()
    ctx.sleep(1)
    ctx.check_screen(r, "none", "hide closed the tour")


def dnd(ctx, r):
    code, out = ctx.camalert.set_dnd(True)
    r.check(code == 200 and out.get("dnd") is True, "do not disturb on")
    try:
        code, out = ctx.camalert.action("show", cam=ctx.cams[0], mode="photo", sec=10, priority="normal")
        r.check(code == 200 and out.get("result") is False, "normal request ignored (%s)" % out.get("action"))
        ctx.sleep(1.5)
        st = ctx.camalert.status()
        r.check(st.get("window") is None and st.get("screen") in (None, "none"), "nothing on screen")
    finally:
        code, out = ctx.camalert.set_dnd(False)
        r.check(code == 200 and out.get("dnd") is False, "do not disturb off")


def ptz(ctx, r):
    if not ctx.fake or ctx.device.kind != "enigma2":
        raise Skip("PTZ only against the fake camera (it would move a real camera)")
    if not _answer(r, *ctx.camalert.action("ptz", cam=PTZ_CAMERA, move="left")):
        return
    calls = []
    for _ in range(10):
        ctx.sleep(0.5)
        calls = ctx.device.ptz_calls()
        if "ptzMoveLeft" in calls:
            break
    r.check("ptzMoveLeft" in calls, "fake camera got ptzMoveLeft (%s)" % ",".join(calls[:6]))


def ha(ctx, r):
    device_id = ctx.device.p.get("ha_device_id")
    if ctx.ha is None or not device_id:
        raise Skip("no Home Assistant token or ha_device_id")
    cam = ctx.cams[0]
    ctx.ha.service("camalert", "show", {"device_id": device_id, "camera": cam, "priority": "normal", "seconds": 15})
    r.check(ctx.wait_window(cam, 15) == cam, "Home Assistant camalert.show reached the player")
    ctx.ha.service("camalert", "hide", {"device_id": device_id})
    r.check(ctx.wait_window(None, 15) is None, "Home Assistant camalert.hide reached the player")


def _wait(ctx, test, timeout):
    end = ctx.clock() + timeout
    while True:
        if test():
            return True
        if ctx.clock() >= end:
            return False
        ctx.sleep(1.0)


def alarm_wake(ctx, r):
    """#77: an alarm request wakes a receiver from standby (setting alarm_wake on); standby comes back after."""
    dev = ctx.device
    if dev.kind != "enigma2":
        raise Skip("alarm wake-up is an Enigma2 feature")
    if dev.p.get("quiet"):
        raise Skip("never woken on purpose: quiet device")
    was_on = not dev.statusinfo()["standby"]
    ctx.change_setting("alarm_wake", True)
    try:
        dev._standby()
        r.check(_wait(ctx, lambda: dev.statusinfo()["standby"], 15), "receiver went to standby")
        code, out = ctx.camalert.action("show", cam=ctx.cams[0], mode="photo", sec=15, priority="alarm")
        r.check(code == 200 and isinstance(out, dict) and out.get("action") in ("wake", "show"),
                "alarm accepted (%s)" % (out.get("action") if isinstance(out, dict) else code))
        r.check(_wait(ctx, lambda: not dev.statusinfo()["standby"], 20), "alarm woke the receiver")
        r.check(ctx.wait_window(ctx.cams[0], 15) == ctx.cams[0], "camera shown after waking")
        ctx.camalert.hide()
        r.check(ctx.wait_window(None) is None, "hidden again")
    finally:
        st = dev.statusinfo()["standby"]
        if was_on and st:
            dev.api("/api/powerstate?newstate=4")  # back on, as before the scenario
        elif not was_on and not st:
            dev._standby()


def chime_muted(ctx, r):
    """#77: a test request never rings: the event is tagged "test" and the chime setting is off (or high only)."""
    cam = ctx.cams[0]
    if not _answer(r, *ctx.camalert.action("show", cam=cam, mode="photo", sec=10, priority="normal")):
        return
    ctx.wait_window(cam, 10)
    events = ctx.camalert.get("events").get("events") or []
    r.check(bool(events) and events[0].get("source") == "test",
            "newest event tagged test (%s)" % (events[0].get("source") if events else "no events"))
    chime = None
    if ctx.device.kind == "enigma2":
        chime = (ctx.device.saved_settings() or {}).get("chime", "off")
    elif hasattr(ctx.device, "chime"):
        chime = ctx.device.chime()
    if chime is not None:
        r.check(chime in ("off", "high", '"off"', '"high"'), "chime setting %s rings no normal request" % chime)
    ctx.camalert.hide()


def mqtt(ctx, r):
    """#77: a show command over MQTT (as Home Assistant's MQTT buttons send it) reaches the player."""
    if ctx.mqtt is None:
        raise Skip("no mqtt broker in the profile file")
    st = ctx.camalert.status()
    if not st.get("mqtt"):
        raise Skip("MQTT is off on this player")
    cam = ctx.cams[0]
    ctx.mqtt.show(st["id"], cam=cam, sec=15, mode="photo", priority="normal", label="E2E")
    r.check(ctx.wait_window(cam, 15) == cam, "MQTT show reached the player")
    ctx.camalert.hide()
    r.check(ctx.wait_window(None) is None, "hidden again")


def settings(ctx, r):
    """#84: window position and size over /camalert/settings; the next window uses them; put back after."""
    if "settings" not in (ctx.camalert.status().get("capabilities") or []):
        raise Skip("player without /camalert/settings (older than 1.3)")
    before = ctx.camalert.get("settings")
    try:
        code, out = ctx.camalert.action("settings", position="bottom_left", size="small")
        r.check(code == 200 and out.get("position") == "bottom_left" and out.get("size") == "small",
                "position and size set (%s)" % code)
        code, out = ctx.camalert.action("settings", position="nowhere")
        r.check(code == 400, "invalid position refused (%s)" % code)
        st = ctx.camalert.status()
        r.check(st.get("position") == "bottom_left", "status reports the new position")
        cam = ctx.cams[0]
        if _answer(r, *ctx.camalert.action("show", cam=cam, mode="photo", sec=10, priority="normal")):
            r.check(ctx.wait_window(cam) == cam, "window shown with the new position")
            if ctx.shots:
                s = dict(ctx.settings, position="bottom_left", size="small")
                for attempt in range(5):
                    ok, detail = geometry.check_photo(ctx.screenshot("settings"), cam, ctx.colours[cam], s)
                    if ok:
                        break
                    ctx.sleep(1.5)
                r.check(ok, detail)
            ctx.camalert.hide()
    finally:
        code, out = ctx.camalert.action("settings", position=before.get("position"), size=before.get("size"))
        r.check(code == 200 and out.get("position") == before.get("position"), "position and size put back")


def kodi_resume(ctx, r):
    """#77: a film that plays keeps playing after a CamAlert window (Kodi pauses for live view only)."""
    dev = ctx.device
    media = dev.p.get("resume_file")
    if dev.kind != "kodi" or not media:
        raise Skip("Kodi with resume_file in the profile only")
    dev.rpc.call("Player.Open", {"item": {"file": media}})
    try:
        r.check(_wait(ctx, lambda: bool(dev.rpc.call("Player.GetActivePlayers")), 15), "test film plays")
        ctx.sleep(3)
        cam = ctx.cams[0]
        if _answer(r, *ctx.camalert.action("show", cam=cam, mode="photo", sec=8, priority="normal")):
            ctx.wait_window(cam, 10)
            ctx.camalert.hide()
            ctx.wait_window(None, 10)
        players = dev.rpc.call("Player.GetActivePlayers") or []
        speed = None
        if players:
            speed = dev.rpc.call("Player.GetProperties", {"playerid": players[0]["playerid"],
                                                          "properties": ["speed"]}).get("speed")
        r.check(speed == 1, "film plays on after CamAlert (speed %s)" % speed)
    finally:
        for p in dev.rpc.call("Player.GetActivePlayers") or []:
            dev.rpc.call("Player.Stop", {"playerid": p["playerid"]})


SCENARIOS = {"show": show, "strip": strip, "mosaic": mosaic, "tour": tour, "dnd": dnd, "ptz": ptz, "ha": ha,
             "alarm_wake": alarm_wake, "chime_muted": chime_muted, "mqtt": mqtt, "settings": settings,
             "kodi_resume": kodi_resume}


def run(name, ctx):
    r = Result(name)
    start = ctx.clock()
    try:
        SCENARIOS[name](ctx, r)
    except Skip as e:
        r.status = "skipped"
        r.checks.append({"ok": None, "detail": str(e)})
    except Exception as e:  # noqa: BLE001 - a broken scenario is a failure, the run goes on
        r.status = "failed"
        r.checks.append({"ok": False, "detail": "error: %s: %s" % (e.__class__.__name__, e)})
    finally:
        try:
            ctx.camalert.hide()
            clear = getattr(ctx.device, "clear_screens", None)
            if clear is not None:
                ctx.sleep(1)
                reports = ctx.camalert.status().get("screen") is not None
                presses = clear()
                if presses and reports:
                    # the player itself says hide worked (checked in the scenario): the leftover is not CamAlert's
                    r.checks.append({"ok": None, "detail": "cleanup: %d EXIT press(es) for something else on "
                                                            "the OSD" % presses})
                elif presses:  # a player without "screen" (older than 1.0): hide did not close it (#63)
                    r.check(False, "hide left %d screen(s) open, closed with EXIT (#63)" % presses)
        except Exception as e:  # noqa: BLE001
            r.check(False, "cleanup: %s: %s" % (e.__class__.__name__, e))
    r.seconds = ctx.clock() - start
    return r
