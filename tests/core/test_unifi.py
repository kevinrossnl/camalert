"""camalert_core UniFi Protect (#9): helpers, the read-only client (fake console) and the trigger source."""
import io
import json
import unittest
import urllib.error

import _paths

_paths.core()
from camalert_core.devices import client, config as dev_config, unifi  # noqa: E402
from camalert_core.triggers import enabled_sources  # noqa: E402
from camalert_core.triggers.unifi import UnifiSource  # noqa: E402

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

    def test_poll_uses_the_client(self):
        orig = client.protect_state
        client.protect_state = lambda dev: {"now": 5, "cams": {}, "events": []}
        try:
            self.assertEqual(UnifiSource.poll(DEV)["now"], 5)
        finally:
            client.protect_state = orig


if __name__ == "__main__":
    unittest.main()
