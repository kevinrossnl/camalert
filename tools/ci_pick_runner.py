#!/usr/bin/env python3
"""Picks the Forgejo Actions runner for the CI jobs (#54).

The heavy CI jobs run on the workstation runner when it is online and fall back to the NAS runner (label
`truenas`) only when it is not: a burst of parallel jobs on the NAS overloads its disks. The fallback runs all
areas in one job, one after another ("sequential"), so the NAS never runs more than one CamAlert job at a time.

Usage in the workflow (job `pick-runner`), prints `runner=<label>` and `mode=parallel|sequential` lines that are
appended to $GITHUB_OUTPUT:

    python3 tools/ci_pick_runner.py >> "$GITHUB_OUTPUT"

Environment:
    FORCE_RUNNER         auto (default) | werkstation | truenas: `werkstation` uses the workstation even when the
                         API says it is busy or cannot be asked, `truenas` forces the fallback (to test it)
    RUNNER_STATUS_TOKEN  personal access token with scope read:user (repository secret); without it the API
                         cannot be asked and the fallback is used. The automatic workflow token cannot see runners.
    WORKSTATION_LABELS   preferred labels, best first (default "werkstation skills-werkstation"); keep the label
                         that this repository can always use last (`werkstation` itself is registered for
                         another repository today, so only `skills-werkstation` is visible here)
    FALLBACK_LABEL       default "truenas"
    GITHUB_SERVER_URL    Forgejo base URL (set by the runner)

Plain Python 3.8+, standard library only; never prints the token. Diagnostics go to stderr (job log).
"""
import json
import os
import sys
import urllib.request

DEFAULT_WORKSTATION = "werkstation skills-werkstation"
DEFAULT_FALLBACK = "truenas"
ONLINE = ("idle", "active")  # Forgejo runner status: offline | idle | active (busy)


def choose(runners, preferred, fallback=DEFAULT_FALLBACK, force="auto"):
    """Returns (label, mode, reason). `runners` is the JSON list of GET /user/actions/runners (or None when the
    API could not be asked). An idle workstation runner wins over a busy one; a busy one still wins over the
    fallback (its jobs queue there, which is still faster and keeps the NAS free)."""
    force = (force or "auto").strip().lower()
    if force == fallback or force == "truenas":
        return fallback, "sequential", "forced by force_runner=%s" % force
    if force == "werkstation":
        # the first preferred label that has a runner at all (any status); without a list the last one, which is
        # the label this repository can always use (the first ones may belong to other repositories)
        for label in preferred:
            if any(label in (r.get("labels") or []) for r in (runners or [])):
                return label, "parallel", "forced by force_runner=werkstation"
        return preferred[-1], "parallel", "forced by force_runner=werkstation (runner list unknown)"
    if force not in ("", "auto"):
        return fallback, "sequential", "unknown force_runner=%r, using the fallback" % force
    if runners is None:
        return fallback, "sequential", "runner status unknown (no RUNNER_STATUS_TOKEN or API error)"
    for wanted in ("idle", "active"):
        for label in preferred:
            for r in runners:
                if label in (r.get("labels") or []) and r.get("status") == wanted:
                    return label, "parallel", "runner %s (label %s) is %s" % (r.get("name"), label, wanted)
    seen = ", ".join("%s=%s" % (r.get("name"), r.get("status")) for r in runners) or "no runners"
    return fallback, "sequential", "no workstation runner online (%s)" % seen


def fetch_runners(server, token, timeout=5):
    """GET /api/v1/user/actions/runners (runners registered at user level = usable by every repository of the
    user). Returns the list, or None on any error (the reason goes to stderr)."""
    if not server or not token:
        return None
    req = urllib.request.Request(server.rstrip("/") + "/api/v1/user/actions/runners?limit=50",
                                 headers={"Authorization": "token " + token, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # HTTP error, timeout, bad JSON: fall back, never fail the pipeline here
        msg = getattr(exc, "code", None) or type(exc).__name__
        print("runner API not usable (%s)" % msg, file=sys.stderr)
        return None
    if not isinstance(data, list):
        print("runner API returned no list", file=sys.stderr)
        return None
    return data


def main(env=None, out=sys.stdout):
    env = os.environ if env is None else env
    preferred = (env.get("WORKSTATION_LABELS") or DEFAULT_WORKSTATION).split()
    fallback = env.get("FALLBACK_LABEL") or DEFAULT_FALLBACK
    force = env.get("FORCE_RUNNER") or "auto"
    runners = None
    if force.strip().lower() in ("", "auto", "werkstation"):
        runners = fetch_runners(env.get("GITHUB_SERVER_URL"), env.get("RUNNER_STATUS_TOKEN"))
    label, mode, reason = choose(runners, preferred, fallback, force)
    print("picked %s (%s): %s" % (label, mode, reason), file=sys.stderr)
    out.write("runner=%s\nmode=%s\n" % (label, mode))
    return 0


if __name__ == "__main__":
    sys.exit(main())
