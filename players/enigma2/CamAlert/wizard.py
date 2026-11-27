# -*- coding: utf-8 -*-
# CamAlert - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""The first-start wizard (#120): find go2rtc, choose the default camera, a test, and how to add the receiver in
Home Assistant. The logic is camalert_core.wizard; this module only opens the standard Enigma2 dialogs (ChoiceBox,
MessageBox, VirtualKeyBoard). Every network call runs in a thread. Leaving the wizard at any point marks it done
(it does not open by itself again); the settings menu can start it again."""
import threading

from Components.config import config, configfile
from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Screens.VirtualKeyBoard import VirtualKeyBoard
from twisted.internet import threads

from . import _
from .camalert_core import wizard as core
from .camalert_core.events import TEST_SOURCE


def settings():
    c = config.plugins.camalert
    return {"wizard_done": bool(c.wizard_done.value), "source": c.source.value, "server": c.server.value,
            "mqtt_host": c.mqtt_host.value, "ha_webhook": c.ha_webhook.value}


def should_start():
    return core.should_start(settings())


def _save(values):
    c = config.plugins.camalert
    for key, value in values.items():
        getattr(c, key).value = value
        getattr(c, key).save()
    configfile.save()


def search(stop=None):
    """In a thread: every go2rtc in the network, [(server, cameras)]."""
    s = settings()
    return core.unique_servers(core.scan(core.candidates(core.own_ip(), core.ha_host(s)), stop=stop))


class Wizard(object):
    def __init__(self, session, on_close=None):
        self.session, self.on_close = session, on_close
        self.found, self.server, self.cameras, self.camera = [], None, [], None
        self.stop = threading.Event()
        self.searching = None
        self.finished = False

    # --- step 1: go2rtc ---------------------------------------------------------------------------------------------
    def start(self):
        self.searching = self.session.openWithCallback(self.search_closed, MessageBox,
                                                       _("Searching for go2rtc in your network..."), MessageBox.TYPE_INFO)
        threads.deferToThread(search, self.stop).addCallbacks(self.search_done, lambda err: self.search_done([]))

    def search_closed(self, *ret):
        if self.searching is not None:  # closed with OK / EXIT before the search ended: use what was found
            self.searching = None
            self.stop.set()

    def search_done(self, found):
        if self.searching is not None:
            box, self.searching = self.searching, None
            box.close()
        self.found = found or []
        self.choose_server()

    def choose_server(self):
        choices = [("%s (%s)" % (srv, _("%d cameras") % len(cams)), ("server", srv, cams)) for srv, cams in self.found]
        choices += [(_("Enter the address yourself"), ("manual",)), (_("Without go2rtc (camera file)"), ("direct",))]
        title = _("CamAlert wizard") if self.found else \
            _("No go2rtc found in your network. Enter its address yourself, or set up go2rtc first (see the guide).")
        self.session.openWithCallback(self.server_chosen, ChoiceBox, title=title, list=choices)

    def server_chosen(self, choice):
        if not choice:
            return self.finish()
        what = choice[1]
        if what[0] == "server":
            self.use_server(what[1], what[2])
        elif what[0] == "manual":
            self.session.openWithCallback(self.typed, VirtualKeyBoard, title=_("go2rtc address"),
                                          text=config.plugins.camalert.server.value or "http://")
        else:
            from .display import CAMERA_FILE
            self.finish(core.result(direct=True))
            self.session.open(MessageBox, _("Without go2rtc, list your cameras in %s, then open CamAlert again.")
                              % CAMERA_FILE, MessageBox.TYPE_INFO)

    def typed(self, text):
        if text is None:
            return self.choose_server()
        srv = core.server_from_input(text)
        if not srv:
            return self.no_answer(text)
        from .setup import fetch_streams
        threads.deferToThread(fetch_streams, srv).addCallbacks(lambda cams: self.use_server(srv, cams),
                                                              lambda err: self.no_answer(srv))

    def no_answer(self, srv):
        self.session.openWithCallback(lambda *a: self.choose_server(), MessageBox,
                                      _("go2rtc does not answer at %s.") % srv, MessageBox.TYPE_ERROR)

    # --- step 2: camera ---------------------------------------------------------------------------------------------
    def use_server(self, srv, cams):
        self.server, self.cameras = srv, list(cams or [])
        _save({"source": "go2rtc", "server": srv})  # the preview picture needs the address
        if not self.cameras:
            self.finish()
            self.session.open(MessageBox, _("go2rtc has no cameras yet. Add your cameras in go2rtc and start the "
                                            "wizard again from the menu."), MessageBox.TYPE_INFO)
            return
        self.choose_camera()

    def choose_camera(self):
        from .display import Controller
        ctl = Controller.instance
        if ctl is not None:
            import time
            ctl._names, ctl._names_at = list(self.cameras), time.time()  # the list the wizard just read
        current = config.plugins.camalert.camera.value
        choices = [(name, name) for name in self.cameras]
        selection = self.cameras.index(current) if current in self.cameras else 0
        self.session.openWithCallback(self.camera_chosen, ChoiceBox,
                                      title=_("Which camera should CamAlert show by default?"), list=choices,
                                      selection=selection)

    def camera_chosen(self, choice):
        if not choice:
            return self.finish()
        from .display import Controller
        self.camera = choice[1]
        if Controller.instance is not None:
            Controller.instance.show(self.camera, 15, "photo", "high", source=TEST_SOURCE)  # preview
        self.session.openWithCallback(self.camera_confirmed, MessageBox, _("Is this the right camera?"),
                                      MessageBox.TYPE_YESNO)

    def camera_confirmed(self, yes):
        from .display import Controller
        if Controller.instance is not None:
            Controller.instance.hide()
        if not yes:
            return self.choose_camera()
        _save({"camera": self.camera})
        self.session.openWithCallback(self.test_answered, MessageBox,
                                      _("Show a test notification now? It plays no doorbell chime."),
                                      MessageBox.TYPE_YESNO)

    # --- step 3: test, step 4: done ---------------------------------------------------------------------------------
    def test_answered(self, yes):
        from .display import Controller
        if yes and Controller.instance is not None:
            Controller.instance.show(self.camera, 10, "notify", "high", source=TEST_SOURCE)
        self.finish(core.result(self.server, self.camera))
        from .mqtt import node_name
        name, address = core.add_text(node_name(), core.own_ip(), config.plugins.camalert.http_port.value)
        self.session.open(MessageBox, "\n".join([
            _("Ready! Add this player in Home Assistant: Settings > Devices & services > Add integration > CamAlert."),
            _("Name: %s") % name, _("Address: %s") % address]), MessageBox.TYPE_INFO)

    def finish(self, values=None):
        """Saves what the wizard chose; wizard_done in any case, so it does not open by itself again."""
        if self.finished:
            return
        self.finished = True
        self.stop.set()
        _save(dict(values or {}, wizard_done=True))
        if self.on_close:
            self.on_close()
