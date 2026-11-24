"""camalert_core.events: event list and diagnostics lines."""
import unittest

import _paths

_paths.core()
from camalert_core import events as ev  # noqa: E402


class TestEvents(unittest.TestCase):
    def test_events(self):
        events = []
        for i in range(25):
            dropped = ev.add_event(events, {"n": i}, limit=20)
        self.assertEqual(len(events), 20)
        self.assertEqual(events[0]["n"], 24)
        self.assertEqual(dropped, [{"n": 4}])
        self.assertEqual(ev.caller_source("HomeAssistant/2026.11 aiohttp/3.12 Python/3.13"), "ha")
        self.assertEqual(ev.caller_source("curl/8.5"), "api")
        self.assertEqual(ev.event_title("Front door", "Person"), "Person · Front door")
        self.assertEqual(ev.event_title("Front door", None), "Front door")
        self.assertFalse(hasattr(ev, "event_line"))  # English line removed; screens use present.event_line (#41)
        self.assertEqual(ev.diag_line(True, "pwd=x ok"), "[ OK ]  pwd=*** ok")
        self.assertEqual(ev.diag_line(False, "x")[:6], "[FAIL]")

    def test_test_source(self):
        """#62: requests with test=1 have the source "test", a listed source with its own label."""
        self.assertTrue(ev.is_test(ev.TEST_SOURCE))
        self.assertFalse(ev.is_test("api"))
        self.assertIn("test", ev.SOURCES)


if __name__ == "__main__":
    unittest.main()
