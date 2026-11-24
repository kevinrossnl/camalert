# -*- coding: utf-8 -*-
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Temporary shim (#1): `logic` lives in core/camalert_core/ (copied into this package as camalert_core by the
build). This module *is* camalert_core.logic, so module state and monkeypatches are shared."""
import sys

from .camalert_core import logic as _core

sys.modules[__name__] = _core
