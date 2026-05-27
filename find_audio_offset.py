#!/usr/bin/env python3
"""
Find the audio data offset in a Tascam DAW backup disk image.

The Tascam backup format stores a cluster allocation table (FAT) filled with
0xFF bytes before the raw audio data. This script finds where that table ends.

Audio is stored as 24-bit signed big-endian PCM at 44100 Hz, mono per track.
To import in Audacity: File -> Import -> Raw Data, with the offset printed here.
"""

import sys
import os

CHUNK = 0x800       # 2KB scan granularity
FF_THRESHOLD = 0.70 # above this = FAT region
TASCAM_SIG = b"dSNGMNG"


def find_audio_offset(path):
    size = os.path.getsize(path)

    with open(path, "rb") as f:
        # Confirm Tascam signature
        data = f.read(0x10000)
        if TASCAM_SIG not in data:
            print("Warning: Tascam signature (dSNGMNG) not found — may not be a Tascam backup")

        in_fat = False
        offset = 0

        while offset < size:
            f.seek(offset)
            chunk = f.read(CHUNK)
            if not chunk:
                break

            ff_pct = sum(1 for b in chunk if b == 0xFF) / len(chunk)

            if ff_pct > FF_THRESHOLD:
                in_fat = True
            elif in_fat:
                # First chunk after FAT with low FF density = audio start
                return offset

            offset += CHUNK

    return None


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <backup.bin>")
        sys.exit(1)

    path = sys.argv[1]
    offset = find_audio_offset(path)

    if offset is None:
        print("Could not find audio offset — FAT region not detected")
        sys.exit(1)

    print(f"Audio data starts at:")
    print(f"  decimal: {offset}")
    print(f"  hex:     0x{offset:08X}")
    print()
    print("Audacity import settings:")
    print("  File → Import → Raw Data")
    print(f"  Start offset: {offset}")
    print("  Encoding:     24-bit signed PCM")
    print("  Byte order:   Big-endian")
    print("  Sample rate:  44100 Hz")
    print("  Channels:     1 (mono — each track is stored separately)")
