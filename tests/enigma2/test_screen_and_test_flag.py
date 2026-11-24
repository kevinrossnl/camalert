"""#63: hide closes the mosaic and the tour (also stacked ones), status "screen" says what is shown;
#62: a test request (source "test") never plays the doorbell chime and is tagged in the event list."""
import unittest

import _paths  # noqa: F401
from enigma2.test_ui_findings import CAMS, Base


class TestScreen(Base):
    def run_later(self, name):
        """Runs the callLater calls of `name` (the fake reactor only records them)."""
        for c in list(self.env.reactor.calls):
            if getattr(c.fn, "__name__", "") == name:
                self.env.reactor.calls.remove(c)
                c.fn(*c.a, **c.kw)

    def test_status_screen(self):
        self.assertEqual(self.ctl.status()["screen"], "none")
        self.assertEqual(self.ctl.show("garden", 10, "photo", "normal"), "show")
        self.assertEqual(self.ctl.status()["screen"], "photo")
        self.ctl.hide()
        self.assertEqual(self.ctl.show("front_door,garden", 10, "photo", "normal"), "show")
        self.assertEqual(self.ctl.status()["screen"], "strip")
        self.ctl.hide()
        self.assertEqual(self.ctl.status()["screen"], "none")

    def test_hide_closes_mosaic_and_tour(self):
        m = self.session.open(self.d.MosaicScreen, CAMS, 0)
        self.assertEqual(self.ctl.status()["screen"], "mosaic")
        t = self.session.open(self.d.TourScreen, CAMS, 8)
        self.assertEqual(self.ctl.status()["screen"], "tour")
        self.ctl.hide()
        self.assertEqual([s for s, _r in self.session.closed], [t])  # Enigma2 closes only the top dialog ...
        self.assertEqual(self.ctl.status()["screen"], "mosaic")
        self.run_later("close_fullscreens")                           # ... the next one after it has gone
        self.assertEqual([s for s, _r in self.session.closed], [t, m])
        self.assertEqual((self.ctl.status()["screen"], self.ctl.fullscreens), ("none", []))

    def test_closed_by_the_user_is_forgotten(self):
        m = self.session.open(self.d.MosaicScreen, CAMS, 0)
        m.close()  # EXIT on the remote
        self.assertEqual(self.ctl.status()["screen"], "none")
        self.ctl.hide()
        self.assertEqual(len(self.session.closed), 1)

    def test_hide_does_not_close_a_screen_of_someone_else(self):
        """Another dialog on top (e.g. a menu): only the top dialog can be closed; retried a few times."""
        m = self.session.open(self.d.MosaicScreen, CAMS, 0)
        self.session.current_dialog = object()
        self.ctl.hide()
        self.assertEqual(self.session.closed, [])
        self.session.current_dialog = m
        self.run_later("close_fullscreens")
        self.assertEqual([s for s, _r in self.session.closed], [m])

    def test_tour_live_and_close_failure(self):
        t = self.session.open(self.d.TourScreen, CAMS, 8)

        def broken(*a):
            raise RuntimeError("not the top dialog")
        t.close = broken
        self.ctl.hide()  # must not raise
        self.assertEqual(self.ctl.fullscreens, [])


class TestTestFlag(Base):
    def test_no_chime_for_a_test_request(self):
        rang = []
        self.ctl.chime = lambda: rang.append(1)
        self.c.chime.value = "all"
        self.assertEqual(self.ctl.show("garden", 10, "photo", "normal", "test"), "show")
        self.assertEqual(rang, [])
        self.assertEqual(self.ctl.events[0]["source"], "test")
        self.ctl.hide()
        self.ctl.last_shown.clear()
        self.assertEqual(self.ctl.show("garden", 10, "photo", "normal", "api"), "show")
        self.assertEqual(rang, [1])

    def test_test_label_in_the_event_list(self):
        self.ctl.show("garden", 10, "photo", "normal", "test")
        s = self.session.open(self.ca.diagnostics.EventsScreen)
        self.assertIn("Test request", s["list"].list[0][0])


if __name__ == "__main__":
    unittest.main()
