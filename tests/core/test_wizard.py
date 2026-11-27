"""#120: the first-start wizard: when it opens, where it looks for go2rtc, the search in threads with a time limit,
and what it saves."""
import json
import threading
import time
import unittest

import _paths

_paths.core()
from camalert_core import wizard  # noqa: E402

STREAMS = json.dumps({
    "front_door": {"producers": [{"url": "rtsp://192.168.1.20:7447/abc"}]},
    "front_door_jpeg": {"producers": [{"url": "ffmpeg:front_door#video=mjpeg"}]},  # helper stream (#117)
    "garden": {"producers": [{"url": "rtsp://192.168.1.21/stream1"}]},
})


class FakeNet(object):
    """go2rtc answers at some addresses, another web service at one, the rest refuses or is slow."""

    def __init__(self, go2rtc=(), other=(), slow=(), delay=0.0):
        self.go2rtc, self.other, self.slow, self.delay = set(go2rtc), set(other), set(slow), delay
        self.asked = []
        self.lock = threading.Lock()

    def probe(self, server):
        with self.lock:
            self.asked.append(server)
        if server in self.slow:
            time.sleep(self.delay)
        if server in self.go2rtc:
            return wizard.cameras_from(STREAMS)
        if server in self.other:
            return wizard.cameras_from("<html>router</html>")
        return None


class TestWizard(unittest.TestCase):
    def test_opens_only_on_a_new_player(self):
        self.assertTrue(wizard.should_start({"server": "", "source": "go2rtc"}))
        self.assertTrue(wizard.should_start({}))
        self.assertFalse(wizard.should_start({"server": "http://192.168.1.10:1984"}))  # existing installation
        self.assertFalse(wizard.should_start({"server": "", "source": "direct"}))
        self.assertFalse(wizard.should_start({"server": "", "wizard_done": True}))
        self.assertTrue(wizard.should_start({"server": "not an address"}) is False)  # invalid != not set

    def test_steps(self):
        self.assertEqual(wizard.steps(), ("go2rtc", "camera", "test", "done"))
        self.assertEqual(wizard.next_step("go2rtc"), "camera")
        self.assertEqual(wizard.next_step("go2rtc", direct=True), "test")
        self.assertIsNone(wizard.next_step("done"))

    def test_candidates_most_likely_first(self):
        c = wizard.candidates("192.168.1.50", "192.168.1.10")
        self.assertEqual(c[:2], ["http://homeassistant.local:1984", "http://192.168.1.10:1984"])
        self.assertEqual(len(c), 2 + 253)  # .1-.254 without the Home Assistant host again
        self.assertEqual(len(set(c)), len(c))
        self.assertIn("http://192.168.1.50:1984", c)  # go2rtc may run on the player itself
        self.assertEqual(wizard.candidates(None), ["http://homeassistant.local:1984"])
        self.assertEqual(wizard.candidates("fe80::1"), ["http://homeassistant.local:1984"])

    def test_ha_host_from_settings(self):
        self.assertEqual(wizard.ha_host({"ha_webhook": "http://192.168.1.10:8123/api/webhook/x"}), "192.168.1.10")
        self.assertEqual(wizard.ha_host({"mqtt_host": "192.168.1.11"}), "192.168.1.11")
        self.assertIsNone(wizard.ha_host({}))

    def test_scan_finds_go2rtc_in_order_and_ignores_other_services(self):
        net = FakeNet(go2rtc={"http://192.168.1.30:1984", "http://homeassistant.local:1984"},
                      other={"http://192.168.1.1:1984"})
        found = wizard.scan(wizard.candidates("192.168.1.50"), net.probe)
        self.assertEqual([s for s, _ in found], ["http://homeassistant.local:1984", "http://192.168.1.30:1984"])
        self.assertEqual(found[0][1], ["front_door", "garden"])  # helper streams left out
        self.assertEqual(len(net.asked), 255)

    def test_scan_has_a_time_limit(self):
        net = FakeNet(go2rtc={"http://192.168.1.2:1984"}, slow={"http://192.168.1.%d:1984" % i for i in range(3, 255)},
                      delay=5.0)
        start = time.time()
        found = wizard.scan(wizard.candidates("192.168.1.50"), net.probe, budget=0.5)
        self.assertLess(time.time() - start, 2.0)
        self.assertEqual([s for s, _ in found], ["http://192.168.1.2:1984"])

    def test_scan_can_be_stopped(self):
        stop = threading.Event()
        stop.set()
        self.assertEqual(wizard.scan(["http://192.168.1.2:1984"], FakeNet(go2rtc={"http://192.168.1.2:1984"}).probe,
                                     stop=stop), [])

    def test_same_go2rtc_under_two_addresses_once(self):
        found = [("http://homeassistant.local:1984", ["front_door"]), ("http://192.168.1.10:1984", ["front_door"]),
                 ("http://192.168.1.30:1984", ["garden"])]
        self.assertEqual([s for s, _ in wizard.unique_servers(found)],
                         ["http://homeassistant.local:1984", "http://192.168.1.30:1984"])

    def test_probe(self):
        class Answer(object):
            def __init__(self, body):
                self.body = body

            def read(self, n):
                return self.body

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def opener(url, timeout):
            self.assertEqual(url, "http://192.168.1.10:1984/api/streams")
            return Answer(STREAMS.encode())

        def refused(url, timeout):
            raise OSError("refused")

        self.assertEqual(wizard.probe("http://192.168.1.10:1984", opener=opener), ["front_door", "garden"])
        self.assertIsNone(wizard.probe("http://192.168.1.10:1984", opener=refused))
        self.assertEqual(wizard.cameras_from("{}"), [])  # go2rtc without cameras: found, but empty
        self.assertIsNone(wizard.cameras_from("[1]"))

    def test_typed_address(self):
        self.assertEqual(wizard.server_from_input("192.168.1.10"), "http://192.168.1.10:1984")
        self.assertEqual(wizard.server_from_input(" http://192.168.1.10:1985/ "), "http://192.168.1.10:1985")
        self.assertEqual(wizard.server_from_input("https://go2rtc.example"), "https://go2rtc.example:443")
        self.assertIsNone(wizard.server_from_input(""))
        self.assertIsNone(wizard.server_from_input("http://"))

    def test_result_and_last_screen(self):
        self.assertEqual(wizard.result("http://192.168.1.10:1984", "garden"),
                         {"wizard_done": True, "source": "go2rtc", "server": "http://192.168.1.10:1984",
                          "camera": "garden"})
        self.assertEqual(wizard.result(direct=True), {"wizard_done": True, "source": "direct"})
        self.assertEqual(wizard.result(), {"wizard_done": True})  # stopped early: does not open again
        self.assertEqual(wizard.add_text("TV player", "192.168.1.40", 8099), ("TV player", "192.168.1.40:8099"))

    def test_own_ip(self):
        class Sock(object):
            def __init__(self, ip=None, fail=False):
                self.ip, self.fail, self.closed = ip, fail, False

            def connect(self, addr):
                if self.fail:
                    raise OSError("network unreachable")

            def getsockname(self):
                return (self.ip, 50000)

            def close(self):
                self.closed = True

        self.assertEqual(wizard.own_ip(lambda *a: Sock("192.168.1.50")), "192.168.1.50")
        self.assertIsNone(wizard.own_ip(lambda *a: Sock("127.0.0.1")))
        self.assertIsNone(wizard.own_ip(lambda *a: Sock(fail=True)))


if __name__ == "__main__":
    unittest.main()
