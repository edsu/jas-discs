#!/usr/bin/env python3
"""
Extract all audio from a Tascam DAW backup disk image as a single WAV file.

Finds the audio start offset by detecting the end of the FAT region, then
writes everything from that point to end of file as a 24-bit mono WAV.

Usage:
    python3 extract_audio.py <backup.bin> [output.wav]
"""

import sys
import os
import wave

SAMPLE_RATE    = 44100
CHUNK_SAMPLES  = 4096
TASCAM_SIGS    = (b"dSNGMNG", b"SNGMNG")
FF_THRESHOLD   = 0.70
OTHER_THRESHOLD = 0.65
SUSTAIN_CHUNKS = 3
MIN_FAT_CHUNKS = 50
FAT_SCAN_CHUNK = 0x800


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
        ff_pct   = sum(1 for b in chunk if b == 0xFF) / len(chunk)
        zero_pct = sum(1 for b in chunk if b == 0x00) / len(chunk)
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


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <backup.bin> [output.wav]")
        sys.exit(1)

    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else src.replace(".bin", "_audio.wav")

    size = os.path.getsize(src)
    with open(src, "rb") as f:
        print("Finding audio offset...")
        audio_offset = find_audio_offset(f, size)
        if audio_offset is None:
            print("Error: could not find audio region")
            sys.exit(1)
        print(f"  Audio starts at 0x{audio_offset:08X} ({audio_offset})")

        num_bytes = size - audio_offset
        num_samples = num_bytes // 3
        duration = num_samples / SAMPLE_RATE

        print(f"  Audio length: {duration:.1f}s ({num_bytes // 1024 // 1024} MB)")
        print(f"Extracting to {dst} ...")

        f.seek(audio_offset)
        with wave.open(dst, "w") as w:
            w.setnchannels(1)
            w.setsampwidth(3)
            w.setframerate(SAMPLE_RATE)

            remaining = num_samples
            while remaining > 0:
                n = min(CHUNK_SAMPLES, remaining)
                raw = f.read(n * 3)
                if not raw:
                    break
                # WAV 24-bit is little-endian; input is big-endian — swap
                le = bytearray()
                for i in range(len(raw) // 3):
                    b = raw[i*3:(i+1)*3]
                    le += bytes([b[2], b[1], b[0]])
                w.writeframes(bytes(le))
                remaining -= n

        print("Done.")
