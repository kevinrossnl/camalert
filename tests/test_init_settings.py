import os
import re
import unittest

SRC = os.path.join(os.path.dirname(__file__), "..", "src", "CamAlert", "__init__.py")


class TestSettingsAreGuarded(unittest.TestCase):
    def test_every_setting_goes_through_add(self):
        """A broken saved value must not stop the plugin from loading (found on a receiver: ConfigClock)."""
        text = open(SRC, encoding="utf-8").read()
        self.assertFalse(re.search(r"^c\.[a-z_]+ = Config", text, re.M), "use _add(name, lambda: Config...)")
        self.assertGreater(len(re.findall(r'^_add\("', text, re.M)), 30)
