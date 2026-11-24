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

    def __init__(self, expire_once=False, fail=None, login_status=None, retry_after=None, data_status=None):
        self.calls, self.expire_once, self.fail = [], expire_once, fail
        self.events = []
        # login_status: HTTP code the login answers (e.g. 403, 429); data_status: code of every data call
        self.login_status, self.retry_after, self.data_status = login_status, retry_after, data_status

    def logins(self):
        return [c[1] for c in self.calls].count(unifi.LOGIN_PATH)

    def refuse(self, req, code):
        headers = {"Retry-After": self.retry_after} if self.retry_after is not None else {}
        raise urllib.error.HTTPError(req.full_url, code, "no", headers, io.BytesIO(b""))

    def open(self, req, timeout=None):
        path = req.full_url.split(":443", 1)[1]
        self.calls.append((req.get_method(), path.split("?")[0], req.headers.get("X-csrf-token")))
        if self.fail:
            raise self.fail
        if path == unifi.LOGIN_PATH:
            if self.login_status:
                self.refuse(req, self.login_status)
            body = json.loads(req.data.decode())
            if body["password"] != "secret":
                raise urllib.error.HTTPError(req.full_url, 401, "no", {}, io.BytesIO(b""))
            return Resp(b"{}", {"X-CSRF-Token": "tok"})
        if self.data_status:
            self.refuse(req, self.data_status)
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
        p.backoff.last_login -= 60  # the session is a minute old (a refusal right after a login waits, #78)
        self.assertEqual(p.cameras(now=1), {CAM_A: "front_door", CAM_B: "ueber_garten"})
        self.assertEqual([c[0] for c in fake.calls].count("POST"), 2)
        with self.assertRaises(client.DeviceError) as e:
            client.Protect(dict(DEV, password="wrong"), opener=FakeConsole()).cameras()
        self.assertEqual(str(e.exception), "UniFi Protect login refused (check user/password): HTTP 401")
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
        self.assertIn(key, client._protect)  # the session (cookie) is kept across errors (#78)
        client.reset_logins()
        self.assertNotIn(key, client._protect)
        ok = FakeConsole()
        client._protect[key] = client.Protect(dev, opener=ok)
        self.assertEqual(client.protect_state(dev)["events"], [])
        self.assertRaises(client.DeviceError, client.ptz, DEV, "up")
        new = dict(dev, password="other")  # other credentials of the same console replace the old session
        orig = client.Protect
        client.Protect = lambda d, backoff=None: orig(d, opener=FakeConsole(), backoff=backoff)
        try:
            self.assertRaises(client.LoginError, client.protect_state, new)  # FakeConsole wants "secret"
        finally:
            client.Protect = orig
        self.assertNotIn(key, client._protect)
        self.assertIn(key[:3] + ("other",), client._protect)
        client.reset_logins()


