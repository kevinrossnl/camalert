"""Preconditions per device. Any failure means the device is skipped, never forced (#3 section 3)."""
import sys

from .profiles import in_window

IDLE_STATES = ("off", "idle", "standby", "unavailable", "paused")


class Check(object):
    def __init__(self, name, ok, detail=""):
        self.name, self.ok, self.detail = name, ok, detail

    def as_dict(self):
        return {"name": self.name, "ok": self.ok, "detail": self.detail}

    def __repr__(self):
        return "Check(%r, %r, %r)" % (self.name, self.ok, self.detail)


def ask(question):
    """Interactive confirmation; only on a terminal (a scheduled run can never confirm)."""
    if not sys.stdin.isatty():
        return False
    try:
        return input(question + " [y/N] ").strip().lower() in ("y", "yes", "j", "ja")
    except EOFError:
        return False


def preconditions(profile, info, minute, options, ha=None, confirm=ask):
    """[Check] for one device. minute: minute of the local day. options: allow_quiet, wake, nobody_watching (names
    of devices a person confirmed nobody watches)."""
    name = profile["name"]
    out = [Check("allowed hours", in_window(profile["allowed"], minute), profile["allowed_hours"])]
    if profile["sleep"] is not None:
        out.append(Check("not in sleep hours", not in_window(profile["sleep"], minute), profile["sleep_hours"]))
    if profile["quiet"]:
        out.append(Check("quiet device allowed", bool(options.get("allow_quiet")),
                         "" if options.get("allow_quiet") else "quiet device: needs --allow-quiet"))
    out.append(Check("not recording", not info.get("recording")))
    out.append(Check("no timer within 30 min", not info.get("timer_soon"),
                     "%d timer(s)" % info["timer_soon"] if info.get("timer_soon") else ""))
    if profile["type"] == "kodi":
        out.append(Check("nothing playing", not info.get("playing"),
                         "%d active player(s)" % info["playing"] if info.get("playing") else ""))
        return out
    if info.get("standby"):
        out.append(Check("nobody watching", True, "receiver in standby"))
        out.append(Check("wake allowed", bool(options.get("wake")),
                         "" if options.get("wake") else "in standby: needs --wake (the TV may switch on via HDMI-CEC)"))
        return out
    out.append(Check("no menu or dialog on screen", not info.get("osd_busy"),
                     "the OSD shows something: someone may be using the receiver" if info.get("osd_busy") else ""))
    out.append(watching(profile, options, ha, confirm))
    return out


def watching(profile, options, ha, confirm):
    name = profile["name"]
    if name in (options.get("nobody_watching") or ()):
        return Check("nobody watching", True, "confirmed with --nobody-watching")
    if profile["watching"] == "ha":
        if ha is None:
            return Check("nobody watching", False, "Home Assistant token missing")
        try:
            state = ha.state(profile["ha_media_player"])
        except Exception as e:  # noqa: BLE001
            return Check("nobody watching", False, "Home Assistant: %s" % e.__class__.__name__)
        return Check("nobody watching", state in IDLE_STATES, "media player %s" % state)
    ok = confirm("Is nobody watching on %s right now?" % name)
    return Check("nobody watching", ok, "confirmed interactively" if ok else "not confirmed")
