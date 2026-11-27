"""camalert_core.settingsfile: settings as one file, import with validation and migration, backups, rollback (#7)."""
import json
import os
import shutil
import stat
import tempfile
import unittest

import _paths

_paths.core()
from camalert_core import schema, settingsfile as sf  # noqa: E402


def values(platform, **changes):
    v = schema.defaults(platform)
    v.update(changes)
    return v


class TestExport(unittest.TestCase):
    def test_export_by_schema_id_without_secrets_and_internal(self):
        cur = values("kodi", server="http://192.168.1.10:1984", token="s3cret", mqtt_password="pw", ptz_password="x",
                     wizard_done=True, ha_webhook="http://192.168.1.20:8123/api/webhook/abc")
        doc = sf.export(cur, "kodi", player="CamAlert Kodi")
        self.assertEqual((doc["format"], doc["schema_version"], doc["platform"], doc["secrets"], doc["player"]),
                         (sf.FORMAT, schema.SCHEMA_VERSION, "kodi", False, "CamAlert Kodi"))
        s = doc["settings"]
        self.assertEqual(s["server"], "http://192.168.1.10:1984")
        for gone in ("token", "mqtt_password", "ptz_password", "wizard_done", "ha_webhook"):
            self.assertNotIn(gone, s)
        self.assertNotIn("s3cret", sf.dumps(doc))
        with_secrets = sf.export(cur, "kodi", secrets=True)["settings"]
        self.assertEqual((with_secrets["token"], with_secrets["mqtt_password"]), ("s3cret", "pw"))
        self.assertNotIn("wizard_done", with_secrets)  # internal: never in a file

    def test_export_uses_types_and_platform_keys(self):
        cur = values("kodi", enabled="false", rtsp_port="8555")  # Kodi stores strings
        s = sf.export(cur, "kodi")["settings"]
        self.assertIs(s["enabled"], False)
        self.assertEqual(s["rtsp_port"], 8555)
        self.assertEqual(json.loads(sf.dumps(sf.export(cur, "kodi")))["settings"]["rtsp_port"], 8555)

    def test_secret_ids(self):
        self.assertIn("token", sf.SECRET_IDS)
        self.assertTrue({"mqtt_password", "ptz_password"} <= set(sf.SECRET_IDS))


class TestRead(unittest.TestCase):
    def test_round_trip_to_another_player_of_the_same_kind(self):
        a = values("enigma2", server="http://192.168.1.10:1984", camera="front_door", position="bottom_left")
        b = values("enigma2", token="mine")
        new, report = sf.read(sf.dumps(sf.export(a, "enigma2")), "enigma2", b)
        self.assertEqual((new["server"], new["camera"], new["position"]),
                         ("http://192.168.1.10:1984", "front_door", "bottom_left"))
        self.assertEqual(new["token"], "mine")  # the file had no secrets: this player's token stays
        self.assertEqual(sorted(report["changed"]), ["camera", "position", "server"])
        self.assertEqual((report["problems"], report["unknown"], report["secrets"]), ([], [], False))

    def test_secrets_imported_when_the_file_has_them(self):
        a = values("kodi", token="t1", mqtt_password="pw")
        new, report = sf.read(sf.dumps(sf.export(a, "kodi", secrets=True)), "kodi", values("kodi"))
        self.assertEqual((new["token"], new["mqtt_password"], report["secrets"]), ("t1", "pw", True))

    def test_broken_values_keep_the_current_value(self):
        doc = sf.export(values("kodi"), "kodi")
        doc["settings"].update(rtsp_port=99999, position="middle", enabled="maybe", server="http://192.168.1.11:1984")
        cur = values("kodi", rtsp_port=8554)
        new, report = sf.read(sf.dumps(doc), "kodi", cur)
        self.assertEqual((new["rtsp_port"], new["position"], new["enabled"]), (8554, cur["position"], cur["enabled"]))
        self.assertEqual(new["server"], "http://192.168.1.11:1984")
        self.assertEqual(sorted(report["problems"]), ["enabled", "position", "rtsp_port"])

    def test_other_player_unknown_and_internal_settings(self):
        doc = sf.export(values("kodi", camera_file="/storage/cams.conf"), "kodi")  # camera_file: Kodi only
        doc["settings"].update(future_setting=1, wizard_done=True)
        cur = values("androidtv")
        new, report = sf.read(sf.dumps(doc), "androidtv", cur)
        self.assertIn("camera_file", report["skipped"])
        self.assertIn("wizard_done", report["skipped"])  # internal: the file cannot set it
        self.assertEqual(report["unknown"], ["future_setting"])
        self.assertEqual(new["wizard_done"], cur["wizard_done"])
        self.assertNotIn("camera_file", new)

    def test_partial_file_keeps_the_rest(self):
        text = json.dumps({"format": sf.FORMAT, "schema_version": schema.SCHEMA_VERSION,
                           "settings": {"size": "large"}})
        cur = values("enigma2", server="http://192.168.1.10:1984")
        new, report = sf.read(text, "enigma2", cur)
        self.assertEqual((new["size"], new["server"], report["changed"]), ("large", "http://192.168.1.10:1984", ["size"]))

    def test_older_schema_is_migrated(self):
        """A version-1 file (Enigma2 yes/no chime, skip_media) gets the version-2 meanings (schema.migrate)."""
        text = json.dumps({"format": sf.FORMAT, "schema_version": 1,
                           "settings": {"chime": True, "skip_media": "yes"}})
        new, report = sf.read(text, "enigma2", values("enigma2"))
        self.assertEqual((new["chime"], new["skip_playing"]), ("high", "video"))
        self.assertEqual(report["unknown"], [])

    def test_bad_files(self):
        for text, reason in (("", "not a settings file"), ("[1]", "not a settings file"), ("{nope", "not a settings file"),
                             (json.dumps({"format": "other", "schema_version": 2, "settings": {}}), "not a settings file"),
                             (json.dumps({"format": sf.FORMAT, "schema_version": True, "settings": {}}), "not a settings file"),
                             (json.dumps({"format": sf.FORMAT, "schema_version": 2, "settings": []}), "not a settings file"),
                             (json.dumps({"format": sf.FORMAT, "schema_version": schema.SCHEMA_VERSION + 1,
                                          "settings": {}}), "made by a newer CamAlert")):
            with self.assertRaises(sf.BadFile) as e:
                sf.read(text, "kodi", values("kodi"))
            self.assertEqual(str(e.exception), reason)


