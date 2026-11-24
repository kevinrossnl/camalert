"""Static safety nets (#1, #3):

- Python 3.8 grammar for everything that runs on a receiver or a Kodi box (Kodi 19 = Python 3.8): the files are
  parsed with ast.parse(feature_version=(3, 8)).
- Import lint: the shared modules (used by Enigma2 and Kodi) never import Enigma2, Twisted, Kodi or Home Assistant
  modules, not even inside a function.
"""
import ast
import os
import sys
import unittest

import _paths

try:
    import pytest
    pytestmark = pytest.mark.lint
except ImportError:  # plain unittest
    pass

FORBIDDEN = ("enigma", "Components", "Screens", "Tools", "Plugins", "skin", "twisted",
             "xbmc", "xbmcgui", "xbmcaddon", "xbmcvfs", "xbmcplugin", "homeassistant", "voluptuous", "aiohttp")


def python_files(*folders):
    for folder in folders:
        for d, dirs, names in os.walk(folder):
            dirs[:] = [x for x in dirs if x != "__pycache__"]
            for n in sorted(names):
                if n.endswith(".py"):
                    yield os.path.join(d, n)


def device_code():
    """Everything that runs on a receiver or a Kodi box."""
    return list(python_files(_paths.ENIGMA2, _paths.KODI_ADDON))


def shared_code():
    return [os.path.join(_paths.SHARED, f) for f in _paths.SHARED_MODULES]


def imported_modules(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield node.lineno, a.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.lineno, node.module


def forbidden_imports(path):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    return ["%s:%d imports %s" % (os.path.relpath(path, _paths.ROOT), line, name)
            for line, name in imported_modules(tree) if name.split(".")[0] in FORBIDDEN]


def py38_problems(paths):
    found = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            src = f.read()
        try:
            ast.parse(src, p, feature_version=(3, 8))
        except SyntaxError as e:
            found.append("%s:%s %s" % (os.path.relpath(p, _paths.ROOT), e.lineno, e.msg))
    return found


class TestLint(unittest.TestCase):
    def test_device_code_is_python_38(self):
        files = device_code()
        self.assertGreater(len(files), 20)
        self.assertEqual(py38_problems(files), [])

    def test_shared_code_has_no_platform_imports(self):
        found = []
        for p in shared_code():
            found += forbidden_imports(p)
        self.assertEqual(found, [])

    @unittest.skipIf(sys.version_info < (3, 8), "feature_version needs Python 3.8+")
    def test_grammar_check_finds_new_syntax(self):
        """Self test: syntax of newer Python versions is refused."""
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write("match x:\n    case 1:\n        pass\n")
        try:
            self.assertTrue(py38_problems([f.name]))
        finally:
            os.remove(f.name)

    def test_import_lint_finds_platform_imports(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write("import os\n\ndef f():\n    from enigma import eTimer\n    import xbmcgui\n")
        try:
            self.assertEqual(len(forbidden_imports(f.name)), 2)
        finally:
            os.remove(f.name)


if __name__ == "__main__":
    unittest.main()
