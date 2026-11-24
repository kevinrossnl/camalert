"""camalert_core UniFi Protect (#9): helpers, the read-only client (fake console) and the trigger source."""
import io
import json
import unittest
import urllib.error

import _paths

_paths.core()
from camalert_core.devices import client, config as dev_config, unifi  # noqa: E402
from camalert_core.triggers import enabled_sources  # noqa: E402
from camalert_core.triggers import Trigger  # noqa: E402
from camalert_core.triggers import unifi as unifi_trigger  # noqa: E402
from camalert_core.triggers.unifi import PollStatus, UnifiSource, labels  # noqa: E402

CAM_A, CAM_B = "65a1b2c3d4e5f60718293a4b", "65a1b2c3d4e5f60718293a4c"
BOOT = {"cameras": [{"id": CAM_A, "displayName": "Front Door", "isAdopted": True},
                    {"id": CAM_B, "name": "Über Garten"},
                    {"id": "65a1b2c3d4e5f60718293a4d", "displayName": "New", "isAdopted": False},
                    {"displayName": "no id"}, "junk", {"id": "x", "displayName": "!!"}]}


def ev(i, kind, cam=CAM_A, smart=None):
    return {"id": i, "type": kind, "camera": cam, "smartDetectTypes": smart or [], "start": 1}


class TestHelpers(unittest.TestCase):
    def test_slug_and_cameras(self):
        self.assertEqual(unifi.slug(" Front Door "), "front_door")
        self.assertEqual(unifi.slug(u"Große Wiese"), "grosse_wiese")
        self.assertEqual(unifi.slug(None), "")
        self.assertEqual(unifi.protect_cameras(BOOT), {CAM_A: "front_door", CAM_B: "ueber_garten"})
        self.assertEqual(unifi.protect_cameras(None), {})

    def test_maps_and_kinds(self):
        self.assertEqual(unifi.camera_map("Front Door=door_cam| bad |=x|garden=  "), {"front_door": "door_cam"})
        self.assertEqual(unifi.wanted_kinds("motion, Ring, ghost"), ["ring", "motion"])
        self.assertEqual(unifi.wanted_kinds(""), ["ring", "person"])
        self.assertEqual(unifi.wanted_kinds("ghost"), ["ring", "person"])
        self.assertEqual(unifi.event_kinds(ev("1", "ring")), ["ring"])
        self.assertEqual(unifi.event_kinds(ev("1", "motion")), ["motion"])
        self.assertEqual(unifi.event_kinds(ev("1", "smartDetectZone", smart=["vehicle", "person"])),
                         ["person", "vehicle"])
        self.assertEqual(unifi.event_kinds(ev("1", "smartAudioDetect", smart=["alrmSpeak"])), [])
        self.assertEqual(unifi.event_kinds(None), [])

    def test_paths_and_match(self):
        p = unifi.events_path(1000, 2000.5, 10)
        self.assertTrue(p.startswith("/proxy/protect/api/events?start=1000&end=2000&limit=10&orderDirection=ASC"))
        self.assertIn("types=ring&types=motion", p)
        self.assertEqual(unifi.snapshot_path(CAM_A, 640), "/proxy/protect/api/cameras/%s/snapshot?w=640&force=true"
                         % CAM_A)
        self.assertRaises(ValueError, unifi.snapshot_path, "../x")
        cams = unifi.protect_cameras(BOOT)
        self.assertEqual(unifi.match(ev("1", "ring"), cams, ["ring"]), ("front_door", "ring"))
        self.assertEqual(unifi.match(ev("1", "ring"), cams, ["ring"], {"front_door": "door"}), ("door", "ring"))
        self.assertIsNone(unifi.match(ev("1", "motion"), cams, ["ring"]))
        self.assertIsNone(unifi.match(ev("1", "ring", cam="other"), cams, ["ring"]))

    def test_kind_rules(self):
        self.assertEqual(unifi.kind_rules("ring=alarm/live| Motion = normal / log / garden |person=/notify"),
                         {"ring": ("alarm", "live", None), "motion": ("normal", "log", "garden"),
                          "person": (None, "notify", None)})
        # unknown kinds, broken parts, invalid values and empty rules are skipped
        self.assertEqual(unifi.kind_rules("ghost=alarm|ring|vehicle=loud/huge|animal=//|=x"), {})
        self.assertEqual(unifi.kind_rules(None), {})

    def test_devices_file(self):
        d = dev_config.parse_devices("protect|unifi|192.168.1.1|viewer|p|w\nnvr|unifi|192.168.1.2:7443|v|x")
        self.assertEqual(d["protect"], {"type": "unifi", "host": "192.168.1.1", "port": 443, "user": "viewer",
                                        "password": "p|w"})
        self.assertEqual(d["nvr"]["port"], 7443)


