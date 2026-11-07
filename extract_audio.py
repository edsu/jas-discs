#!/usr/bin/env python3
"""
Extract all audio from a Tascam DAW backup disk image as a single WAV file.

Finds the audio start offset by detecting the end of the FAT region, then
works out how the samples are stored, and writes everything from there to the
end of the file as a mono WAV.

The audio is big-endian PCM at 44100 Hz, but discs differ: some are 16-bit and
some 24-bit, and on some the audio starts a byte or two after the offset the
FAT scan finds. Reading with the wrong width or alignment turns it into
static, so both are detected from the audio itself: real audio changes little
from one sample to the next, while misread audio changes as much as its own
size.

Usage:
    python3 extract_audio.py <backup.bin> [output.wav] [--bits 16|24] [--skip N]
"""

import argparse
import os
import sys
import wave
from array import array

SAMPLE_RATE    = 44100
TASCAM_SIGS    = (b"dSNGMNG", b"SNGMNG")
FF_THRESHOLD   = 0.70
OTHER_THRESHOLD = 0.65
SUSTAIN_CHUNKS = 3
MIN_FAT_CHUNKS = 50
FAT_SCAN_CHUNK = 0x800

PROBE_WINDOWS  = 20         # stretches of the disc sampled to detect the format
PROBE_BYTES    = 6 * 44100  # per stretch; a multiple of 6 keeps phases relative
AUDIO_RATIO    = 0.7        # smoothness score below this looks like audio
COPY_BYTES     = 6 * 2**20  # extraction chunk; a multiple of both widths


def find_audio_offset(f, size):
    f.seek(0)
    header = f.read(0x10000)
    if not any(sig in header for sig in TASCAM_SIGS):
        print("Warning: Tascam signature not found — may not be a Tascam backup")

    seen_fat = False
    fat_run = 0
    run = 0
    candidate = None
    offset = 0
    while offset < size:
        f.seek(offset)
        chunk = f.read(FAT_SCAN_CHUNK)
        if not chunk:
            break
        ff_pct   = chunk.count(0xFF) / len(chunk)
        zero_pct = chunk.count(0x00) / len(chunk)
        other_pct = 1.0 - ff_pct - zero_pct
        if ff_pct > FF_THRESHOLD:
            fat_run += 1
            if fat_run >= MIN_FAT_CHUNKS:
                seen_fat = True
            run = 0
            candidate = None
        elif seen_fat and other_pct > OTHER_THRESHOLD:
            if candidate is None:
                candidate = offset
            run += 1
            if run >= SUSTAIN_CHUNKS:
                return candidate
        else:
            fat_run = 0
            run = 0
            candidate = None
        offset += FAT_SCAN_CHUNK
    return None


def samples(raw, width):
    """Big-endian samples as ints (24-bit ones scaled by 256, which is fine
    for a ratio)."""
    n = len(raw) // width
    raw = raw[:n * width]
    if width == 2:
        a = array("h", raw)
    else:
        # Pad each 3-byte sample to a 4-byte big-endian int, low byte zero.
        buf = bytearray(n * 4)
        buf[0::4], buf[1::4], buf[2::4] = raw[0::3], raw[1::3], raw[2::3]
        a = array("i", bytes(buf))
    if sys.byteorder == "little":
        a.byteswap()
    return a


def smoothness(raw, width):
    v = samples(raw, width)
    level = sum(map(abs, v)) + 1
    change = sum(abs(b - a) for a, b in zip(v, v[1:]))
    return change / level


def detect_format(f, start, size):
    """Vote over stretches of the disc for the (width, phase) that looks like
    audio. Phase is bytes to skip after start."""
    votes = {}
    span = size - start - PROBE_BYTES - 6
    for i in range(PROBE_WINDOWS):
        pos = start + (span * i // PROBE_WINDOWS) // 6 * 6
        f.seek(pos)
        raw = f.read(PROBE_BYTES + 6)
        if (raw.count(0) + raw.count(0xFF)) > 0.6 * len(raw):
            continue  # silence or filesystem, says nothing
        score, width, phase = min(
            (smoothness(raw[p:p + PROBE_BYTES], w), w, p)
            for w in (2, 3) for p in range(w))
        if score < AUDIO_RATIO:
            votes[(width, phase)] = votes.get((width, phase), 0) + 1
    if not votes:
        return None, votes
    best = max(votes, key=votes.get)
    # Insist on a clear winner; a split vote means something unexpected.
    if votes[best] < 2 * (sum(votes.values()) - votes[best]) or votes[best] < 3:
        return None, votes
    return best, votes


def describe(votes):
    return ", ".join(f"{8 * w}-bit skip {p}: {n}" for (w, p), n in
                     sorted(votes.items(), key=lambda kv: -kv[1])) or "none"


def main():
    ap = argparse.ArgumentParser(description="Extract the audio from a Tascam backup image as one WAV.")
    ap.add_argument("src", help="cdrdao 2048-byte user-data image (.bin)")
    ap.add_argument("dst", nargs="?", help="output WAV (default: <src>_audio.wav)")
    ap.add_argument("--bits", type=int, choices=(16, 24),
                    help="sample width, instead of detecting it")
    ap.add_argument("--skip", type=int,
                    help="bytes to skip after the audio offset, instead of detecting it")
    args = ap.parse_args()

    src = args.src
    dst = args.dst or src.replace(".bin", "_audio.wav")

    size = os.path.getsize(src)
    with open(src, "rb") as f:
        print("Finding audio offset...")
        audio_offset = find_audio_offset(f, size)
        if audio_offset is None:
            print("Error: could not find audio region")
            sys.exit(1)
        print(f"  Audio starts at 0x{audio_offset:08X} ({audio_offset})")

        print("Detecting sample format...")
        found, votes = detect_format(f, audio_offset, size)
        print(f"  Votes: {describe(votes)}")
        width = args.bits // 8 if args.bits else (found[0] if found else None)
        skip = args.skip if args.skip is not None else (
            found[1] if found and found[0] == width else None)
        if width is None or skip is None:
            print("Error: could not tell how the samples are stored; "
                  "give --bits and --skip to say")
            sys.exit(1)
        print(f"  Using {8 * width}-bit big-endian, skipping {skip} byte(s)")

        start = audio_offset + skip
        num_samples = (size - start) // width
        duration = num_samples / SAMPLE_RATE

        print(f"  Audio length: {duration:.1f}s ({num_samples * width // 1024 // 1024} MB)")
        print(f"Extracting to {dst} ...")

        f.seek(start)
        with wave.open(dst, "w") as w:
            w.setnchannels(1)
            w.setsampwidth(width)
            w.setframerate(SAMPLE_RATE)

            remaining = num_samples * width
            while remaining > 0:
                raw = f.read(min(COPY_BYTES, remaining))
                if not raw:
                    break
                raw = raw[:len(raw) // width * width]
                # WAV is little-endian; the disc is big-endian — swap.
                le = bytearray(len(raw))
                for k in range(width):
                    le[k::width] = raw[width - 1 - k::width]
                w.writeframes(bytes(le))
                remaining -= len(raw)

        print("Done.")


if __name__ == "__main__":
    main()