class Clock(object):
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class TestLoginBackoff(unittest.TestCase):
    """#78: a refused or rate-limited login is not retried at every poll."""

    def protect(self, fake, clock=None, backoff=None):
        return client.Protect(DEV, opener=fake, backoff=backoff, clock=clock or Clock())

    def polls(self, p, clock, seconds, step=5):
        """Polls every `step` s for `seconds`; returns the errors."""
        errors = []
        end = clock.t + seconds
        while clock.t < end:
            try:
                p.state(now=clock.t)
            except client.DeviceError as e:
                errors.append(e)
            clock.t += step
        return errors

    def test_429_without_retry_after_backs_off_exponentially(self):
        fake, clock = FakeConsole(login_status=429), Clock()
        p = self.protect(fake, clock)
        logins = []
        for _ in range(7):
            with self.assertRaises(client.LoginError) as e:
                p.state(now=clock.t)
            self.assertEqual(e.exception.kind, "rate")
            logins.append((clock.t, fake.logins()))
            wait = e.exception.next_at - clock.t
            # every poll inside the window fails at once, without a request
            self.assertEqual(len(self.polls(p, clock, wait - 1)), len(range(0, int(wait - 1), 5)))
            clock.t = e.exception.next_at
        self.assertEqual([n for _, n in logins], [1, 2, 3, 4, 5, 6, 7])
        waits = [b[0] - a[0] for a, b in zip(logins, logins[1:])]
        self.assertEqual(waits, [30, 60, 120, 300, 900, 900])
        self.assertEqual(str(e.exception), "UniFi Protect login: too many attempts (HTTP 429)")

    def test_429_honours_retry_after(self):
        fake, clock = FakeConsole(login_status=429, retry_after="600"), Clock()
        p = self.protect(fake, clock)
        with self.assertRaises(client.LoginError) as e:
            p.state(now=clock.t)
        self.assertEqual(e.exception.next_at, clock.t + 600)
        self.polls(p, clock, 595)
        self.assertEqual(fake.logins(), 1)
        clock.t = 1600
        fake.retry_after = "5"  # shorter than the backoff: the backoff (60 s for the 2nd failure) wins
        with self.assertRaises(client.LoginError) as e:
            p.state(now=clock.t)
        self.assertEqual(e.exception.next_at, clock.t + 60)
        self.assertEqual(fake.logins(), 2)
        self.assertEqual(client.retry_after("Wed, 21 Oct 2015 07:30:00 GMT", 1445412600), 0)
        self.assertEqual(client.retry_after("Wed, 21 Oct 2015 07:30:00 GMT", 1445412000), 600)
        self.assertEqual(client.retry_after("99999"), client.RETRY_AFTER_MAX)
        self.assertIsNone(client.retry_after("soon"))
        self.assertIsNone(client.retry_after(None))

    def test_429_on_a_data_call_waits_too(self):
        fake, clock = FakeConsole(data_status=429, retry_after="120"), Clock()
        p = self.protect(fake, clock)
        with self.assertRaises(client.LoginError) as e:
            p.state(now=clock.t)
        self.assertEqual((e.exception.kind, e.exception.next_at), ("rate", clock.t + 120))
        n = len(fake.calls)
        self.polls(p, clock, 115)
        self.assertEqual(len(fake.calls), n)  # nothing at all goes to the console while it waits

    def test_403_repeated_is_one_state_and_keeps_backing_off(self):
        fake, clock = FakeConsole(login_status=403), Clock()
        p = self.protect(fake, clock)
        st = PollStatus()
        st.consoles = 1
        new = []
        for _ in range(100):  # 500 s of polls every 5 s
            try:
                p.state(now=clock.t)
            except client.DeviceError as e:
                new.append(st.failed(e, clock.t))
                self.assertEqual(e.kind, "auth")
                self.assertEqual(str(e), "UniFi Protect login refused (check user/password): HTTP 403")
            clock.t += 5
        self.assertEqual(new.count(True), 1)  # logged once, not at every poll or attempt
        self.assertEqual(fake.logins(), 4)  # t=0, 30, 90, 210 (next 510)
        lines = st.lines(lambda t: t, lambda ts: "t%d" % ts)
        self.assertEqual(lines[0], (False, "UniFi Protect: UniFi Protect login refused (check user/password): HTTP 403"))
        self.assertEqual(lines[1], (None, "UniFi Protect: next login attempt t%d" % (1000 + 210 + 300)))
        self.assertNotIn("secret", repr(lines))
        st.ok(2000)
        self.assertIsNone(st.next_retry)

    def test_network_error_is_its_own_kind(self):
        fake, clock = FakeConsole(fail=OSError("unreachable")), Clock()
        with self.assertRaises(client.LoginError) as e:
            self.protect(fake, clock).state(now=clock.t)
        self.assertEqual((e.exception.kind, str(e.exception)), ("network", "UniFi Protect login: not reachable (OSError)"))
        fake = FakeConsole(login_status=500)
        with self.assertRaises(client.LoginError) as e:
            self.protect(fake, clock).state(now=clock.t)
        self.assertEqual((e.exception.kind, str(e.exception)), ("http", "UniFi Protect login: HTTP 500"))

    def test_success_resets_the_backoff_and_keeps_the_session(self):
        fake, clock = FakeConsole(login_status=429), Clock()
        p = self.protect(fake, clock)
        for _ in range(3):  # three failures: the next wait would be 5 min
            self.assertRaises(client.LoginError, p.state, clock.t)
            clock.t = p.backoff.next_at
        fake.login_status = None
        p.state(now=clock.t)
        self.assertEqual((p.backoff.failures, p.backoff.error), (0, None))
        logins = fake.logins()
        self.polls(p, clock, 300)
        self.assertEqual(fake.logins(), logins)  # the session cookie is reused at every poll
        fake.login_status = 429  # a new failure starts at 30 s again
        fake.expire_once = True
        with self.assertRaises(client.LoginError) as e:
            p.state(now=clock.t)
        self.assertEqual(e.exception.next_at, clock.t + 30)

    def test_relogin_after_401_at_most_once_per_window(self):
        fake, clock = FakeConsole(), Clock()
        p = self.protect(fake, clock)
        p.state(now=clock.t)
        self.assertEqual(fake.logins(), 1)
        fake.data_status = 401  # the console keeps refusing the session (e.g. the user lost its role)
        errors = self.polls(p, clock, 600)
        self.assertLessEqual(fake.logins(), 1 + 6)  # not one login per poll (120 polls)
        self.assertTrue(any(isinstance(e, client.LoginError) and e.kind == "auth" for e in errors))
        fake.data_status = None  # fixed: the next attempt after the wait works
        clock.t = p.backoff.next_at
        p.state(now=clock.t)
        logins = fake.logins()
        clock.t += 3600
        fake.expire_once = True  # a session that ran out: one new login and the poll works
        p.state(now=clock.t)
        self.assertEqual(fake.logins(), logins + 1)

    def test_devices_file_change_resets(self):
        dev = dict(DEV, host="192.168.1.98")
        b = client.backoff_for(dev)
        b.failed(client.LoginError("x", "auth"), 1000)
        self.assertIs(client.backoff_for(dev), b)
        self.assertRaises(client.LoginError, b.check, 1001)
        UnifiSource.devices_changed()
        b.check(1001)  # no wait any more
        self.assertEqual(b.failures, 0)
        client._backoff.pop((dev["host"], dev["port"]), None)


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
