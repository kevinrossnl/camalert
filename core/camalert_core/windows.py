# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Several photo windows at the same time, each with its own id (#87).

A request without an id uses the normal window (id ""), exactly as before; it always keeps the corner (place 0). A
request with an id opens a window of its own: the same id again extends or replaces that window in its place; a new
id takes the next free place 1..max_windows-1 (window_geometry slot); when all are taken, the oldest id window of
the lowest priority makes room. The normal window never has to give way.
"""
import re

MAX_WINDOWS = (1, 3)       # the setting max_windows: 1 = the old behaviour (one window for every id)
DEFAULT_MAX_WINDOWS = 2
WINDOW_ID = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
RANK = {"low": 0, "normal": 1, "high": 2, "alarm": 3}


def window_id_param(value):
    """None (no id), or a valid window id; ValueError otherwise."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if not WINDOW_ID.match(text):
        raise ValueError("invalid window id")
    return text


def max_windows(value):
    """The setting max_windows as an int in 1..3 (the default for anything else)."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_WINDOWS
    return max(MAX_WINDOWS[0], min(MAX_WINDOWS[1], n))


class WindowSlots(object):
    """Which window id is in which place. Pure bookkeeping, the same on every player (Kotlin: Windows.kt)."""

    def __init__(self, limit=DEFAULT_MAX_WINDOWS):
        self.limit = max_windows(limit)
        self.open = {}      # id -> (slot, priority rank, sequence)
        self.seq = 0

    def place(self, wid, priority="normal"):
        """(slot, evicted id or None, existing) for a window `wid` that is about to be shown. With limit 1 there are
        no id windows: every id is the normal window."""
        wid = wid if (wid and self.limit > 1) else ""
        self.seq += 1
        rank = RANK.get(priority, 1)
        if wid in self.open:
            slot = self.open[wid][0]
            self.open[wid] = (slot, max(rank, self.open[wid][1]), self.seq)
            return slot, None, True
        evicted = None
        if not wid:
            slot = 0
        else:
            used = set(v[0] for k, v in self.open.items() if k)
            free = [s for s in range(1, self.limit) if s not in used]
            if free:
                slot = free[0]
            else:
                evicted = min((k for k in self.open if k), key=lambda k: (self.open[k][1], self.open[k][2]))
                slot = self.open.pop(evicted)[0]
        self.open[wid] = (slot, rank, self.seq)
        return slot, evicted, False

    def remove(self, wid):
        self.open.pop(wid or "", None)

    def clear(self):
        self.open.clear()

    def slot(self, wid):
        v = self.open.get(wid or "")
        return v[0] if v else None

    def ids(self):
        """Open ids, in the order of their places."""
        return [k for k, _v in sorted(self.open.items(), key=lambda kv: kv[1][0])]
