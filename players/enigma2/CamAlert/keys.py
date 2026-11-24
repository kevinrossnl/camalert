# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Enigma2 remote key codes and what they do in the photo window and in PTZ mode."""


KEY_OK, KEY_EXIT, KEY_LEFT, KEY_RIGHT = 352, 174, 105, 106
PASS_KEYS = {113, 114, 115}  # mute, volume down, volume up: leave the window open


def key_action(code):
    """What a remote key does while the photo window is open: live / prev / next / close / pass / close_pass."""
    if code == KEY_OK:
        return "live"
    if code == KEY_LEFT:
        return "prev"
    if code == KEY_RIGHT:
        return "next"
    if code == KEY_EXIT:
        return "close"
    if code in PASS_KEYS:
        return "pass"
    return "close_pass"  # close the window and let the key do its normal job (zapping, numbers, menu, ...)


KEY_UP, KEY_DOWN, KEY_YELLOW, KEY_CHANNELUP, KEY_CHANNELDOWN = 103, 108, 400, 402, 403


def ptz_key(code):
    """What a remote key does in PTZ mode: up/down/left/right/zoom_in/zoom_out/home/leave, None = let it pass."""
    return {KEY_UP: "up", KEY_DOWN: "down", KEY_LEFT: "left", KEY_RIGHT: "right", KEY_CHANNELUP: "zoom_in",
            KEY_CHANNELDOWN: "zoom_out", KEY_OK: "home", KEY_EXIT: "leave", KEY_YELLOW: "leave"}.get(code)
