#!/usr/bin/env python3
"""Writes the JSON-RPC methods of one Kodi version (name, parameters, required, allowed values) for the strict
Kodi stubs (tests/kodi/stubs.py, #29).

    kodi_jsonrpc_snapshot.py <methods.json> <types.json> <kodi major> > tests/kodi/fixtures/jsonrpc/<major>.json

methods.json / types.json are Kodi's own schema (xbmc/interfaces/json-rpc/schema/ in the Kodi sources, branch
Matrix = 19, Nexus = 20, Omega = 21, Piers = 22): public data, no device needed.
Copyright (C) 2026 CamAlert developers, GPL v2.
"""
import json
import re
import sys


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.loads(re.sub(r"^\s*//.*$", "", f.read(), flags=re.M))


def enum_of(spec, types, depth=0):
    """Allowed values of a parameter (also for arrays of an enum type), or None."""
    if not isinstance(spec, dict) or depth > 4:
        return None
    if "enum" in spec:
        return sorted(set(spec["enum"]))
    if "$ref" in spec:
        return enum_of(types.get(spec["$ref"]), types, depth + 1)
    if spec.get("type") == "array":
        return enum_of(spec.get("items"), types, depth + 1)
    return None


def snapshot(methods, types, major):
    out = {}
    for name, m in sorted(methods.items()):
        if m.get("type") != "method":
            continue
        params = []
        for p in m.get("params", []):
            entry = {"name": p["name"], "required": bool(p.get("required"))}
            values = enum_of(p, types)
            if values:
                entry["enum"] = values
            params.append(entry)
        out[name] = {"params": params}
    return {"kodi": major, "source": "Kodi JSON-RPC schema (methods.json, types.json)", "methods": out}


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    json.dump(snapshot(load(sys.argv[1]), load(sys.argv[2]), int(sys.argv[3])), sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")
