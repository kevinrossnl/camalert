"""tools/export_contract.py (#64): the JSON that the Android TV player's Kotlin tests read is up to date with the
contract tables and the core, and contains what those tests rely on."""
import json
import os
import unittest

import _paths

_paths.tools()
import export_contract as X  # noqa: E402


class TestExport(unittest.TestCase):
    def test_outputs_are_up_to_date(self):
        stale = []
        for path, text in sorted(X.outputs().items()):
            with open(path, encoding="utf-8") as f:
                if f.read() != text:
                    stale.append(os.path.relpath(path, _paths.ROOT))
        self.assertEqual(stale, [], "run python3 tools/export_contract.py update")
        self.assertEqual(X.main(["x", "check"]), 0)

    def test_every_contract_row_is_exported(self):
        from contract import api_table, mqtt_table
        http = X.http_contract()
        self.assertEqual([r["name"] for r in http["rows"]], [r["name"] for r in api_table.TABLE])
        self.assertTrue(all(r["check"] in (None, "status_keys", "no_snapshot_paths", "log_lines", "prometheus")
                            for r in http["rows"]), "a new check needs its Kotlin twin in HttpContractTest.kt")
        mqtt = X.mqtt_contract()
        self.assertEqual(len(mqtt["commands"]), len(mqtt_table.COMMANDS))
        self.assertTrue(all("model" not in d["payload"]["device"] for d in mqtt["discovery"]))
        self.assertEqual({c["check"]["kind"] for c in mqtt["published"]}, {"one_of", "json_keys", "not_empty"})

    def test_android_settings_follow_the_schema(self):
        from camalert_core import schema
        data = X.runtime()
        ids = [s["id"] for s in data["settings"]]
        kodi = [s.id for s in schema.for_platform("kodi")]
        self.assertEqual(ids, [i for i in kodi if i not in X.NOT_ON_ANDROIDTV], "schema order, Kodi set")
        self.assertTrue(set(X.NOT_ON_ANDROIDTV) <= set(kodi), "only settings that exist")
        for s in data["settings"]:
            want = X.ANDROIDTV_DEFAULTS[s["id"]][0] if s["id"] in X.ANDROIDTV_DEFAULTS else schema.BY_ID[s["id"]].default
            self.assertEqual(s["default"], want, s["id"])
            self.assertEqual(schema.coerce(schema.BY_ID[s["id"]], s["default"]), s["default"], "valid default")
        self.assertEqual(sorted(X.ANDROIDTV_DEFAULTS), ["live_volume"], "a new difference needs a reason in #64")
        self.assertEqual(json.loads(json.dumps(data["keymap"])), json.loads(json.dumps(
            __import__("camalert_core.keymap", fromlist=["x"]).KEYMAP["androidtv"])))


if __name__ == "__main__":
    unittest.main()
