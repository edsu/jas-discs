#!/usr/bin/env python3
"""
Find the audio data offset in a Tascam DAW backup disk image.

Two format variants are handled:
  - Newer (e.g. 2488): large FAT region (>70% 0xFF bytes) followed directly by audio
  - Older variant: small FAT, then zeros, then audio detectable by sustained
    density of non-zero/non-FF bytes (>50% "other")

Audio is stored as 24-bit signed big-endian PCM at 44100 Hz, mono per track.
To import in Audacity: File -> Import -> Raw Data, with the offset printed here.
"""

import sys
import os

CHUNK = 0x800         # 2KB scan granularity
FF_THRESHOLD = 0.70   # above this = FAT region
OTHER_THRESHOLD = 0.65 # sustained above this = audio region
SUSTAIN_CHUNKS = 3    # consecutive chunks needed to confirm audio start
MIN_FAT_CHUNKS = 50   # minimum consecutive FAT chunks to count as the main FAT (~100KB)
TASCAM_SIGS = (b"dSNGMNG", b"SNGMNG")


def find_audio_offset(path):
    size = os.path.getsize(path)

    with open(path, "rb") as f:
        header = f.read(0x10000)
        if not any(sig in header for sig in TASCAM_SIGS):
            print("Warning: Tascam signature not found — may not be a Tascam backup")

        seen_fat = False
        fat_run = 0      # consecutive FAT chunks seen
        run = 0          # consecutive audio-density chunks
        offset = 0
        candidate = None

        while offset < size:
            f.seek(offset)
            chunk = f.read(CHUNK)
            if not chunk:
                break

            ff_pct    = sum(1 for b in chunk if b == 0xFF) / len(chunk)
            zero_pct  = sum(1 for b in chunk if b == 0x00) / len(chunk)
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
