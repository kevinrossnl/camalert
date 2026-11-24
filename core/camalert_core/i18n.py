# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Translating texts that the core hands to the players (#41).

The core never translates itself: it marks its texts with N_() (English msgids, collected by
tools/strings.py into the Enigma2 po files and by tools/i18n/i18n.py into the Kodi strings.po with ids in
KODI_CORE_IDS) and every function that returns user-facing text takes `tr`, a callable msgid -> text:

    Enigma2:  tr = _                                         (the plugin's gettext function)
    Kodi:     tr = kodi_translator(xbmcaddon.Addon().getLocalizedString,
                                   kodi_ids(open(<add-on>/resources/language/resource.language.en_gb/strings.po).read()))
    tests:    tr = no_translation (English)
The master catalogue with all translations is core/i18n/ (not part of the packages).
"""
import re

KODI_CORE_IDS = (30500, 30700)  # [first, last): Kodi string ids of the core's N_() texts


def N_(text):
    """Marks a core text for translation (returns it unchanged)."""
    return text


def no_translation(text):
    return text


def kodi_ids(po_text):
    """{English msgid: Kodi string id} from the en_gb strings.po; for a text that has several ids, the one in
    KODI_CORE_IDS wins, else the lowest."""
    out = {}
    for m in re.finditer(r'msgctxt "#(\d+)"\s*\nmsgid "((?:[^"\\]|\\.)*)"', po_text):
        i = int(m.group(1))
        text = m.group(2).replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
        old = out.get(text)
        core = KODI_CORE_IDS[0] <= i < KODI_CORE_IDS[1]
        if old is None or (core and not KODI_CORE_IDS[0] <= old < KODI_CORE_IDS[1]) or \
                (core == (KODI_CORE_IDS[0] <= old < KODI_CORE_IDS[1]) and i < old):
            out[text] = i
    return out


def kodi_translator(get_string, ids):
    """tr(msgid) for Kodi: get_string(id) (Addon.getLocalizedString); the English msgid when the text has no id
    or Kodi returns nothing (strings not loaded yet)."""
    def tr(text):
        i = ids.get(text)
        if i is None:
            return text
        try:
            return get_string(i) or text
        except Exception:  # noqa: BLE001 - never break a screen over a translation
            return text
    return tr
