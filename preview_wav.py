#!/usr/bin/env python3
"""
Write a short preview of a long WAV: several seconds from several points in
it, back to back, so you can hear whether it is music or static without
playing hours of audio.

Each clip starts at an evenly spaced point (25%, 50%, 75% for 3 clips), moved
forward past near-silence, since a recording of quiet tape hiss is hard to
tell from either.

usage: preview_wav.py INPUT.wav OUTPUT.wav [--clips 3] [--seconds 10]
"""

import argparse
import sys
import wave
from array import array

QUIET_DBFS = -40   # a second whose peak is below this counts as silence
SEARCH_SECONDS = 120


def peak(frames, width):
    """Peak level of little-endian PCM frames, as a fraction of full scale."""
    if width == 2:
        a = array("h", frames)
    else:
        buf = bytearray(len(frames) // 3 * 4)
        buf[1::4], buf[2::4], buf[3::4] = frames[0::3], frames[1::3], frames[2::3]
        a = array("i", bytes(buf))
    if sys.byteorder == "big":
        a.byteswap()
    full = 1 << (8 * a.itemsize - 1)
    return max(map(abs, a), default=0) / full


def first_sound(r, start, stop):
    """First 1-second step at or after start (and before stop) that isn't
    near-silent; start itself if there is none."""
    rate, width = r.getframerate(), r.getsampwidth()
    quiet = 10 ** (QUIET_DBFS / 20)
    for pos in range(start, stop, rate):
        r.setpos(pos)
        if peak(r.readframes(rate), width) >= quiet:
            return pos
    return start


def main():
    ap = argparse.ArgumentParser(description="Cut a short preview from a long WAV.")
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--clips", type=int, default=3)
    ap.add_argument("--seconds", type=float, default=10.0)
    args = ap.parse_args()

    with wave.open(args.src) as r, wave.open(args.dst, "w") as w:
        w.setparams(r.getparams())
        n, rate = r.getnframes(), r.getframerate()
        clip = min(int(args.seconds * rate), n // args.clips)
        for i in range(args.clips):
            target = n * (i + 1) // (args.clips + 1)
            stop = min(target + SEARCH_SECONDS * rate, n - clip)
            pos = first_sound(r, target, stop)
            print(f"  clip {i + 1}: {pos // rate // 60}:{pos // rate % 60:02d}")
            r.setpos(pos)
            w.writeframes(r.readframes(clip))


if __name__ == "__main__":
    main()
