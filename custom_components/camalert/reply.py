"""Quick replies (#98): a colour key on the TV plays a prepared message on the doorbell's speaker.

None of the players has a usable microphone, so talking back from the TV itself is not possible. Instead the player's
options in Home Assistant map a colour key to a short text; when that key is pressed while a camera is on screen,
Home Assistant speaks the text with a TTS engine on a media player, usually the doorbell camera's speaker (UniFi
Protect: media_player.<camera>_speaker). Only signed key presses (#82) count, so nothing else on the network can
make the doorbell talk. The colour key's normal event (camalert_button) still fires for automations.
"""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from .const import BUTTONS
from .speech import tts_engine

_LOGGER = logging.getLogger(__name__)
CONF_REPLY_SPEAKER = "reply_speaker"
CONF_REPLY_TTS = "reply_tts"
CONF_REPLY = "reply_%s"  # reply_red, reply_green, reply_yellow, reply_blue
REPLY_MAX = 200
EVENT_REPLY = "camalert_reply"
# suggested texts in the options form (only active once a speaker is chosen)
SUGGESTED = {"red": "Please leave the parcel at the door.", "yellow": "I'm coming."}


def reply_text(options, button: str) -> str:
    """The reply for a colour key, '' when there is none or no speaker is chosen."""
    if button not in BUTTONS or not options.get(CONF_REPLY_SPEAKER):
        return ""
    return str(options.get(CONF_REPLY % button) or "").strip()[:REPLY_MAX]


async def async_play_reply(hass: HomeAssistant, entry, button: str, camera: str, verified: bool) -> bool:
    """Speaks the reply of `button` on the chosen speaker; False when there is nothing to do or it is refused."""
    text = reply_text(entry.options, button)
    if not text:
        return False
    if not verified:  # an unsigned press (older player) may not make the doorbell talk
        _LOGGER.warning("%s: reply on %s refused: the player does not sign its keys (update CamAlert)",
                        entry.title, button)
        return False
    engine = tts_engine(hass, entry.options.get(CONF_REPLY_TTS))
    speaker = entry.options[CONF_REPLY_SPEAKER]
    if not engine:
        _LOGGER.warning("%s: reply on %s: no TTS engine in Home Assistant", entry.title, button)
        return False
    try:
        await hass.services.async_call("tts", "speak", {"entity_id": engine, "media_player_entity_id": speaker,
                                                        "message": text, "cache": True}, blocking=True)
    except Exception as e:  # noqa: BLE001 - speaker offline, engine failed: log, never break the webhook
        _LOGGER.warning("%s: reply on %s could not be played on %s: %s", entry.title, button, speaker, e)
        return False
    hass.bus.async_fire(EVENT_REPLY, {"player": entry.title, "camera": camera, "button": button, "text": text,
                                      "speaker": speaker})
    return True