class TestBackups(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.t = [1700000000.0]
        self.b = sf.Backups(os.path.join(self.dir, "backups"), keep=3, clock=lambda: self.t[0])

    def tearDown(self):
        shutil.rmtree(self.dir)

    def tick(self):
        self.t[0] += 61

    def test_backup_has_secrets_owner_only_and_keeps_the_newest(self):
        paths = []
        for i in range(5):
            paths.append(self.b.save(values("kodi", token="t%d" % i), "kodi", "import"))
            os.utime(paths[-1], (self.t[0], self.t[0]))
            self.tick()
        items = self.b.list()
        self.assertEqual([x["path"] for x in items], paths[:1:-1])  # newest 3, newest first
        self.assertFalse(os.path.exists(paths[0]))
        self.assertEqual(stat.S_IMODE(os.stat(paths[-1]).st_mode), 0o600)
        with open(paths[-1]) as f:
            doc = json.load(f)
        self.assertEqual((doc["settings"]["token"], doc["reason"], doc["secrets"]), ("t4", "import", True))

    def test_same_second_does_not_overwrite(self):
        a = self.b.save(values("kodi"), "kodi", "import")
        b = self.b.save(values("kodi"), "kodi", "import")
        self.assertNotEqual(a, b)
        self.assertTrue(os.path.exists(a) and os.path.exists(b))

    def test_rollback_restores_and_can_be_undone(self):
        before = values("enigma2", server="http://192.168.1.10:1984", token="t")
        p = self.b.save(before, "enigma2", "import")
        os.utime(p, (self.t[0], self.t[0]))
        self.tick()
        after = dict(before, server="http://192.168.1.99:1984", token="t")
        new, report, used = self.b.rollback("enigma2", after)
        self.assertEqual((new["server"], new["token"], used["reason"]), ("http://192.168.1.10:1984", "t", "import"))
        self.assertEqual(report["changed"], ["server"])
        newest = self.b.latest()
        self.assertEqual(newest["reason"], "rollback")  # the settings before the rollback are kept too
        with open(newest["path"]) as f:
            self.assertEqual(json.load(f)["settings"]["server"], "http://192.168.1.99:1984")

    def test_backup_before_a_migration_restores_with_the_new_meanings(self):
        old = {"chime": "true", "skip_media": "true", "foscam_poll": "true", "server": "http://192.168.1.10:1984"}
        path = self.b.save(old, "enigma2", "migration", schema_version=1)
        with open(path) as f:
            doc = json.load(f)
        self.assertEqual((doc["schema_version"], doc["settings"]["foscam_poll"]), (1, "true"))
        new, report, used = self.b.rollback("enigma2", values("enigma2"))
        self.assertEqual((new["chime"], new["skip_playing"], new["foscam_enabled"], new["server"]),
                         ("high", "video", True, "http://192.168.1.10:1984"))
        self.assertEqual(used["reason"], "migration")

    def test_no_backups(self):
        self.assertEqual(self.b.list(), [])
        self.assertIsNone(self.b.latest())
        self.assertIsNone(self.b.rollback("kodi", values("kodi")))

    def test_broken_files_in_the_folder_are_ignored(self):
        os.makedirs(self.b.folder)
        with open(os.path.join(self.b.folder, "settings-backup-broken.json"), "w") as f:
            f.write("{")
        with open(os.path.join(self.b.folder, "other.json"), "w") as f:
            f.write("{}")
        self.assertEqual(self.b.list(), [])


if __name__ == "__main__":
    unittest.main()
