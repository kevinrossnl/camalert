# -*- coding: utf-8 -*-
# CamAlert - show IP cameras on your TV.
# Copyright (C) 2026 CamAlert developers. Licensed under the GNU GPL v2 (see LICENSE).
"""Minimal MQTT 3.1.1 codec (QoS 0)."""


def _mqtt_len(n):
    out = bytearray()
    while True:
        b = n % 128
        n //= 128
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _mqtt_str(s):
    b = s.encode("utf-8") if isinstance(s, str) else s
    return len(b).to_bytes(2, "big") + b


def mqtt_connect(client_id, user=None, password=None, will_topic=None, will_payload=b"offline", keepalive=60):
    flags = 0x02  # clean session
    payload = _mqtt_str(client_id)
    if will_topic:
        flags |= 0x04 | 0x20  # will flag, will retain (QoS 0)
        payload += _mqtt_str(will_topic) + _mqtt_str(will_payload)
    if user:
        flags |= 0x80
        payload += _mqtt_str(user)
        if password:
            flags |= 0x40
            payload += _mqtt_str(password)
    var = _mqtt_str("MQTT") + bytes([4, flags]) + keepalive.to_bytes(2, "big")
    body = var + payload
    return bytes([0x10]) + _mqtt_len(len(body)) + body


def mqtt_publish(topic, payload, retain=False):
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    body = _mqtt_str(topic) + payload
    return bytes([0x30 | (1 if retain else 0)]) + _mqtt_len(len(body)) + body


def mqtt_subscribe(packet_id, topics):
    body = packet_id.to_bytes(2, "big") + b"".join(_mqtt_str(t) + b"\x00" for t in topics)
    return bytes([0x82]) + _mqtt_len(len(body)) + body


MQTT_PING = b"\xc0\x00"
MQTT_DISCONNECT = b"\xe0\x00"


def mqtt_split(buffer):
    """Splits a byte buffer into complete packets: returns ([(type, flags, body)], rest)."""
    packets, i = [], 0
    while True:
        if len(buffer) - i < 2:
            break
        mult, length, j = 1, 0, i + 1
        while True:
            if j >= len(buffer):
                return packets, buffer[i:]
            b = buffer[j]
            length += (b & 0x7F) * mult
            mult *= 128
            j += 1
            if not b & 0x80:
                break
        if len(buffer) - j < length:
            break
        packets.append((buffer[i] >> 4, buffer[i] & 0x0F, buffer[j:j + length]))
        i = j + length
    return packets, buffer[i:]


def mqtt_parse_publish(flags, body):
    """(topic, payload) of an incoming PUBLISH packet."""
    n = int.from_bytes(body[:2], "big")
    topic = body[2:2 + n].decode("utf-8", "replace")
    rest = body[2 + n:]
    if (flags >> 1) & 0x03:  # QoS > 0 has a packet id
        rest = rest[2:]
    return topic, rest
