#!/usr/bin/env python3
"""Render NEXO's original, deterministic 40-second electronic soundtrack.

All instruments are synthesized here: no samples, outside music, or dependencies.
Run: python tools/nexo-motion/scripts/audio.py
Output: tools/nexo-motion/public/audio.wav (48 kHz stereo, signed PCM16).
The composition and renderer may be reused and redistributed with this project.
"""

from array import array
from pathlib import Path
import math
import random
import struct
import wave


SAMPLE_RATE = 48_000
DURATION = 40.0
TAU = 2.0 * math.pi
FRAMES = round(SAMPLE_RATE * DURATION)
OUTPUT = Path(__file__).resolve().parents[1] / "public" / "audio.wav"
LEFT = array("f", [0.0]) * FRAMES
RIGHT = array("f", [0.0]) * FRAMES
RNG = random.Random(965)


def frequency(midi):
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def smooth(value):
    value = min(1.0, max(0.0, value))
    return value * value * (3.0 - 2.0 * value)


def bounds(start, duration):
    first = max(0, round(start * SAMPLE_RATE))
    last = min(FRAMES, round((start + duration) * SAMPLE_RATE))
    return first, last


def add_pad(start, duration, notes):
    """Slow stereo sine voices with restrained overtones and organic drift."""
    first, last = bounds(start, duration)
    for voice, note in enumerate(notes):
        hz = frequency(note)
        pan = [-0.52, 0.30, -0.14, 0.57][voice % 4]
        gain_l = math.sqrt((1.0 - pan) / 2.0)
        gain_r = math.sqrt((1.0 + pan) / 2.0)
        phase = voice * 0.71
        for index in range(first, last):
            t = index / SAMPLE_RATE - start
            envelope = smooth(t / 1.7) * smooth((duration - t) / 2.6)
            drift = 0.78 + 0.08 * math.sin(TAU * 0.13 * t + phase)
            fundamental = math.sin(TAU * hz * t + phase)
            shimmer = math.sin(TAU * hz * 1.0022 * t + phase + 0.25)
            overtone = math.sin(TAU * 2.0 * hz * t + phase)
            value = (fundamental * 0.61 + shimmer * 0.32 + overtone * 0.07)
            value *= 0.023 * envelope * drift
            LEFT[index] += value * gain_l
            RIGHT[index] += value * gain_r


def add_bass(start, midi, duration=0.43, gain=0.032):
    first, last = bounds(start, duration)
    hz = frequency(midi)
    for index in range(first, last):
        t = index / SAMPLE_RATE - start
        envelope = smooth(t / 0.018) * math.exp(-t * 5.0)
        envelope *= smooth((duration - t) / 0.07)
        value = gain * envelope * (
            math.sin(TAU * hz * t) + 0.12 * math.sin(TAU * hz * 2 * t)
        )
        LEFT[index] += value
        RIGHT[index] += value


def add_kick(start, gain=0.047):
    first, last = bounds(start, 0.20)
    for index in range(first, last):
        t = index / SAMPLE_RATE - start
        # Integral of the decaying frequency sweep avoids phase discontinuities.
        phase = TAU * (46.0 * t + 3.25 * (1.0 - math.exp(-t * 25)))
        envelope = smooth(t / 0.003) * math.exp(-t * 24)
        value = gain * envelope * math.sin(phase)
        LEFT[index] += value
        RIGHT[index] += value


def add_tick(start, pan, gain=0.008):
    first, last = bounds(start, 0.052)
    previous = 0.0
    gain_l = math.sqrt((1.0 - pan) / 2.0)
    gain_r = math.sqrt((1.0 + pan) / 2.0)
    for index in range(first, last):
        t = index / SAMPLE_RATE - start
        noise = RNG.uniform(-1.0, 1.0)
        high = noise - previous
        previous = noise
        value = gain * high * math.exp(-t * 110) * smooth(t / 0.001)
        LEFT[index] += value * gain_l
        RIGHT[index] += value * gain_r


