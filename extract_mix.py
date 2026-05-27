#!/usr/bin/env python3
"""
Extract the final mixed track from a Tascam DAW backup disk image.

Finds the audio start offset by detecting the end of the FAT region, then
scans for silence gaps to locate track boundaries and extracts the last track
(the stereo or mono mix) as a WAV file.

Usage:
    python3 extract_mix.py <backup.bin> [output.wav]

Options are tunable via constants below if silence detection needs adjustment.
"""

import sys
import os
import struct
import wave

SAMPLE_RATE    = 44100
CHUNK_SAMPLES  = 4096        # samples to read at a time during silence scan
SILENCE_THRESH = 500         # 24-bit amplitude threshold for "silence" (out of 8388607)
MIN_GAP_SECS   = 0.5         # minimum silence duration to count as a track boundary
TASCAM_SIG     = b"dSNGMNG"
FF_THRESHOLD   = 0.70
FAT_SCAN_CHUNK = 0x800


def find_audio_offset(f, size):
    f.seek(0)
    header = f.read(0x10000)
    if TASCAM_SIG not in header:
        print("Warning: Tascam signature (dSNGMNG) not found — may not be a Tascam backup")

    in_fat = False
    offset = 0
    while offset < size:
        f.seek(offset)
        chunk = f.read(FAT_SCAN_CHUNK)
        if not chunk:
            break
        ff_pct = sum(1 for b in chunk if b == 0xFF) / len(chunk)
        if ff_pct > FF_THRESHOLD:
            in_fat = True
        elif in_fat:
            return offset
        offset += FAT_SCAN_CHUNK
    return None


def read_samples(f, n):
    """Read n 24-bit big-endian signed samples, return as list of ints."""
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
    """Return list of (start_byte, end_byte) for each track, in file coordinates."""
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
                    # End of a track — record it, start new one after the gap
                    gap_start_byte = byte_pos - silence_run * 3
                    boundaries.append((track_start, gap_start_byte))
                    track_start = byte_pos
                silence_run = 0
            byte_pos += 3

    # Final track runs to end of file
    if byte_pos > track_start:
        boundaries.append((track_start, byte_pos))

    return boundaries


def write_wav(path, f, start_byte, end_byte, channels=1):
    num_samples = (end_byte - start_byte) // 3
    f.seek(start_byte)

    with wave.open(path, "w") as w:
        w.setnchannels(channels)
        w.setsampwidth(3)  # 24-bit = 3 bytes
        w.setframerate(SAMPLE_RATE)

        remaining = num_samples
        while remaining > 0:
            n = min(CHUNK_SAMPLES, remaining)
            raw = f.read(n * 3)
            if not raw:
                break
            # WAV 24-bit is little-endian; input is big-endian — swap bytes
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
        print(f"Usage: {sys.argv[0]} <backup.bin> [output.wav]")
        sys.exit(1)

    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else src.replace(".bin", "_mix.wav")

    size = os.path.getsize(src)
    with open(src, "rb") as f:
        print("Finding audio offset...")
        audio_offset = find_audio_offset(f, size)
        if audio_offset is None:
            print("Error: could not find audio region")
            sys.exit(1)
        print(f"  Audio starts at 0x{audio_offset:08X} ({audio_offset})")

        print("Scanning for track boundaries (this may take a moment)...")
        tracks = find_track_boundaries(f, audio_offset, size)

        print(f"\nFound {len(tracks)} track(s):")
        for i, (start, end) in enumerate(tracks):
            dur = seconds(end - start)
            label = "← mix" if i == len(tracks) - 1 else ""
            print(f"  Track {i+1}: 0x{start:08X}–0x{end:08X}  ({dur:.1f}s)  {label}")

        if not tracks:
            print("No tracks found — try lowering SILENCE_THRESH or MIN_GAP_SECS")
            sys.exit(1)

        mix_start, mix_end = tracks[-1]
        print(f"\nExtracting mix to {dst} ...")
        write_wav(dst, f, mix_start, mix_end)
        dur = seconds(mix_end - mix_start)
        print(f"  Done: {dur:.1f}s, {(mix_end - mix_start) // 1024} KB")