class Resp(object):
    def __init__(self, body, headers=None):
        self.body, self.headers = body, headers or {}

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeConsole(object):
    """Answers like a UniFi OS console; records every request (method, path, csrf)."""

    def __init__(self, expire_once=False, fail=None):
        self.calls, self.expire_once, self.fail = [], expire_once, fail
        self.events = []

    def open(self, req, timeout=None):
        path = req.full_url.split(":443", 1)[1]
        self.calls.append((req.get_method(), path.split("?")[0], req.headers.get("X-csrf-token")))
        if self.fail:
            raise self.fail
        if path == unifi.LOGIN_PATH:
            body = json.loads(req.data.decode())
            if body["password"] != "secret":
                raise urllib.error.HTTPError(req.full_url, 401, "no", {}, io.BytesIO(b""))
            return Resp(b"{}", {"X-CSRF-Token": "tok"})
        if self.expire_once:
            self.expire_once = False
            raise urllib.error.HTTPError(req.full_url, 401, "expired", {}, io.BytesIO(b""))
        if path == unifi.BOOTSTRAP_PATH:
            return Resp(json.dumps(BOOT).encode())
        if path.startswith("/proxy/protect/api/events"):
            return Resp(json.dumps(self.events).encode())
        if "/snapshot" in path:
            return Resp(b"\xff\xd8jpeg")
        return Resp(b"not json")


DEV = {"type": "unifi", "host": "192.168.1.1", "port": 443, "user": "viewer", "password": "secret"}


class TestClient(unittest.TestCase):
    def test_state_read_only_and_cached_cameras(self):
        fake = FakeConsole()
        fake.events = [ev("e1", "ring")]
        p = client.Protect(DEV, opener=fake)
        st = p.state(now=1000)
        self.assertEqual(st, {"now": 1000000, "cams": {CAM_A: "front_door", CAM_B: "ueber_garten"},
                              "events": [ev("e1", "ring")]})
        p.state(now=1100)  # cameras cached
        p.state(now=1000 + client.BOOTSTRAP_MAX_AGE + 1)  # read again
        methods = [c[0] for c in fake.calls]
        self.assertEqual(methods.count("POST"), 1)  # only the login posts
        self.assertEqual([c[1] for c in fake.calls].count(unifi.BOOTSTRAP_PATH), 2)
        self.assertTrue(all(c[2] == "tok" for c in fake.calls[1:]))
        self.assertEqual(p.snapshot(CAM_A), b"\xff\xd8jpeg")

    def test_relogin_after_401_and_errors(self):
        fake = FakeConsole(expire_once=True)
        p = client.Protect(DEV, opener=fake)
        p.login()
        self.assertEqual(p.cameras(now=1), {CAM_A: "front_door", CAM_B: "ueber_garten"})
        self.assertEqual([c[0] for c in fake.calls].count("POST"), 2)
        with self.assertRaises(client.DeviceError) as e:
            client.Protect(dict(DEV, password="wrong"), opener=FakeConsole()).cameras()
        self.assertEqual(str(e.exception), "UniFi Protect login: HTTP 401")
        with self.assertRaises(client.DeviceError) as e:
            client.Protect(DEV, opener=FakeConsole(fail=OSError("secret in url"))).cameras()
        self.assertNotIn("secret", str(e.exception))
        p = client.Protect(DEV, opener=FakeConsole())
        self.assertRaises(client.DeviceError, p.get, "/other")
        self.assertEqual(client.Protect(DEV).base, "https://192.168.1.1:443")

    def test_protect_state_and_no_ptz(self):
        fake = FakeConsole(fail=OSError("down"))
        dev = dict(DEV, host="192.168.1.99")
        key = (dev["host"], dev["port"], dev["user"], dev["password"])
        client._protect[key] = client.Protect(dev, opener=fake)
        self.assertRaises(client.DeviceError, client.protect_state, dev)
        self.assertNotIn(key, client._protect)  # new session next time
        ok = FakeConsole()
        client._protect[key] = client.Protect(dev, opener=ok)
        self.assertEqual(client.protect_state(dev)["events"], [])
        self.assertRaises(client.DeviceError, client.ptz, DEV, "up")
        client._protect.pop(key, None)