def add_glint(start, midi, pan, gain=0.009):
    first, last = bounds(start, 1.10)
    hz = frequency(midi)
    gain_l = math.sqrt((1.0 - pan) / 2.0)
    gain_r = math.sqrt((1.0 + pan) / 2.0)
    for index in range(first, last):
        t = index / SAMPLE_RATE - start
        envelope = smooth(t / 0.012) * math.exp(-t * 5.0)
        value = gain * envelope * (
            math.sin(TAU * hz * t) + 0.13 * math.sin(TAU * hz * 3.0 * t)
        )
        LEFT[index] += value * gain_l
        RIGHT[index] += value * gain_r


def add_whoosh(transition):
    """Soft stereo air crest, then a small low impact, at each scene change."""
    start = transition - 0.72
    duration = 1.20
    first, last = bounds(start, duration)
    filtered_l = 0.0
    filtered_r = 0.0
    for index in range(first, last):
        t = index / SAMPLE_RATE - start
        progress = t / duration
        envelope = math.sin(math.pi * progress) ** 2
        crest = 0.3 + 0.7 * math.exp(-((t - 0.68) / 0.32) ** 2)
        alpha = 0.025 + 0.24 * math.sin(math.pi * progress) ** 2
        filtered_l += alpha * (RNG.uniform(-1.0, 1.0) - filtered_l)
        filtered_r += alpha * (RNG.uniform(-1.0, 1.0) - filtered_r)
        LEFT[index] += 0.037 * filtered_l * envelope * crest
        RIGHT[index] += 0.037 * filtered_r * envelope * crest
    add_kick(transition, gain=0.073)
    add_glint(transition + 0.04, 81, 0.30, gain=0.006)


def compose():
    # D minor add9 / B-flat major7 / F major add9 / C add9.
    # Chord overlap keeps the texture continuous as the edit changes scenes.
    chords = [
        (0.0, 12.0, [50, 57, 65, 76]),
        (9.3, 12.6, [46, 57, 62, 65]),
        (19.3, 12.6, [53, 60, 67, 69]),
        (29.3, 10.7, [48, 55, 62, 64]),
    ]
    for start, duration, notes in chords:
        add_pad(start, duration, notes)

    roots = [38, 34, 41, 36]
    for beat in range(78):
        start = 0.5 + beat * 0.5
        if start > 38.0:
            break
        root = roots[min(3, int(start // 10))]
        gain = 0.027 if beat % 4 else 0.037
        add_bass(start, root, gain=gain)
        if beat % 2 == 0:
            add_kick(start, gain=0.038)
        add_tick(start + 0.25, -0.35 if beat % 2 else 0.35)
        if beat % 8 == 2:
            note = [74, 77, 79, 76][min(3, int(start // 10))]
            add_glint(start, note, -0.2 if beat % 16 else 0.3)

    for transition in [6.0, 13.0, 23.0, 33.0]:
        add_whoosh(transition)

    # Final restrained resolution is followed by sufficient tail and fade.
    add_glint(36.0, 72, -0.20, gain=0.008)
    add_glint(36.5, 79, 0.25, gain=0.005)


def render():
    compose()
    peak = 0.0
    for index in range(FRAMES):
        t = index / SAMPLE_RATE
        fade = smooth(t / 0.75) * smooth((DURATION - t) / 1.8)
        LEFT[index] *= fade
        RIGHT[index] *= fade
        peak = max(peak, abs(LEFT[index]), abs(RIGHT[index]))
    # A conservative fixed ceiling leaves headroom for platform encoding.
    gain = 0.58 / peak if peak else 1.0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUTPUT), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        for first in range(0, FRAMES, 8192):
            last = min(FRAMES, first + 8192)
            pcm = bytearray((last - first) * 4)
            for offset, index in enumerate(range(first, last)):
                struct.pack_into(
                    "<hh", pcm, offset * 4,
                    round(LEFT[index] * gain * 32767),
                    round(RIGHT[index] * gain * 32767),
                )
            output.writeframesraw(pcm)
    with wave.open(str(OUTPUT), "rb") as output:
        assert output.getnframes() == FRAMES
        assert output.getnchannels() == 2
        assert output.getsampwidth() == 2
        assert output.getframerate() == SAMPLE_RATE
        assert output.getnframes() / output.getframerate() == DURATION
    print(f"{OUTPUT}: {DURATION:.1f}s; stereo PCM16; {SAMPLE_RATE} Hz; peak 0.580")


if __name__ == "__main__":
    render()
