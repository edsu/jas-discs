#!/usr/bin/env python3
"""
Extract all tracks from a Tascam DAW backup disk image, including individual
tracks and the final mix (last track).

Finds the audio start offset by detecting the end of the FAT region, then
scans for silence gaps to locate track boundaries and writes each as a WAV file.

Usage:
    python3 extract_tracks.py <backup.bin> [output_dir]

Tune the constants below if silence detection needs adjustment.
"""

import sys
import os
import struct
import wave

SAMPLE_RATE    = 44100
CHUNK_SAMPLES  = 4096
SILENCE_THRESH = 500         # 24-bit amplitude threshold (out of 8388607)
MIN_GAP_SECS   = 0.5         # minimum silence to count as a track boundary
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


def read_samples(f, n):
    raw = f.read(n * 3)
    if not raw:
        return []
    count = len(raw) // 3
    samples = []
    for i in range(count):
        b = raw[i*3:(i+1)*3]
        val = struct.unpack(">I", b"\x00" + b)[0]
        if val >= 0x800000:
            val -= 0x1000000
        samples.append(val)
    return samples


def find_track_boundaries(f, audio_offset, size):
    min_gap_samples = int(MIN_GAP_SECS * SAMPLE_RATE)

    f.seek(audio_offset)
    boundaries = []
    track_start = audio_offset
    silence_run = 0
    byte_pos = audio_offset

    while byte_pos < size:
        samples = read_samples(f, CHUNK_SAMPLES)
        if not samples:
            break

        for s in samples:
            if abs(s) <= SILENCE_THRESH:
                silence_run += 1
            else:
                if silence_run >= min_gap_samples:
                    gap_start_byte = byte_pos - silence_run * 3
                    boundaries.append((track_start, gap_start_byte))
                    track_start = byte_pos
                silence_run = 0
            byte_pos += 3

    if byte_pos > track_start:
        boundaries.append((track_start, byte_pos))

    return boundaries


def write_wav(path, f, start_byte, end_byte):
    num_samples = (end_byte - start_byte) // 3
    f.seek(start_byte)

    with wave.open(path, "w") as w:
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


def seconds(byte_count):
    return byte_count / 3 / SAMPLE_RATE


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <backup.bin> [output_dir]")
        sys.exit(1)

    src = sys.argv[1]
    base = os.path.splitext(os.path.basename(src))[0]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(src)
    os.makedirs(out_dir, exist_ok=True)

    size = os.path.getsize(src)
    with open(src, "rb") as f:
        print("Finding audio offset...")
        audio_offset = find_audio_offset(f, size)
        if audio_offset is None:
            print("Error: could not find audio region")
            sys.exit(1)
        print(f"  Audio starts at 0x{audio_offset:08X} ({audio_offset})")

        audio_path = os.path.join(out_dir, f"{base}_audio.wav")
        print(f"Extracting full audio to {audio_path} ...")
        write_wav(audio_path, f, audio_offset, size - ((size - audio_offset) % 3))
        dur = seconds(size - audio_offset)
        print(f"  Done: {dur:.1f}s")

        print("Scanning for track boundaries (this may take a moment)...")
        tracks = find_track_boundaries(f, audio_offset, size)

        if not tracks:
            print("No tracks found — try lowering SILENCE_THRESH or MIN_GAP_SECS")
            sys.exit(1)

        total = len(tracks)
        print(f"\nFound {total} track(s):\n")

        for i, (start, end) in enumerate(tracks):
            dur = seconds(end - start)
            is_mix = (i == total - 1)
            label = "mix" if is_mix else f"track{i+1:02d}"
            filename = f"{base}_{label}.wav"
            path = os.path.join(out_dir, filename)

            tag = "← mix" if is_mix else ""
            print(f"  [{i+1}/{total}] {filename}  ({dur:.1f}s)  {tag}")
            write_wav(path, f, start, end)

        print(f"\nDone. Files written to: {out_dir}")
