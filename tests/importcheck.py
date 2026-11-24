"""Finds names a module uses from the core (or from a player's own helper modules) without importing them
(found on a receiver test: a missing import only fails when that code path runs)."""
import ast
import os

import _paths


def module_names(path):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    out = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.Assign):
            out |= {t.id for t in n.targets if isinstance(t, ast.Name)}
            out |= {e.id for t in n.targets if isinstance(t, ast.Tuple) for e in t.elts if isinstance(e, ast.Name)}
    return out


def missing_imports(path, exported):
    """Names of `exported` that the module at path uses but neither imports nor defines."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    imported = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, (ast.ImportFrom, ast.Import))
                for a in n.names}
    defined = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    defined |= {t.id for n in ast.walk(tree) if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign))
                for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)}
    defined |= {e.id for n in ast.walk(tree) if isinstance(n, ast.Assign) for t in n.targets
                if isinstance(t, ast.Tuple) for e in t.elts if isinstance(e, ast.Name)}
    defined |= {a.arg for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.Lambda)) for a in
                n.args.args + n.args.kwonlyargs}
    defined |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    return sorted((used & exported) - imported - defined)


def check_folder(folder, helper_modules=()):
    """{file: [missing names]} for every module of a player package."""
    exported = set(_paths.core_names())
    for h in helper_modules:
        exported |= module_names(os.path.join(folder, h))
    out = {}
    for f in sorted(os.listdir(folder)):
        if f.endswith(".py"):
            m = missing_imports(os.path.join(folder, f), exported - module_names(os.path.join(folder, f)))
            if m:
                out[f] = m
    return out
