# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Settings as one file: export, import, backups and rollback (#7). The same on every player.

    export(values, platform)        -> the settings of a player as a dict (schema ids), secrets left out unless asked
    dumps(doc)                      -> that dict as JSON text (what the player writes to a file)
    read(text, platform, current)   -> (new values, report): validated against the schema; an older schema version is
                                       migrated first; what the file does not hold (and secrets it left out) stays
    Backups(folder)                 -> a copy of the settings before an import, a migration or a rollback; the
                                       newest few are kept, rollback() is read() of the newest

The file never holds internal settings (the wizard flag, the Home Assistant webhook, update checks): they belong
to this player. Secrets are the passwords and the API token; an export holds them only when asked (a backup on the
player itself always does, readable only by the player).
"""
import json
import os
import time

from . import schema
from .i18n import N_

FORMAT = "camalert-settings"
FORMAT_VERSION = 1
NOT_A_FILE = N_("not a settings file")
TOO_NEW = N_("made by a newer CamAlert")
SECRET_IDS = tuple(s.id for s in schema.SETTINGS if s.type == "password") + ("token",)


class BadFile(ValueError):
    """Not a CamAlert settings file, broken JSON, or made by a newer CamAlert (reason in str())."""


def _exported(platform):
    return [s for s in schema.for_platform(platform) if s.level != "internal"]


def export(values, platform, secrets=False, player=None, created=None):
    """values: {platform key: value} of one player. Settings it lacks get their default; secrets only if asked."""
    out = {}
    for s in _exported(platform):
        if s.id in SECRET_IDS and not secrets:
            continue
        value = values.get(s.key(platform), s.default_for(platform))
        try:
            out[s.id] = schema.coerce(s, value)
        except (TypeError, ValueError):
            out[s.id] = s.default_for(platform)
    doc = {"format": FORMAT, "format_version": FORMAT_VERSION, "schema_version": schema.SCHEMA_VERSION,
           "platform": platform, "created": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(created)),
           "secrets": bool(secrets), "settings": out}
    if player:
        doc["player"] = player
    return doc


def dumps(doc):
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False)


def parse(text):
    """The settings file as a dict, or BadFile."""
    try:
        doc = json.loads(text)
    except (TypeError, ValueError):
        raise BadFile(NOT_A_FILE)
    if not isinstance(doc, dict) or doc.get("format") != FORMAT or not isinstance(doc.get("settings"), dict):
        raise BadFile(NOT_A_FILE)
    version = doc.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise BadFile(NOT_A_FILE)
    if version > schema.SCHEMA_VERSION:
        raise BadFile(TOO_NEW)
    return doc


def read(text, platform, current):
    """(new values, report) for an import: current ({platform key: value}) with the file applied.

    A file of an older schema version is migrated first (schema.migrate). A setting the file does not hold keeps its
    current value, so a file without secrets keeps the passwords and token of this player. A broken value keeps the
    current one too and is reported. report: changed / problems (ids with a broken value) / skipped (settings of
    another player) / unknown (ids this CamAlert does not know) / secrets (the file held them)."""
    doc = parse(text)
    values = dict(doc["settings"])
    if doc["schema_version"] < schema.SCHEMA_VERSION:
        values = schema.migrate(values, platform)
    known = {s.id for s in schema.SETTINGS}
    mine = {s.id: s for s in _exported(platform)}
    new, report = dict(current), {"changed": [], "problems": [], "skipped": [], "unknown": [],
                                  "secrets": bool(doc.get("secrets"))}
    for sid in sorted(values):
        if sid not in known:
            report["unknown"].append(sid)
            continue
        s = mine.get(sid)
        if s is None:
            report["skipped"].append(sid)  # another player's setting, or internal
            continue
        try:
            value = schema.coerce(s, values[sid])
        except (TypeError, ValueError):
            report["problems"].append(sid)
            continue
        key = s.key(platform)
        try:
            before = schema.coerce(s, current[key])
        except (KeyError, TypeError, ValueError):
            before = None
        if before != value:
            report["changed"].append(sid)
        new[key] = value
    return new, report


class Backups(object):
    """Copies of the settings on the player itself, before an import, a migration or a rollback: always with
    secrets (the folder is the player's own; files are made readable by the owner only). keep = how many stay."""
    PREFIX = "settings-backup-"

    def __init__(self, folder, keep=5, clock=time.time):
        self.folder, self.keep, self.clock = folder, keep, clock

    def save(self, values, platform, reason, player=None, schema_version=None):
        """Writes a backup and returns its path; older ones beyond keep are removed. schema_version: the values
        are saved as they are (the player's own keys of that older version), e.g. before a migration; read()
        migrates them again when the backup is restored."""
        if not os.path.isdir(self.folder):
            os.makedirs(self.folder)
        now = self.clock()
        doc = export(values, platform, secrets=True, player=player, created=now)
        if schema_version is not None:
            doc["schema_version"] = schema_version
            doc["settings"] = {str(k): v for k, v in values.items()}
        doc["reason"] = reason
        base = os.path.join(self.folder, "%s%s" % (self.PREFIX, time.strftime("%Y%m%d-%H%M%S", time.localtime(now))))
        path, n = base + ".json", 1
        while os.path.exists(path):
            n += 1
            path = "%s-%d.json" % (base, n)
        tmp = path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(dumps(doc))
        os.rename(tmp, path)
        for old in self.list()[self.keep:]:
            try:
                os.remove(old["path"])
            except OSError:
                pass
        return path

    def list(self):
        """[{path, created, reason}] newest first; unreadable files are left out."""
        try:
            names = [n for n in os.listdir(self.folder) if n.startswith(self.PREFIX) and n.endswith(".json")]
        except OSError:
            return []
        out = []
        for name in names:
            path = os.path.join(self.folder, name)
            try:
                with open(path) as f:
                    doc = parse(f.read())
            except (OSError, BadFile):
                continue
            out.append({"path": path, "created": str(doc.get("created", "")), "reason": str(doc.get("reason", "")),
                        "mtime": os.path.getmtime(path)})
        out.sort(key=lambda b: (b["mtime"], b["path"]), reverse=True)
        return out

    def latest(self):
        items = self.list()
        return items[0] if items else None

    def rollback(self, platform, current, player=None):
        """(new values, report, backup) from the newest backup, after saving the current settings as a backup
        (so a rollback can be undone the same way); None when there is no backup."""
        last = self.latest()
        if last is None:
            return None
        with open(last["path"]) as f:
            text = f.read()
        new, report = read(text, platform, current)
        self.save(current, platform, "rollback", player)
        return new, report, last
