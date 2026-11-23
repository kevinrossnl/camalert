import glob
import os
import unittest

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

HERE = os.path.dirname(__file__)


@unittest.skipIf(yaml is None, "PyYAML not installed")
class TestBlueprints(unittest.TestCase):
    def load(self, path):
        class Loader(yaml.SafeLoader):
            pass
        Loader.add_constructor("!input", lambda l, n: ("INPUT", l.construct_scalar(n)))
        return yaml.load(open(path, encoding="utf-8"), Loader=Loader)

    def test_inputs_declared_and_used(self):
        files = glob.glob(os.path.join(HERE, "..", "homeassistant", "blueprints", "*.yaml"))
        self.assertEqual(len(files), 3)
        for f in files:
            d = self.load(f)
            used = set()

            def walk(x):
                if isinstance(x, tuple) and x[0] == "INPUT":
                    used.add(x[1])
                elif isinstance(x, dict):
                    for v in x.values():
                        walk(v)
                elif isinstance(x, list):
                    for v in x:
                        walk(v)
            walk({k: v for k, v in d.items() if k != "blueprint"})
            self.assertEqual(used, set(d["blueprint"]["input"]), f)
            self.assertIn("camalert.", str(d["actions"]), f)
            self.assertTrue(d["blueprint"]["source_url"].endswith(os.path.basename(f)), f)
