# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Report a problem (#132) on Kodi: the add-on menu asks the running service for its report (its own API on this
device, GET /camalert/report), shows a summary and a QR code that opens a pre-filled GitHub issue on a phone, and
offers to save the full report (without secrets) in a folder the user picks."""
import json
import os
import ssl
import urllib.request

import xbmcgui

from . import kodiapi
from .camalert_core import qr, report
from .camalert_core.urls import valid_port


def fetch(s=None):
    """{"report": ..., "issue_url": ...} from the service on this device."""
    s = s or kodiapi.settings()
    https = bool(s.get("api_https"))
    url = "%s://127.0.0.1:%d/camalert/report" % ("https" if https else "http", valid_port(s.get("http_port"), 8099))
    req = urllib.request.Request(url, headers={"X-CamAlert-Token": s.get("token") or ""})
    ctx = ssl._create_unverified_context() if https else None  # our own self-signed certificate, on localhost
    with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
        return json.loads(r.read().decode("utf-8"))


class ReportWindow(xbmcgui.WindowDialog):
    """The summary on the left, the QR code on the right; BACK closes."""

    def __init__(self, lines, png):
        xbmcgui.WindowDialog.__init__(self)
        from .display import white
        self.addControl(xbmcgui.ControlImage(0, 0, 1280, 720, white(), colorDiffuse="F0101010"))
        box = xbmcgui.ControlTextBox(40, 40, 700, 640, textColor="FFFFFFFF")
        self.addControl(box)
        box.setText("\n".join(lines))
        self.addControl(xbmcgui.ControlImage(780, 110, 460, 460, png))

    def onAction(self, action):
        self.close()


def run():
    tr = kodiapi.core_tr()
    try:
        data = fetch()
    except Exception as e:  # the service is not running or the API is off
        xbmcgui.Dialog().ok("CamAlert", "%s\n%s" % (tr(report.TITLE), e))
        return
    rep, url = data["report"], data["issue_url"]
    png = os.path.join(kodiapi.temp_dir(), "report-qr.png")
    with open(png, "wb") as f:
        f.write(qr.png(qr.encode(url, "M"), scale=8, border=4))
    w = ReportWindow([tr(report.HELP), ""] + report.summary(rep), png)
    w.doModal()
    del w
    if not xbmcgui.Dialog().yesno("CamAlert", tr(report.SAVE) + "?"):
        return
    folder = xbmcgui.Dialog().browse(3, tr(report.SAVE), "files")
    if not folder:
        return
    from .ksettingsio import write
    path = os.path.join(folder, report.FILE_NAME) if "://" not in folder else folder.rstrip("/") + "/" + report.FILE_NAME
    try:
        write(path, report.text(rep))
    except (IOError, OSError) as e:
        xbmcgui.Dialog().ok("CamAlert", tr(report.SAVE_FAILED) % e)
        return
    xbmcgui.Dialog().ok("CamAlert", tr(report.SAVED) % path)
