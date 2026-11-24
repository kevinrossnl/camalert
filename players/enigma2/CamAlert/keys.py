# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Enigma2 remote key codes (input event codes) and their names in the key map (camalert_core.keymap, #42).

The global key hooks get raw codes (they run before keymap.xml), so the codes are listed here once."""
from .camalert_core.keymap import COLOURS, action_for, colour_action, keys_for

CODES = {"OK": 352, "EXIT": 174, "LEFT": 105, "RIGHT": 106, "UP": 103, "DOWN": 108, "CHANNEL_UP": 402,
         "CHANNEL_DOWN": 403, "MUTE": 113, "VOLUME_DOWN": 114, "VOLUME_UP": 115,
         "RED": 398, "GREEN": 399, "YELLOW": 400, "BLUE": 401}
NAMES = {code: name for name, code in CODES.items()}
COLOR_KEYS = {CODES[c.upper()]: c for c in COLOURS}  # 398-401 -> red/green/yellow/blue
# ActionMap actions of the screens that use the image's keymap.xml (tour, mosaic)
ACTIONMAP = {"OK": ("OkCancelActions", "ok"), "EXIT": ("OkCancelActions", "cancel"),
             "LEFT": ("DirectionActions", "left"), "RIGHT": ("DirectionActions", "right"),
             "GREEN": ("ColorActions", "green"), "PLAY": ("MediaPlayerActions", "play")}
KEY_OK, KEY_EXIT, KEY_LEFT, KEY_RIGHT = CODES["OK"], CODES["EXIT"], CODES["LEFT"], CODES["RIGHT"]
KEY_UP, KEY_DOWN, KEY_CHANNELUP, KEY_CHANNELDOWN = CODES["UP"], CODES["DOWN"], CODES["CHANNEL_UP"], CODES["CHANNEL_DOWN"]
KEY_YELLOW = CODES["YELLOW"]
PASS_KEYS = {CODES[k] for k in ("MUTE", "VOLUME_DOWN", "VOLUME_UP")}


def key_action(code):
    """What a remote key does while the photo window is open: live / prev / next / close / pass / close_pass
    (close the window and let the key do its normal job: zapping, numbers, menu, ...)."""
    return action_for("enigma2", "window", NAMES.get(code)) or "close_pass"


def ptz_key(code):
    """What a remote key does in PTZ mode: up/down/left/right/zoom_in/zoom_out/home/leave/pass, None = ignored.
    The configured PTZ colour key also leaves PTZ mode (handled with button_for); other colour keys do not."""
    return action_for("enigma2", "ptz", NAMES.get(code))


def button_for(code, ptz_toggle="blue", has_ptz=False, enabled=True):
    """'ptz' | colour | None for a key code while a camera is on screen (see keymap.colour_action)."""
    return colour_action(COLOR_KEYS.get(code), ptz_toggle, has_ptz, enabled)


def actionmap(context, handlers):
    """{ActionMap context: {action: handler}} for a screen, from the key map; handlers = {logical action: fn}."""
    out = {}
    for action, fn in handlers.items():
        for key in keys_for("enigma2", context, action):
            ctx, name = ACTIONMAP[key]
            out.setdefault(ctx, {})[name] = fn
    return out


def action_map_args(context, handlers):
    """(contexts, actions) for Components.ActionMap.ActionMap(contexts, actions, prio)."""
    by_ctx = actionmap(context, handlers)
    actions = {}
    for acts in by_ctx.values():
        actions.update(acts)
    return sorted(by_ctx), actions


def actionmap_actions(context, handlers):
    """{ActionMap context: {action: (handler, logical action)}} from the key map, for HelpableActionMap."""
    out = {}
    for action, fn in handlers.items():
        for key in keys_for("enigma2", context, action):
            ctx, name = ACTIONMAP[key]
            out.setdefault(ctx, {})[name] = (fn, action)
    return out
