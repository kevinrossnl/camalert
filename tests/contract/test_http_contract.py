"""Every row of the API contract table (api_table.py) against the Enigma2 and the Kodi API handler (#4).

A player that differs from a row fails, unless (row, player) is in KNOWN with the issue that fixes it.
A KNOWN entry that no longer differs fails as well ("stale"): remove it when the issue is fixed.
"""
import os
import re
import unittest

import _paths
from contract.adapters import Enigma2Adapter, KodiAdapter, Request
from contract.api_table import ROUTES, TABLE
from fakes.controller import RecordingController

# (row name, player) -> issue that will remove the difference
KNOWN = {}  # all differences fixed by the API in core (#5); a new one needs an issue


def differences(adapter, r):
    """What is wrong in the player's answer to row r ([] = matches the contract)."""
    ctl = RecordingController(results=r["ctl"].get("results"))
    ctl.fail = r["ctl"].get("fail")
    adapter.reset()
    if r["cameras"] is not None:
        adapter.set_cameras(r["cameras"])
    try:
        ans = adapter.call(Request(r["path"], r["args"], r["ip"], r["header"], r["user_agent"], r["settings"],
                                   r["method"], r["body"]), ctl)
    finally:
        if r["cameras"] is not None:
            adapter.set_cameras(None)
    out = []
    if ans.code != r["code"]:
        out.append("status %s, expected %s" % (ans.code, r["code"]))
    if r["json"] is not None:
        body = ans.json or {}
        for k, v in r["json"].items():
            if body.get(k) != v:
                out.append("%s=%r, expected %r" % (k, body.get(k), v))
    if r["calls"] is not None and ctl.calls != r["calls"]:
        out.append("controller calls %r, expected %r" % (ctl.calls, r["calls"]))
    for k, v in r["headers"].items():
        got = {x.lower(): y for x, y in (ans.headers or {}).items()}.get(k.lower())
        if got != v:
            out.append("header %s=%r, expected %r" % (k, got, v))
    if r["check"] is not None and not out:
        try:
            ok = r["check"](ans.body)
        except Exception as e:  # noqa: BLE001 - report, do not crash the table
            ok, e_ = False, e
            out.append("check raised %r" % e_)
        if not ok and not any(x.startswith("check raised") for x in out):
            out.append("check %s failed on %r" % (r["check"].__name__, ans.body))
    return out


class ContractCase(object):
    adapter_class = None

    @classmethod
    def setUpClass(cls):
        cls.adapter = cls.adapter_class()

    @classmethod
    def tearDownClass(cls):
        close = getattr(cls.adapter, "close", None)
        if close:
            close()

    def test_table(self):
        platform = self.adapter.platform
        unexpected, stale = [], []
        for r in TABLE:
            diff = differences(self.adapter, r)
            known = KNOWN.get((r["name"], platform))
            if diff and not known:
                unexpected.append("%s: %s" % (r["name"], "; ".join(diff)))
            elif known and not diff:
                stale.append("%s (%s)" % (r["name"], known))
        self.assertEqual(unexpected, [], "%s differs from the API contract" % platform)
        self.assertEqual(stale, [], "%s: fixed, remove from KNOWN" % platform)

    def test_rate_limit(self):
        self.adapter.reset()
        codes = [self.adapter.call(Request("/camalert/status", ip="192.168.1.99")).code for _ in range(35)]
        self.assertEqual(codes[0], 200)
        self.assertIn(429, codes)
        self.adapter.reset()


class TestEnigma2Contract(ContractCase, unittest.TestCase):
    adapter_class = Enigma2Adapter


class TestKodiContract(ContractCase, unittest.TestCase):
    adapter_class = KodiAdapter


class TestContractTable(unittest.TestCase):
    def test_known_entries_name_real_rows_and_issues(self):
        names = {r["name"] for r in TABLE}
        self.assertEqual(len(names), len(TABLE), "row names must be unique")
        for (name, platform), issue in KNOWN.items():
            self.assertIn(name, names)
            self.assertIn(platform, ("enigma2", "kodi"))
            self.assertRegex(issue, r"^#\d+$")

    def test_every_home_assistant_call_is_in_the_table(self):
        """Every action the Home Assistant integration calls has rows here, so it cannot fail silently on a
        player (#4)."""
        with open(os.path.join(_paths.HA, "api.py"), encoding="utf-8") as f:
            used = set(re.findall(r'self\._\w+\(\s*"(\w+)"', f.read()))
        self.assertTrue(used)
        self.assertEqual(sorted(used - set(ROUTES)), [])


if __name__ == "__main__":
    unittest.main()
