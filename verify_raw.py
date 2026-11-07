#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy"]
# ///
"""
Check a raw (2352-byte sector) Mode 1 CD image made by rip.sh.

ddrescue's "100% rescued" only means every read returned without error; an
image read through the buffered /dev/disk device also scored 100% while a
fifth of its sectors were duplicates of others. So check the content:

  1. sync + address: every sector starts with the 12-byte sync pattern and
     its header address is its own position in the file
  2. EDC: the CRC each Mode 1 sector carries over its first 2064 bytes
     matches, so the sector is exactly what was written
  3. (optional) its 2048 bytes of user data match the same sector of the
     cdrdao .bin

An all-zero sector is one ddrescue could not read; it counts as missing,
not corrupt. Sectors past the end of the file are missing too.

usage: verify_raw.py IMAGE.raw [--bin IMAGE.bin] [--sectors N] [--min-pct P]

Exit status: 0 image good, 1 corrupt sectors or too many missing, 2 usage.
"""

import argparse
import sys

try:
    import numpy as np
except ImportError:
    sys.exit("verify_raw.py needs numpy; run it directly so uv provides it")

RAW = 2352
USER = 2048
SYNC = np.frombuffer(b"\x00" + b"\xff" * 10 + b"\x00", dtype=np.uint8)


def edc_table():
    # CD-ROM EDC: CRC-32, polynomial 0x8001801B, bit-reflected (0xD8018001),
    # zero initial value, no final XOR.
    table = np.zeros(256, dtype=np.uint32)
    for i in range(256):
        c = i
        for _ in range(8):
            c = (c >> 1) ^ (0xD8018001 if c & 1 else 0)
        table[i] = c
    return table


def edc(sectors):
    """EDC over bytes 0..2063 of each sector, all sectors at once."""
    table = edc_table()
    crc = np.zeros(len(sectors), dtype=np.uint32)
    for j in range(2064):
        crc = (crc >> 8) ^ table[(crc ^ sectors[:, j]) & 0xFF]
    return crc


def bcd(a):
    return (a >> 4) * 10 + (a & 0x0F)


def first(idx, k=5):
    return ", ".join(str(i) for i in idx[:k]) + (" ..." if len(idx) > k else "")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("image")
    ap.add_argument("--bin", help="cdrdao 2048-byte user-data image to compare")
    ap.add_argument("--sectors", type=int,
                    help="expected track length in sectors (default: file size)")
    ap.add_argument("--min-pct", type=float, default=99.0,
                    help="minimum share of expected sectors present and good")
    args = ap.parse_args()

    data = np.fromfile(args.image, dtype=np.uint8)
    n = len(data) // RAW
    if len(data) % RAW:
        print(f"WARN: {len(data) % RAW} trailing bytes ignored "
              f"(file is not whole {RAW}-byte sectors)")
    s = data[: n * RAW].reshape(n, RAW)
    expected = args.sectors if args.sectors else n

    unread = ~s.any(axis=1)
    present = ~unread
    pos = np.arange(n)

    nosync = present & ~(s[:, :12] == SYNC).all(axis=1)
    lba = (bcd(s[:, 12].astype(np.int64)) * 60 + bcd(s[:, 13].astype(np.int64))) * 75 \
        + bcd(s[:, 14].astype(np.int64)) - 150
    misplaced = present & ~nosync & ((lba != pos) | (s[:, 15] != 1))
    stored = s[:, 2064:2068].copy().view("<u4").ravel()
    badedc = present & ~nosync & ~misplaced & (edc(s) != stored)

    corrupt = nosync | misplaced | badedc
    good = int((present & ~corrupt).sum())
    missing = int(unread.sum()) + max(expected - n, 0)

    print(f"image:     {args.image}")
    print(f"sectors:   {n} in file, {expected} expected")
    print(f"good:      {good}")
    print(f"missing:   {missing}"
          + (f" (unread in file: {first(np.flatnonzero(unread))})" if unread.any() else "")
          + (f" ({expected - n} past end of file)" if expected > n else ""))
    for label, mask in (("no sync", nosync), ("misplaced", misplaced), ("bad EDC", badedc)):
        if mask.any():
            print(f"{label + ':':<10} {int(mask.sum())} at {first(np.flatnonzero(mask))}")

    if args.bin:
        b = np.fromfile(args.bin, dtype=np.uint8)
        m = min(len(b) // USER, n)
        ok = present[:m] & ~corrupt[:m]
        diff = ok & (s[:m, 16:16 + USER] != b[: m * USER].reshape(m, USER)).any(axis=1)
        print(f"vs .bin:   {int(ok.sum())} compared, {int(diff.sum())} differ"
              + (f" at {first(np.flatnonzero(diff))}" if diff.any() else ""))
        if diff.any():
            # The .raw sectors passed their own EDC, so the .bin is the suspect.
            print("WARN: .bin user data differs from EDC-verified .raw sectors")

    pct = 100.0 * good / expected if expected else 0.0
    if corrupt.any():
        print(f"FAIL: {int(corrupt.sum())} corrupt sectors")
        return 1
    if pct < args.min_pct:
        print(f"FAIL: only {pct:.2f}% of sectors good (need {args.min_pct:g}%)")
        return 1
    print(f"OK: {pct:.2f}% of sectors good")
    return 0


if __name__ == "__main__":
    sys.exit(main())
