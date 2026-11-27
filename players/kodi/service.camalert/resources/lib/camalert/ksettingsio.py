# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Settings export / import / undo in Kodi (#7); the file format, validation and backups are in
camalert_core.settingsfile. Export and import use Kodi's file browser, so a USB stick or a network share works.
Backups (always with passwords) stay in the add-on data folder (backups/)."""
import os

import xbmcgui
import xbmcvfs

from . import kodiapi
from .camalert_core import settingsfile

PLATFORM = "kodi"
FILE_NAME = "camalert-settings.json"


def backups():
    return settingsfile.Backups(os.path.join(kodiapi.profile_dir(), "backups"))


def current():
    return kodiapi.settings()


def apply(values):
    """Writes the settings that changed (Kodi then tells the service, which applies them); returns their keys."""
    before = current()
    changed = [k for k in sorted(values) if k in before and values[k] != before[k]]
    for k in changed:
        kodiapi.set_setting(k, values[k])
    return changed


def player_name():
    try:
        from .mqtt import node_name
        return node_name()
    except Exception:
        return None


def write(path, text):
    f = xbmcvfs.File(path, "w")
    try:
        if not f.write(text.encode("utf-8")):
            raise IOError(path)
    finally:
        f.close()


def read(path):
    f = xbmcvfs.File(path)
    try:
        return f.read()
    finally:
        f.close()


def export(folder, secrets=False):
    path = os.path.join(folder, FILE_NAME) if "://" not in folder else folder.rstrip("/") + "/" + FILE_NAME
    write(path, settingsfile.dumps(settingsfile.export(current(), PLATFORM, secrets=secrets, player=player_name())))
    return path


def do_import(path):
    """Backup of the current settings, then the file. Returns the report (+ 'backup'); BadFile if unusable."""
    cur = current()
    new, report = settingsfile.read(read(path), PLATFORM, cur)
    report["backup"] = backups().save(cur, PLATFORM, "import", player_name())
    apply(new)
    return report


def undo():
    result = backups().rollback(PLATFORM, current(), player_name())
    if result is None:
        return None
    new, report, used = result
    apply(new)
    report["backup"] = used["path"]
    return report


# --- dialogs (menu entries) -------------------------------------------------------------------------------------------
def tr(sid):
    return kodiapi.tr(sid)


def replaced(report):
    text = tr(30790) % len(report["changed"])
    if report["problems"]:
        text += "[CR]" + tr(30791) % ", ".join(report["problems"])
    xbmcgui.Dialog().ok("CamAlert", text)


def export_dialog():
    i = xbmcgui.Dialog().select(tr(30780), [tr(30783), tr(30784)])
    if i < 0:
        return
    folder = xbmcgui.Dialog().browse(3, tr(30785), "files")
    if not folder:
        return
    try:
        path = export(folder, secrets=(i == 1))
    except (IOError, OSError) as e:
        xbmcgui.Dialog().ok("CamAlert", tr(30793) % e)
        return
    xbmcgui.Dialog().ok("CamAlert", tr(30787) % path)


def import_dialog():
    path = xbmcgui.Dialog().browse(1, tr(30786), "files", ".json")
    if not path or not xbmcgui.Dialog().yesno("CamAlert", tr(30788) % path):
        return
    try:
        report = do_import(path)
    except settingsfile.BadFile as e:
        xbmcgui.Dialog().ok("CamAlert", tr(30792) % kodiapi.core_tr()(str(e)))
        return
    except (IOError, OSError) as e:
        xbmcgui.Dialog().ok("CamAlert", tr(30794) % e)
        return
    replaced(report)


def undo_dialog():
    if backups().latest() is None:
        xbmcgui.Dialog().ok("CamAlert", tr(30795))
        return
    if xbmcgui.Dialog().yesno("CamAlert", tr(30789)):
        report = undo()
        if report is not None:
            replaced(report)
