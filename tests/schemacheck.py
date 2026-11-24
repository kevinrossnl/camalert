"""Compares what a player has with the settings schema (camalert_core.schema, #38)."""
import _paths

_paths.core()
from camalert_core import schema  # noqa: E402

FIELDS = ("type", "default", "min", "max", "step", "choices", "label")


def differences(platform, actual):
    """actual: {player key: {field: value}} (only the fields the player can express).
    Returns sorted [(schema id, field, player value, schema value)]; field 'missing' / 'extra' / 'key' for
    settings that are not there, not in the schema, or stored under another key."""
    out = []
    keys = set(actual)
    for s in schema.for_platform(platform):
        k = s.key(platform)
        if k != s.id:
            out.append((s.id, "key", k, s.id))
        if k not in actual:
            out.append((s.id, "missing", None, k))
            continue
        keys.discard(k)
        for f in FIELDS:
            if f in actual[k]:
                want = getattr(s, f)
                if f == "choices" and want is not None:
                    want = tuple(want)
                if actual[k][f] != want:
                    out.append((s.id, f, actual[k][f], want))
    for k in sorted(keys):
        out.append((k, "extra", k, None))
    return sorted(out, key=lambda x: (x[0], x[1]))


def check(testcase, platform, actual, known):
    """Fails on differences that are not in known {(id, field): issue}, and on stale known entries."""
    found = {(i, f): (a, w) for i, f, a, w in differences(platform, actual)}
    unexpected = ["%s %s: %s has %r, schema %r" % (i, f, platform, a, w) for (i, f), (a, w) in sorted(found.items())
                  if (i, f) not in known]
    stale = ["%s %s (%s)" % (i, f, issue) for (i, f), issue in sorted(known.items()) if (i, f) not in found]
    testcase.assertEqual(unexpected, [], "%s settings differ from camalert_core/schema.py" % platform)
    testcase.assertEqual(stale, [], "fixed: remove from KNOWN")
