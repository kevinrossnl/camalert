"""Enigma2: settings export / import / undo from the settings screen's MENU, and a backup before a migration (#7)."""
import json
import os
import shutil
import stat
import tempfile
import unittest

import _paths  # noqa: F401
from enigma2.harness import e2fake


class TestSettingsIO(unittest.TestCase):
    def setUp(self):
        self.env = e2fake.install("openatv")
        self.ca = self.env.camalert
        self.io = __import__("CamAlert.settingsio", fromlist=["x"])
        self.c = self.env.config.plugins.camalert
        self.c.server.value = "http://192.168.1.10:1984"
        self.c.token.value = "s3cret"
        self.c.from_time.value = [6, 30]
        self.c.wizard_done.value = True
        for x in (self.c.server, self.c.token, self.c.from_time, self.c.wizard_done):
            x.save()
        self.dir = tempfile.mkdtemp()
        self.io.EXPORT_DIRS = (self.dir,)
        self.session = self.env.Session()
        self.env.InfoBar(self.session)
        self.ca.plugin.sessionstart(0, session=self.session)
        self.shown = []
        for name in ("open", "openWithCallback"):
            orig = getattr(self.session, name)

            def wrap(*a, _orig=orig, **kw):
                self.shown.append((a, kw))
                return _orig(*a, **kw)
            setattr(self.session, name, wrap)

    def tearDown(self):
        e2fake.uninstall()
        shutil.rmtree(self.dir)

    def screen(self):
        self.ca.plugin.main(self.session)
        return self.session.opened[-1]

    def text(self):
        """Text of the last message box."""
        a, kw = self.shown[-1]
        args = [x for x in a if isinstance(x, str)]
        return args[0] if args else kw.get("text", "")

    def test_export_without_and_with_secrets(self):
        path = self.io.export()
        self.assertEqual(path, os.path.join(self.dir, "camalert-settings.json"))
        with open(path) as f:
            doc = json.load(f)
        self.assertEqual(doc["settings"]["server"], "http://192.168.1.10:1984")
        self.assertEqual(doc["settings"]["from_time"], "06:30")
        self.assertNotIn("token", doc["settings"])
        self.assertNotIn("wizard_done", doc["settings"])
        path = self.io.export(secrets=True)
        with open(path) as f:
            self.assertEqual(json.load(f)["settings"]["token"], "s3cret")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def write(self, **settings):
        doc = {"format": "camalert-settings", "schema_version": 2, "settings": settings}
        with open(os.path.join(self.dir, "camalert-settings.json"), "w") as f:
            json.dump(doc, f)

    def test_import_and_undo(self):
        self.write(server="http://192.168.1.11:1984", from_time="07:15", rtsp_port=8555, position="nowhere")
        report = self.io.do_import(self.io.import_file())
        self.assertEqual(self.c.server.value, "http://192.168.1.11:1984")
        self.assertEqual(self.c.from_time.value, [7, 15])
        self.assertEqual(int(self.c.rtsp_port.value), 8555)
        self.assertEqual(self.c.token.value, "s3cret")  # not in the file: kept
        self.assertEqual(report["problems"], ["position"])
        self.assertTrue(os.path.isfile(report["backup"]))
        self.assertTrue(report["backup"].startswith(self.env.backup_dir))
        self.assertEqual(self.c.server.saved_value, "http://192.168.1.11:1984")  # saved, not only set
        report = self.io.undo()
        self.assertEqual((self.c.server.value, self.c.from_time.value), ("http://192.168.1.10:1984", [6, 30]))
        self.assertEqual(int(self.c.rtsp_port.value), 8554)
        self.assertIn("server", report["changed"])

    def test_bad_file_changes_nothing(self):
        with open(os.path.join(self.dir, "camalert-settings.json"), "w") as f:
            f.write("not json")
        with self.assertRaises(self.io.settingsfile.BadFile):
            self.io.do_import(self.io.import_file())
        self.assertEqual(self.io.backups().list(), [])
        self.assertEqual(self.c.server.value, "http://192.168.1.10:1984")

    def test_menu(self):
        s = self.screen()
        s.menu()
        self.assertEqual([c[1] for c in self.shown[-1][1]["list"]][-3:], ["export", "import", "expert"])  # no undo yet
        s.menu_chosen(("Import settings", "import"))
        self.assertIn("No camalert-settings.json found", self.text())
        s.menu_chosen(("Export settings", "export"))
        s.export_chosen(("Without passwords and access token", False))
        self.assertIn("Settings saved in %s" % self.dir, self.text())
        self.write(size="large")
        s.menu_chosen(("Import settings", "import"))
        self.assertIn("Import the settings from", self.text())
        s.import_confirmed(True)
        self.assertEqual(self.c.size.value, "large")
        self.assertIn("1 settings changed.", self.text())
        s.menu()
        self.assertIn("undo", [c[1] for c in self.shown[-1][1]["list"]])
        s.menu_chosen(("Undo the last import", "undo"))
        s.undo_confirmed(True)
        self.assertEqual(self.c.size.value, "medium")

    def test_menu_reports_a_bad_file(self):
        s = self.screen()
        with open(os.path.join(self.dir, "camalert-settings.json"), "w") as f:
            f.write(json.dumps({"format": "camalert-settings", "schema_version": 99, "settings": {}}))
        s.menu_chosen(("Import settings", "import"))
        s.import_confirmed(True)
        self.assertIn("cannot be imported (made by a newer CamAlert)", self.text())


class TestMigrationBackup(unittest.TestCase):
    def tearDown(self):
        e2fake.uninstall()

    def test_version1_settings_are_backed_up_before_the_migration(self):
        env = e2fake.install("openatv", {"chime": "true", "foscam_poll": "false", "server": "http://192.168.1.10:1984"})
        io = __import__("CamAlert.settingsio", fromlist=["x"])
        last = io.backups().latest()
        self.assertEqual(last["reason"], "migration")
        with open(last["path"]) as f:
            doc = json.load(f)
        self.assertEqual((doc["schema_version"], doc["settings"]["foscam_poll"]), (1, "false"))
        self.assertEqual(env.config.plugins.camalert.chime.value, "high")

    def test_no_backup_without_a_migration(self):
        e2fake.install("openatv", {"foscam_enabled": "true"})
        io = __import__("CamAlert.settingsio", fromlist=["x"])
        self.assertIsNone(io.backups().latest())


if __name__ == "__main__":
    unittest.main()