class TestSource(unittest.TestCase):
    CAMS = {CAM_A: "front_door", CAM_B: "garden"}

    def state(self, *events):
        return {"now": 1, "cams": self.CAMS, "events": list(events)}

    def test_enabled_and_devices(self):
        self.assertEqual([s.name for s in enabled_sources({"unifi_enabled": True}, "poll")], ["unifi"])
        src = UnifiSource({"unifi_enabled": True})
        self.assertEqual(list(src.devices({"a": {"type": "foscam"}, "p": DEV})), ["p"])

    def test_first_poll_and_repeats_show_nothing(self):
        src = UnifiSource({"unifi_enabled": True})
        self.assertIsNone(src.check("p", None, self.state(ev("1", "ring"))))
        self.assertIsNone(src.check("p", self.state(ev("1", "ring")), self.state(ev("1", "ring"))))
        self.assertIsNone(src.check("p", self.state(), None))

    def test_ring_wins_and_is_high(self):
        src = UnifiSource({"unifi_enabled": True, "unifi_kinds": "ring,person,motion", "unifi_label": "Visitor",
                           "unifi_cameras": "front_door=door_cam", "unifi_mode": "live", "unifi_seconds": 20})
        t = src.check("p", self.state(), self.state(ev("1", "motion", CAM_B), ev("2", "ring"),
                                                     ev("3", "smartDetectZone", CAM_B, ["person"])))
        self.assertEqual(t.show_args(), ("door_cam", 20, "live", "high", "unifi", "Visitor", None))
        t = src.check("p", self.state(), self.state(ev("3", "smartDetectZone", CAM_B, ["person"])))
        self.assertEqual(t.show_args(), ("garden", 20, "live", "normal", "unifi", "Visitor", None))
        alarm = UnifiSource({"unifi_priority": "alarm"})
        self.assertEqual(alarm.check("p", self.state(), self.state(ev("4", "ring"))).priority, "alarm")

    def test_unwanted_kinds_are_ignored(self):
        src = UnifiSource({"unifi_enabled": True})  # default ring,person
        self.assertIsNone(src.check("p", self.state(), self.state(ev("1", "motion"), ev("2", "smartAudioDetect"))))

    def test_rules_per_kind_and_labels(self):
        src = UnifiSource({"unifi_kinds": "ring,person,motion", "unifi_mode": "photo", "unifi_priority": "high",
                           "unifi_rules": "motion=normal/log|person=alarm//porch|ring=normal",
                           "unifi_labels": labels(lambda t: t.upper()), "unifi_label": "unused"})
        t = src.check("p", self.state(), self.state(ev("1", "motion", CAM_B)))
        self.assertEqual(t.show_args(), ("garden", None, "log", "normal", "unifi", "MOTION", None))
        t = src.check("p", self.state(), self.state(ev("2", "smartDetectLine", CAM_B, ["person"])))
        self.assertEqual(t.show_args(), ("porch", None, "photo", "alarm", "unifi", "PERSON", None))
        t = src.check("p", self.state(), self.state(ev("3", "ring")))
        self.assertEqual((t.priority, t.label), ("high", "DOORBELL"))  # a ring stays at least high
        self.assertEqual(sorted(unifi_trigger.KIND_LABELS), sorted(unifi.KINDS))

    def test_rules_per_camera(self):
        src = UnifiSource({"unifi_kinds": "ring,person,motion", "unifi_mode": "log", "unifi_priority": "normal",
                           "unifi_seconds": 20, "unifi_rules": "person=alarm/live/porch",
                           "unifi_camera_rules": "Garden=high/photo/45|front_door=normal/notify/"})
        # camera rule wins over the general settings (all three parts)
        t = src.check("p", self.state(), self.state(ev("1", "motion", CAM_B)))
        self.assertEqual(t.show_args(), ("garden", 45, "photo", "high", "unifi", None, None))
        # camera rule wins over the per-type rule; the per-type camera still redirects; seconds fall back
        t = src.check("p", self.state(), self.state(ev("2", "smartDetectZone", CAM_B, ["person"])))
        self.assertEqual(t.show_args(), ("porch", 45, "photo", "high", "unifi", None, None))
        # a ring stays at least high, also with a camera rule 'normal'
        t = src.check("p", self.state(), self.state(ev("3", "ring")))
        self.assertEqual(t.show_args(), ("front_door", 20, "notify", "high", "unifi", None, None))
        # cameras without a rule use the per-type rule and the general settings
        plain = UnifiSource({"unifi_kinds": "motion", "unifi_mode": "log", "unifi_camera_rules": "other=alarm"})
        t = plain.check("p", self.state(), self.state(ev("4", "motion", CAM_B)))
        self.assertEqual((t.camera, t.mode, t.priority), ("garden", "log", "normal"))
        # the rule matches the camera name after unifi_cameras
        mapped = UnifiSource({"unifi_kinds": "motion", "unifi_cameras": "garden=back_yard",
                              "unifi_camera_rules": "back_yard=alarm/live"})
        t = mapped.check("p", self.state(), self.state(ev("5", "motion", CAM_B)))
        self.assertEqual((t.camera, t.mode, t.priority), ("back_yard", "live", "alarm"))

    def test_camera_rules_parser(self):
        self.assertEqual(unifi.camera_rules(None), {})
        self.assertEqual(unifi.camera_rules("Front Door=HIGH/Photo/30| driveway = normal/log |x"),
                         {"front_door": ("high", "photo", 30), "driveway": ("normal", "log", None)})
        # invalid parts become None, a rule without any valid part and broken parts are skipped
        self.assertEqual(unifi.camera_rules("a=loud/blink/3|b=//301|c=//abc|d=//5|=high|e"),
                         {"d": (None, None, 5)})
        self.assertEqual(unifi.camera_rules("a=/log/300"), {"a": (None, "log", 300)})

    def test_poll_uses_the_client(self):
        orig = client.protect_state
        client.protect_state = lambda dev: {"now": 5, "cams": {}, "events": []}
        try:
            self.assertEqual(UnifiSource.poll(DEV)["now"], 5)
        finally:
            client.protect_state = orig


