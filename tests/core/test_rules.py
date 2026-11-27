"""camalert_core.rules: modes, durations, priorities, do not disturb, active hours, cooldown."""
import unittest

import _paths

_paths.core()
from camalert_core import rules  # noqa: E402


class TestRules(unittest.TestCase):
    def test_clamp_and_mode(self):
        self.assertEqual(rules.clamp_seconds("2"), 5)
        self.assertEqual(rules.clamp_seconds("999"), 300)
        self.assertEqual(rules.clamp_seconds("x", 30), 30)
        self.assertEqual(rules.clamp_seconds(float("inf"), 30), 30)  # found by the property tests (#34)
        self.assertEqual(rules.pick_mode("live"), "live")
        self.assertEqual(rules.pick_mode("evil", "photo"), "photo")

    def test_decide(self):
        self.assertEqual(rules.decide(True, None, None, "a"), "ignore")
        self.assertEqual(rules.decide(False, None, None, ""), "ignore")
        self.assertEqual(rules.decide(False, "a", None, "a"), "ignore")
        self.assertEqual(rules.decide(False, None, "a", "a"), "extend")
        self.assertEqual(rules.decide(False, None, "b", "a"), "show")

    def test_should_pause(self):
        self.assertTrue(rules.should_pause(True, "photo", False))
        self.assertTrue(rules.should_pause(True, "notify", False))
        self.assertFalse(rules.should_pause(True, "live", False))
        self.assertFalse(rules.should_pause(True, "photo", True))
        self.assertFalse(rules.should_pause(False, "photo", False))

    def test_time_window(self):
        self.assertTrue(rules.in_time_window((12, 0), (7, 0), (23, 0)))
        self.assertFalse(rules.in_time_window((23, 0), (7, 0), (23, 0)))
        self.assertFalse(rules.in_time_window((6, 59), (7, 0), (23, 0)))
        self.assertTrue(rules.in_time_window((1, 0), (22, 0), (6, 0)))
        self.assertFalse(rules.in_time_window((12, 0), (22, 0), (6, 0)))
        self.assertTrue(rules.in_time_window((3, 3), (8, 0), (8, 0)))

    def test_lowered_volume(self):
        self.assertEqual(rules.lowered_volume(60, 50), 30)
        self.assertEqual(rules.lowered_volume(60, 100), 60)
        self.assertEqual(rules.lowered_volume(60, 0), 0)
        self.assertEqual(rules.lowered_volume(60, 150), 60)

    def test_priority_rules(self):
        self.assertEqual(rules.pick_priority("alarm"), "alarm")
        self.assertEqual(rules.pick_priority("x"), "normal")
        self.assertTrue(rules.blocked_by_rules("normal", True, False, False, False))
        self.assertTrue(rules.blocked_by_rules("normal", False, True, True, True))
        self.assertFalse(rules.blocked_by_rules("normal", True, True, True, False))
        self.assertFalse(rules.blocked_by_rules("high", True, False, True, True))
        self.assertFalse(rules.blocked_by_rules("alarm", True, False, True, True))

    def test_clock_tuple(self):
        self.assertEqual(rules.clock_tuple([7, 30]), (7, 30))
        self.assertEqual(rules.clock_tuple("03:05"), (3, 5))
        self.assertEqual(rules.clock_tuple(23 * 3600 + 60), (23, 1))
        self.assertEqual(rules.clock_tuple(None), (0, 0))

    def test_cooldown(self):
        self.assertEqual(rules.cooldown_seconds("garden", "*=30|garden=120"), 120)
        self.assertEqual(rules.cooldown_seconds("drive", "*=30|garden=120"), 30)
        self.assertEqual(rules.cooldown_seconds("drive", ""), 0)
        self.assertEqual(rules.cooldown_seconds("x", "*=abc"), 0)
        self.assertTrue(rules.in_cooldown(100.0, 110.0, 30))
        self.assertFalse(rules.in_cooldown(100.0, 140.0, 30))
        self.assertFalse(rules.in_cooldown(None, 140.0, 30))
        self.assertFalse(rules.in_cooldown(100.0, 110.0, 0))

    def test_dnd(self):
        self.assertTrue(rules.dnd_blocks("normal", True))
        self.assertFalse(rules.dnd_blocks("high", True))
        self.assertTrue(rules.dnd_blocks("high", True, "high"))
        self.assertFalse(rules.dnd_blocks("alarm", True, "high"))
        self.assertFalse(rules.dnd_blocks("normal", False))
        self.assertTrue(rules.blocked_by_rules("normal", False, True, False, False, True, True))
        self.assertFalse(rules.blocked_by_rules("high", False, True, False, False, True, True))


if __name__ == "__main__":
    unittest.main()
