# -*- coding: utf-8 -*-
# CamAlert - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Settings export / import / undo on Enigma2 (#7); the file format, validation and backups are in
camalert_core.settingsfile. The export goes to a USB stick or hard disk when there is one (easy to copy to another
receiver), else to /home/root; import reads camalert-settings.json from the same places. Backups (always with
passwords, readable by root only) stay in /etc/enigma2/camalert-backups, which a full image backup includes."""
import os

from Components.config import config, configfile, ConfigClock

from .camalert_core import schema, settingsfile

PLATFORM = "enigma2"
FILE_NAME = "camalert-settings.json"
BACKUP_DIR = os.environ.get("CAMALERT_E2_BACKUP_DIR") or "/etc/enigma2/camalert-backups"  # tests: own folder
EXPORT_DIRS = ("/media/usb", "/media/hdd", "/home/root")


def _settings():
    c = config.plugins.camalert
    out = []
    for s in schema.for_platform(PLATFORM):
        cfg = getattr(c, s.key(PLATFORM), None)
        if cfg is not None:
            out.append((s, cfg))
    return out


def report_values():
    """{schema id: value} for the problem report (#132): like current(), keyed by the schema id."""
    out = {}
    for s, cfg in _settings():
        v = cfg.value
        if isinstance(cfg, ConfigClock):
            v = "%02d:%02d" % (int(v[0]), int(v[1]))
        out[s.id] = v
    return out


def image_info(path="/etc/image-version"):
    """{"model": ..., "image": ..., "python": ...} for the problem report (#132)."""
    import platform
    info = {}
    try:
        with open(path) as f:
            for line in f:
                k, _sep, v = line.strip().partition("=")
                info[k] = v
    except (IOError, OSError):
        pass
    out = {"python": platform.python_version()}
    if info.get("box_type") or info.get("machinebuild"):
        out["model"] = info.get("box_type") or info.get("machinebuild")
    if info.get("distro"):
        out["image"] = ("%s %s" % (info["distro"], info.get("imageversion", ""))).strip()
    return out


def current():
    """{key: value} of every setting this receiver has, in schema types (time as HH:MM)."""
    out = {}
    for s, cfg in _settings():
        v = cfg.value
        if isinstance(cfg, ConfigClock):
            v = "%02d:%02d" % (int(v[0]), int(v[1]))
        out[s.key(PLATFORM)] = v
    return out


def apply(values):
    """Sets and saves the settings in values ({key: value} from settingsfile.read); returns the changed keys."""
    changed = []
    before = current()
    for s, cfg in _settings():
        key = s.key(PLATFORM)
        if key not in values or values[key] == before.get(key):
            continue
        v = values[key]
        if isinstance(cfg, ConfigClock):
            h, m = str(v).split(":")
            cfg.value = [int(h), int(m)]
        elif s.type == "int":
            cfg.value = int(v)
        elif s.type == "bool":
            cfg.value = bool(v)
        else:
            cfg.value = str(v)
        cfg.save()
        changed.append(key)
    if changed:
        config.plugins.camalert.save()
        configfile.save()
    return changed


def player_name():
    try:
        from .mqtt import node_name
        return node_name()
    except Exception:
        return None


def backups():
    return settingsfile.Backups(BACKUP_DIR)


def export_dir():
    for d in EXPORT_DIRS:
        if os.path.isdir(d) and os.access(d, os.W_OK):
            return d
    return "/tmp"


def export(secrets=False, folder=None):
    """Writes camalert-settings.json and returns its path. With secrets: readable by root only."""
    path = os.path.join(folder or export_dir(), FILE_NAME)
    doc = settingsfile.export(current(), PLATFORM, secrets=secrets, player=player_name())
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600 if secrets else 0o644)
    with os.fdopen(fd, "w") as f:
        f.write(settingsfile.dumps(doc))
    os.rename(tmp, path)
    return path


def import_file():
    """The settings file to import (first of the export places), or None."""
    for d in EXPORT_DIRS + ("/tmp",):
        path = os.path.join(d, FILE_NAME)
        if os.path.isfile(path):
            return path
    return None


def do_import(path):
    """Backup of the current settings, then the file. Returns the report (+ 'backup'); BadFile if the file is
    not usable (then nothing changed)."""
    with open(path) as f:
        text = f.read()
    cur = current()
    new, report = settingsfile.read(text, PLATFORM, cur)  # BadFile before anything is written
    report["backup"] = backups().save(cur, PLATFORM, "import", player_name())
    apply(new)
    return report


def undo():
    """Back to the newest backup (the current settings are kept as a backup first). None without backups."""
    result = backups().rollback(PLATFORM, current(), player_name())
    if result is None:
        return None
    new, report, used = result
    apply(new)
    report["backup"] = used["path"]
    return report
