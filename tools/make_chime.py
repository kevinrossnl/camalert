#!/usr/bin/env python3
# Generates the doorbell chime (two soft bell tones, self-made, GPL v2 like the rest). Copyright (C) 2026 CamAlert developers.
import math
import os
import struct
import sys
import wave

RATE = 22050


def tone(freq, seconds, volume=0.45):
    out = []
    for i in range(int(RATE * seconds)):
        t = i / RATE
        env = math.exp(-3.2 * t) * min(1.0, t * 200)  # quick attack, bell-like decay
        s = sum(a * math.sin(2 * math.pi * freq * m * t) for m, a in ((1, 1.0), (2, 0.35), (3, 0.12)))
        out.append(int(32767 * volume * env * s / 1.47))
    return out


def build(path):
    samples = tone(659.25, 0.55) + tone(523.25, 0.9)  # E5 then C5: "ding-dong"
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(struct.pack("<%dh" % len(samples), *samples))
    return path


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "players", "enigma2", "CamAlert", "chime.wav")))
