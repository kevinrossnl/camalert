import ast
import os
import unittest

import _paths  # noqa: E402

SRC = _paths.ENIGMA2


class TestLogicImports(unittest.TestCase):
    def test_used_logic_names_are_imported(self):
        """Every function from logic.py that a module uses must be imported (found on a receiver test)."""
        logic = ast.parse(open(os.path.join(SRC, "logic.py"), encoding="utf-8").read())
        exported = {n.name for n in logic.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        exported |= {t.id for n in logic.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
        for f in os.listdir(SRC):
            if not f.endswith(".py") or f == "logic.py":
                continue
            tree = ast.parse(open(os.path.join(SRC, f), encoding="utf-8").read())
            imported = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
            defined = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
            defined |= {t.id for n in ast.walk(tree) if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
            used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
            missing = (used & exported) - imported - defined
            self.assertFalse(missing, "%s uses %s from logic.py without importing it" % (f, sorted(missing)))
