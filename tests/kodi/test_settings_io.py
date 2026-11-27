"""Kodi: settings export / import / undo from the add-on menu, and a backup before a migration (#7)."""
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest

import _paths
from kodi import stubs as kodi_stubs


class TestKodiSettingsIO(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.profile = os.path.join(self.tmp, "profile")
        os.makedirs(self.profile)
        self.store = kodi_stubs.install(profile=self.profile, settings={
            "server": "http://192.168.1.10:1984", "token": "s3cret", "from_time": "06:30", "wizard_done": "true"})
        for name in [m for m in sys.modules if m == "camalert" or m.startswith("camalert.")]:
            del sys.modules[name]
        _paths.kodi_package()
        self.io = _paths.kodi_module("ksettingsio")
        self.script = _paths.kodi_module("script")
        self.gui = sys.modules["xbmcgui"]
        self.said = []
        self.answers = {}
        for meth in ("ok", "yesno", "select", "browse"):
            self.addCleanup(setattr, self.gui.Dialog, meth, getattr(self.gui.Dialog, meth))
        self.gui.Dialog.ok = lambda s, heading, message: self.said.append(message) or True
        self.gui.Dialog.yesno = lambda s, heading, message, *a, **kw: self.said.append(message) or \
            self.answers.get("yesno", True)
        self.gui.Dialog.select = lambda s, heading, items, *a, **kw: self.answers.get("select", 0)
        self.gui.Dialog.browse = lambda s, kind, heading, shares, mask="", *a, **kw: \
            self.answers["file"] if kind == 1 else self.tmp

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def file(self):
        return os.path.join(self.tmp, "camalert-settings.json")

    def test_menu_has_the_three_entries(self):
        labels = [label for label, _action in self.script.MENU]
        self.assertEqual(labels[-3:], [30780, 30781, 30782])

    def test_export_without_and_with_secrets(self):
        self.io.export_dialog()
        with open(self.file()) as f:
            doc = json.load(f)
        self.assertEqual((doc["platform"], doc["settings"]["server"], doc["settings"]["from_time"]),
                         ("kodi", "http://192.168.1.10:1984", "06:30"))
        self.assertNotIn("token", doc["settings"])
        self.assertIn("Settings saved in", self.said[-1])
        self.answers["select"] = 1
        self.io.export_dialog()
        with open(self.file()) as f:
            self.assertEqual(json.load(f)["settings"]["token"], "s3cret")

    def write(self, **settings):
        with open(self.file(), "w") as f:
            json.dump({"format": "camalert-settings", "schema_version": 2, "settings": settings}, f)
        self.answers["file"] = self.file()

    def test_import_asks_first_and_can_be_undone(self):
        self.write(server="http://192.168.1.11:1984", size="large", rtsp_port="no")
        self.answers["yesno"] = False
        self.io.import_dialog()
        self.assertEqual(self.store["server"], "http://192.168.1.10:1984")  # said no: nothing changed
        self.answers["yesno"] = True
        self.io.import_dialog()
        self.assertEqual((self.store["server"], self.store["size"], self.store["token"]),
                         ("http://192.168.1.11:1984", "large", "s3cret"))
        self.assertIn("2 settings changed.", self.said[-1])
        self.assertIn("rtsp_port", self.said[-1])
        backups = os.listdir(os.path.join(self.profile, "backups"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.profile, "backups", backups[0])).st_mode), 0o600)
        self.io.undo_dialog()
        self.assertEqual((self.store["server"], self.store["size"]), ("http://192.168.1.10:1984", "medium"))

    def test_bad_file_and_nothing_to_undo(self):
        with open(self.file(), "w") as f:
            f.write("{}")
        self.answers["file"] = self.file()
        self.io.import_dialog()
        self.assertIn("This file cannot be imported (not a settings file).", self.said[-1])
        self.assertFalse(os.path.exists(os.path.join(self.profile, "backups")))
        self.io.undo_dialog()
        self.assertEqual(self.said[-1], "There is no import to undo.")


class TestKodiMigrationBackup(unittest.TestCase):
    def test_version1_settings_are_backed_up_before_the_migration(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        profile = os.path.join(tmp, "profile")
        os.makedirs(profile)
        with open(os.path.join(profile, "settings.xml"), "w") as f:
            f.write('<settings version="2"><setting id="live_resume">false</setting>'
                    '<setting id="server">http://192.168.1.10:1984</setting></settings>')
        kodi_stubs.install(profile=profile)
        for name in [m for m in sys.modules if m == "camalert" or m.startswith("camalert.")]:
            del sys.modules[name]
        _paths.kodi_package()
        kodiapi = _paths.kodi_module("kodiapi")
        self.assertIn("live_return", kodiapi.migrate_settings())
        io = _paths.kodi_module("ksettingsio")
        last = io.backups().latest()
        self.assertEqual(last["reason"], "migration")
        with open(last["path"]) as f:
            doc = json.load(f)
        self.assertEqual((doc["schema_version"], doc["settings"]["live_resume"]), (1, "false"))


if __name__ == "__main__":
    unittest.main()
