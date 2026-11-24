#!/usr/bin/env python3
"""Safe end-to-end runner for real CamAlert players (#35). Docs: docs/dev/e2e.md.

    python3 tools/e2e/run.py --device <name>[,<name>] [--scenario show,mosaic] [--dry-run]
    python3 tools/e2e/run.py --restore last

Devices come from tools/e2e/devices.local.yaml (never in git; example: devices.example.yaml). Every precondition
must pass or the device is skipped: allowed hours, quiet devices only with --allow-quiet and never in their sleep
hours, not recording and no timer within 30 minutes, nobody watching (standby + --wake, Home Assistant, an
interactive confirmation or --nobody-watching <device>), for Kodi nothing playing. The runner mutes first and
verifies it, writes a state snapshot to reports/state/ before the first change, and restores in `finally`.
Reports: reports/<run>/ (git-ignored). Never on GitHub. Copyright (C) 2026 CamAlert developers, GPL v2.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from camalert_e2e import profiles  # noqa: E402
from camalert_e2e.runner import REPORTS, Runner, restore_last  # noqa: E402
from camalert_e2e.scenarios import CORE  # noqa: E402


def names(text):
    return [x.strip() for x in (text or "").split(",") if x.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--device", help="profile name(s), comma separated")
    ap.add_argument("--scenario", help="comma separated, default: the profile's list or %s" % ",".join(CORE))
    ap.add_argument("--dry-run", action="store_true", help="preconditions and snapshot only, change nothing")
    ap.add_argument("--restore", metavar="RUN", help="'last' (or a run id): undo a run that did not finish")
    ap.add_argument("--allow-quiet", action="store_true", help="allow quiet devices (never in their sleep hours)")
    ap.add_argument("--wake", action="store_true", help="wake receivers in standby (standby is restored)")
    ap.add_argument("--nobody-watching", default="", metavar="DEVICES",
                    help="a person confirmed that nobody watches these devices (non-interactive runs)")
    ap.add_argument("--profiles", default=profiles.LOCAL_FILE, help="profile file (default devices.local.yaml)")
    ap.add_argument("--reports", default=REPORTS, help="report folder (default reports/, git-ignored)")
    a = ap.parse_args(argv)
    try:
        devices, ha_cfg = profiles.load(a.profiles)
    except profiles.ProfileError as e:
        print("profile error: %s" % e)
        return 2
    if a.restore:
        problems = restore_last(devices, a.reports, which=a.restore)
        return 1 if problems else 0
    chosen = names(a.device)
    unknown = [n for n in chosen if n not in devices]
    if not chosen or unknown:
        print("choose --device from: %s" % ", ".join(sorted(devices)))
        return 2
    options = {"allow_quiet": a.allow_quiet, "wake": a.wake, "nobody_watching": names(a.nobody_watching),
               "dry_run": a.dry_run}
    code = 0
    for name in chosen:
        selected = names(a.scenario) or devices[name]["scenarios"] or list(CORE)
        bad = [s for s in selected if s not in CORE]
        if bad:
            print("unknown scenario(s): %s" % ", ".join(bad))
            return 2
        data = Runner({name: devices[name]}, ha_cfg, options, a.reports).run([name], selected)
        for d in data["devices"]:
            print("%s: %s %s" % (d["device"], d["status"], d.get("reason", "")))
            if d["status"] in ("failed", "error"):
                code = 1
        print("report: %s (privacy findings: %d)" % (os.path.join(a.reports, data["run"]), data["privacy_findings"]))
    return code


if __name__ == "__main__":
    sys.exit(main())
