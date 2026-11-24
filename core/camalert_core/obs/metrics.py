# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Prometheus text format."""


def metrics_text(m, labels=None):
    """Prometheus text format. m: {name: (type, help, value or {label_value: value})}."""
    extra = ",".join('%s="%s"' % (k, str(v).replace('"', "'")) for k, v in sorted((labels or {}).items()))
    out = []
    for name in sorted(m):
        kind, help_text, value = m[name]
        out.append("# HELP camalert_%s %s" % (name, help_text))
        out.append("# TYPE camalert_%s %s" % (name, kind))
        if isinstance(value, dict):
            for lv, v in sorted(value.items()):
                lab = ",".join(x for x in (extra, 'key="%s"' % str(lv).replace('"', "'")) if x)
                out.append("camalert_%s{%s} %s" % (name, lab, _num(v)))
        else:
            out.append("camalert_%s%s %s" % (name, "{%s}" % extra if extra else "", _num(value)))
    return "\n".join(out) + "\n"


def _num(v):
    return ("%d" % v) if isinstance(v, bool) or float(v).is_integer() else ("%.6g" % v)