class TestPollStatus(unittest.TestCase):
    def lines(self, st):
        return st.lines(lambda t: t, lambda ts: "t%d" % ts)

    def test_lines(self):
        st = PollStatus()
        self.assertEqual(self.lines(st), [(False, "UniFi Protect: no console of type unifi in the devices file")])
        st.consoles = 1
        self.assertEqual(self.lines(st), [(None, "UniFi Protect: not checked yet")])
        self.assertTrue(st.failed(client.DeviceError("UniFi Protect login: HTTP 401 password=hunter2"), 5))
        self.assertFalse(st.failed(client.DeviceError("UniFi Protect login: HTTP 401 password=hunter2"), 6))
        out = self.lines(st)
        self.assertEqual(out[0][0], False)
        self.assertNotIn("hunter2", out[0][1])
        self.assertEqual(out[1], (None, "UniFi Protect: no event since the start"))
        st.ok(10)
        st.event(Trigger("garden", "normal", "unifi", "Motion", mode="log"), 11)
        self.assertEqual(self.lines(st), [(True, "UniFi Protect: last check t10"),
                                          (True, "UniFi Protect: last event t11, garden (Motion) [Log only]")])
        st.event(Trigger("door", "high", "unifi"))
        self.assertEqual(self.lines(st)[1][1][-4:], "door")
        st.reset()
        self.assertIsNone(st.last_poll)
        self.assertIsInstance(unifi_trigger.STATUS, PollStatus)


if __name__ == "__main__":
    unittest.main()
