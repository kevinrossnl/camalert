"""The temporary shims (#1): <player>/logic.py, devices.py and camlog.py ARE the core modules (same objects, same
module state), on Enigma2 and on Kodi. Remove this test together with the shims."""
import unittest

import _paths


class TestShims(unittest.TestCase):
    def test_enigma2(self):
        from enigma2.harness import e2fake
        env = e2fake.install("openatv")
        try:
            import importlib
            for name in _paths.SHIMS:
                shim = importlib.import_module("CamAlert." + name)
                core = importlib.import_module("CamAlert.camalert_core." + name)
                self.assertIs(shim, core, name)
            self.assertIs(env.camalert.display.redact, core_attr("CamAlert", "logic", "redact"))
        finally:
            e2fake.uninstall()

    def test_kodi(self):
        from kodi import stubs
        stubs.install()
        _paths.kodi_package()
        for name in _paths.SHIMS:
            self.assertIs(_paths.kodi_module(name), _paths.kodi_module("camalert_core." + name), name)
        self.assertIs(_paths.kodi_module("server").redact, core_attr("camalert", "logic", "redact"))


def core_attr(package, module, attr):
    import sys
    return getattr(sys.modules["%s.camalert_core.%s" % (package, module)], attr)


if __name__ == "__main__":
    unittest.main()
