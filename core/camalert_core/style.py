# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Accessibility and personal settings shared by every player (#48, #10).

Priority marking (#48): colours from the Okabe-Ito palette (safe for colour blindness) and never colour alone:
normal = no frame, high = orange frame + "Doorbell", alarm = vermillion frame + "ALARM". Text stays white on
#202020 (about 15:1). A flashing frame is opt-in and flashes at most FLASH_PER_SECOND times (WCAG 2.3.1: at most 3).

Presets (#48): a preset sets ordinary settings of the shared schema, it is no separate code path.

Languages (#10): "system" follows the receiver / Kodi / Android language; otherwise CamAlert uses its own texts in
that language whatever the system language is.
"""
from .i18n import N_

BORDER_MODES = ("off", "steady", "flash")
PRIORITY_COLOURS = {"high": "#E69F00", "alarm": "#D55E00"}  # Okabe-Ito orange / vermillion
PRIORITY_MARKS = {"high": N_("Doorbell"), "alarm": N_("ALARM")}
TEXT_COLOUR, BACKGROUND = "#FFFFFF", "#202020"
FLASH_PER_SECOND = 1.0  # frame on/off cycles per second; WCAG 2.3.1 allows at most 3
FLASH_MS = int(500 / FLASH_PER_SECOND)  # time between two toggles


def priority_mark(priority, border="steady"):
    """{"colour", "label", "flash"} for a window with this priority, or None (normal priority, or border "off").
    The label (untranslated msgid) is always shown with the colour, so the colour is never the only signal."""
    if border not in ("steady", "flash") or priority not in PRIORITY_COLOURS:
        return None
    return {"colour": PRIORITY_COLOURS[priority], "label": PRIORITY_MARKS[priority], "flash": border == "flash"}


def marked_title(title, priority, border, tr):
    """The window title with the priority word in front: 'ALARM · Front door' (translated); unchanged when there
    is no mark."""
    mark = priority_mark(priority, border)
    if mark is None:
        return title
    word = tr(mark["label"])
    return "%s · %s" % (word, title) if title else word


def contrast(fg, bg):
    """WCAG contrast ratio of two #RRGGBB colours."""
    def lum(c):
        out = []
        for i in (1, 3, 5):
            v = int(c[i:i + 2], 16) / 255.0
            out.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
        return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]
    a, b = sorted((lum(fg), lum(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


# --- presets ------------------------------------------------------------------------------------------------------
PRESET_LABELS = {"simple": N_("Simple: large text, large window, 60 seconds")}
PRESETS = {
    # large text, large window, 60 s, camera control key off, chime for doorbell and alarm
    "simple": {"text_size": "xlarge", "size": "large", "duration": 60, "ptz_key": "off", "chime": "high"},
}


def preset_changes(name, current, keys=None):
    """{key: value} that a preset changes compared to the current settings; keys limits it to the settings this
    player has (a player without ptz_key skips it). Unknown preset: {}."""
    out = {}
    for k, v in PRESETS.get(name, {}).items():
        if keys is not None and k not in keys:
            continue
        if current.get(k) != v:
            out[k] = v
    return out


# --- language -----------------------------------------------------------------------------------------------------
LANGUAGES = ("system", "en", "nl", "de", "fr", "it", "pl")
SYSTEM_LANGUAGE = N_("System language")
# Each language in its own name, never translated: someone who cannot read the current language finds theirs.
LANGUAGE_NAMES = {"en": "English", "nl": "Nederlands", "de": "Deutsch", "fr": "Français", "it": "Italiano",
                  "pl": "Polski"}


def language_label(code, tr):
    return tr(SYSTEM_LANGUAGE) if code == "system" else LANGUAGE_NAMES.get(code, code)


def effective_language(setting, system):
    """The language CamAlert shows: the setting unless it is "system" (or unknown), else the system language
    ('nl', 'nl_NL', 'nl-NL' -> 'nl'); 'en' when nothing fits."""
    if setting in LANGUAGE_NAMES:
        return setting
    code = (system or "").replace("-", "_").split("_")[0].lower()
    return code if code in LANGUAGE_NAMES else "en"
