import os
import sys
import unittest

import _paths  # noqa: E402

_paths.shared()
from camalert_core import logic as L  # noqa: E402


class TestRobustness(unittest.TestCase):
    def test_ipv6_servers(self):
        self.assertEqual(L.normalize_server("fd00::10"), "http://[fd00::10]:1984")
        self.assertEqual(L.normalize_server("[fd00::10]:1985"), "http://[fd00::10]:1985")
        self.assertEqual(L.normalize_server("https://[2001:db8::1]"), "https://[2001:db8::1]:443")
        self.assertIsNone(L.normalize_server("http://host:99999"))
        self.assertEqual(L.rtsp_url("http://[fd00::10]:1984", "garden"), "rtspt://[fd00::10]:8554/garden")
        self.assertEqual(L.snapshot_url("http://[fd00::10]:1984", "garden"),
                         "http://[fd00::10]:1984/api/frame.jpeg?src=garden&width=640")

    def test_cooldown(self):
        self.assertEqual(L.cooldown_seconds("garden", "*=30|garden=120"), 120)
        self.assertEqual(L.cooldown_seconds("drive", "*=30|garden=120"), 30)
        self.assertEqual(L.cooldown_seconds("drive", ""), 0)
        self.assertEqual(L.cooldown_seconds("x", "*=abc"), 0)
        self.assertTrue(L.in_cooldown(100.0, 110.0, 30))
        self.assertFalse(L.in_cooldown(100.0, 140.0, 30))
        self.assertFalse(L.in_cooldown(None, 140.0, 30))
        self.assertFalse(L.in_cooldown(100.0, 110.0, 0))

    def test_metrics(self):
        text = L.metrics_text({"requests_total": ("counter", "Requests", {"show": 3}), "dnd": ("gauge", "DND", True),
                               "uptime_seconds": ("gauge", "Up", 12.5)}, {"version": "1.0.0"})
        self.assertIn("# TYPE camalert_requests_total counter", text)
        self.assertIn('camalert_requests_total{version="1.0.0",key="show"} 3', text)
        self.assertIn('camalert_dnd{version="1.0.0"} 1', text)
        self.assertIn('camalert_uptime_seconds{version="1.0.0"} 12.5', text)
        self.assertTrue(text.endswith("\n"))

    def test_rate_limit_and_exposure(self):
        r = L.RateLimiter(3, 10)
        self.assertEqual([r.allow("a", t) for t in (0, 1, 2, 3)], [True, True, True, False])
        self.assertTrue(r.allow("b", 3))
        self.assertTrue(r.allow("a", 11))
        self.assertTrue(L.exposed_without_token("any", "", "1.2.3.4"))
        self.assertFalse(L.exposed_without_token("any", "secret", "1.2.3.4"))
        self.assertFalse(L.exposed_without_token("any", "", "192.168.1.5"))
        self.assertFalse(L.exposed_without_token("lan", "", "1.2.3.4"))

    def test_substreams(self):
        self.assertEqual(L.live_stream_name("front_door", "front_door=front_door_sub"), "front_door_sub")
        self.assertEqual(L.live_stream_name("garden", "front_door=front_door_sub"), "garden")


if __name__ == "__main__":
    unittest.main()
