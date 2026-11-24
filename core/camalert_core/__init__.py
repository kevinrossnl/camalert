# -*- coding: utf-8 -*-
# CamAlert core - shared, plain Python (3.8+) used by every player (Enigma2 plugin, Kodi add-on).
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Shared CamAlert code without any Enigma2, Twisted, Kodi or Home Assistant import.

The builds copy this whole package into each player package (`CamAlert/camalert_core/` in the ipk,
`resources/lib/camalert/camalert_core/` in the Kodi zip); inside the package all imports are relative.
"""
