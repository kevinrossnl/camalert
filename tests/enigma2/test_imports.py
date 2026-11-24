import unittest

import _paths
import importcheck


class TestImports(unittest.TestCase):
    def test_used_core_names_are_imported(self):
        """Every name from the core or from services.py/keys.py that a module uses must be imported (found on a
        receiver test)."""
        self.assertEqual(importcheck.check_folder(_paths.ENIGMA2, ("services.py", "keys.py")), {})


if __name__ == "__main__":
    unittest.main()
