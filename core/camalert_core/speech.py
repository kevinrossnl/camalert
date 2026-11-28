# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Spoken announcement with a request (#89), the same on every player.

Home Assistant turns the text into speech (a TTS engine, WAV) and sends `say_url` (where the player fetches the
audio) and `say` (the text) along with /camalert/show. The players only play a WAV file next to the TV sound, like
the chime; the Android TV app can also speak the text itself (its own TextToSpeech) when there is no audio url.

Rules: the setting `speak` (off / high = doorbell and alarm / all), never for a test (#62) or the viewer's own key
(#13), and only when the request is shown (Do not disturb, active hours and the other rules already said no
otherwise). The audio url must point into the local network (an IP address in the LAN, the caller or a local
name; host names with dots are not resolved, so the check never blocks the GUI thread).
"""
from .access import url_target
from .events import is_test

SPEAK_CHOICES = ("off", "high", "all")
MAX_TEXT = 300           # characters of `say`
MAX_URL = 2048           # characters of `say_url`
MAX_AUDIO = 4 * 1024 * 1024  # bytes of the audio file a player downloads
FETCH_TIMEOUT = 10       # seconds


class SpeechError(ValueError):
    """`say` or `say_url` is wrong (400)."""


def speak_wanted(setting, priority):
    """The setting `speak`: 'off', 'high' (doorbell and alarm) or 'all' requests (same as the chime)."""
    return setting == "all" or (setting == "high" and priority in ("high", "alarm"))


def no_dns(_host):
    return []


def speech_request(args, caller_ip=None):
    """(url or None, text or None) from the request arguments `say_url` and `say`; SpeechError when invalid."""
    text = args.get("say")
    url = args.get("say_url")
    text = " ".join(str(text).split())[:MAX_TEXT] if text not in (None, "") else None
    if url in (None, ""):
        return None, text or None
    url = str(url).strip()
    if len(url) > MAX_URL:
        raise SpeechError("say_url is too long")
    why = url_target(url, caller_ip, no_dns)
    if why:
        raise SpeechError("say_url: " + why.replace("url host name does not resolve",
                                                     "use an IP address or a local name"))
    return url, text or None


def should_speak(setting, priority, source, result, url, text):
    """True when this request is spoken: something to say, the setting allows it, the request is shown, and it is
    not a test or the viewer's own key."""
    if not (url or text) or result not in ("show", "extend", "wake"):
        return False
    if is_test(source) or source == "menu":
        return False
    return speak_wanted(setting, priority or "normal")


def is_wav(data):
    """A RIFF/WAVE file (what the players can play next to the TV sound)."""
    return isinstance(data, (bytes, bytearray)) and len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def fetch_wav(url, opener=None, timeout=FETCH_TIMEOUT):
    """The WAV bytes at url (blocking: call in a thread). SpeechError when it is not a WAV file or too large."""
    if opener is None:
        from urllib.request import urlopen as opener
    with opener(url, timeout=timeout) as r:
        data = r.read(MAX_AUDIO + 1)
    if len(data) > MAX_AUDIO:
        raise SpeechError("audio file is too large")
    if not is_wav(data):
        raise SpeechError("audio is not a WAV file (ask Home Assistant for preferred_format wav)")
    return data
