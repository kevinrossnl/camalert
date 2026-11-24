# -*- coding: utf-8 -*-
# CamAlert - show IP cameras (via go2rtc) on an Enigma2 receiver.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""HELP key on CamAlert screens (#40): the image's HelpableScreen lists the keys of a screen with their meaning.
Images without Screens.HelpMenu get plain ActionMaps (the HELP key then does nothing)."""
from Components.ActionMap import ActionMap

try:
    from Screens.HelpMenu import HelpableScreen
    from Components.ActionMap import HelpableActionMap
except ImportError:  # pragma: no cover - every supported image has it
    HelpableScreen = HelpableActionMap = None

HelpBase = HelpableScreen if HelpableScreen is not None else object


def init_help(screen):
    """Call in the screen's __init__ after Screen.__init__ (the screen class inherits HelpBase)."""
    if HelpableScreen is not None:
        HelpableScreen.__init__(screen)


def help_actions(screen, name, context, actions, prio=0):
    """screen[name] = an action map for one keymap context; actions = {action: (function, help text)}.
    The help texts are shown by the HELP key."""
    if HelpableActionMap is not None:
        screen[name] = HelpableActionMap(screen, context, actions, prio)
    else:
        screen[name] = ActionMap([context], {a: v[0] for a, v in actions.items()}, prio)
    return screen[name]
