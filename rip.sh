#!/bin/bash
# Image a Tascam 788 backup CD two ways:
#   NAME.raw  - 2352-byte raw sectors via ddrescue (archival copy, error recovery)
#   NAME.bin  - 2048-byte user data via cdrdao
#   NAME.wav  - all the audio on the disc as one 24-bit mono WAV, from the
#               .bin via extract_audio.py (tracks are carved out by hand)
#
# Everything goes in a BagIt bag, backups/ next to this script unless BAG is
# given: the files in BAG/data/, their MD5s in BAG/manifest-md5.txt. The
# script stays outside the bag so the bag holds only the payload.
#
# On this drive the disc device returns whole raw sectors (sync, header,
# data, EDC/ECC), so the ddrescue image is a raw sector image, not an ISO.
#
# usage: ./rip.sh NAME DEVICE [BAG]
#   e.g. ./rip.sh exp_number_12 /dev/disk4
#
# Exit status:
#   0  ddrescue image usable
#   1  setup problem, no image made
#   2  ddrescue image failed
#
# Tunables (override from the environment):
#   MIN_PCT    minimum percentage of sectors verified good      (default 99)
#   SUDO       set to "sudo" if reading the device needs root   (default none)
#   PREVIEW    set to 0 to skip playing a sample of the WAV       (default 1)
#   PREVIEW_SECONDS  length of each of the three preview clips    (default 10)

set -uo pipefail

MIN_PCT=${MIN_PCT:-99}
SUDO=${SUDO:-}
PREVIEW=${PREVIEW:-1}
PREVIEW_SECONDS=${PREVIEW_SECONDS:-10}

name=${1:?usage: rip.sh NAME DEVICE [BAG]}
dev=${2:?usage: rip.sh NAME DEVICE [BAG]}
# Uncached device for ddrescue; see pass 1. Accepts /dev/diskN or /dev/rdiskN.
dev=/dev/${dev#/dev/}
dev=${dev/\/dev\/rdisk//dev/disk}
rdev=${dev/\/dev\/disk//dev/rdisk}

out=data/$name

die() { echo "error: $*" >&2; exit 1; }

for tool in ddrescue cdrdao diskutil python3; do
  command -v "$tool" >/dev/null 2>&1 || die "$tool not found in PATH"
done
root=$(cd "$(dirname "$0")" && pwd)
bag=${3:-$root/backups}
verify=$root/verify_raw.py
extract=$root/extract_audio.py
[ -x "$verify" ] || die "$verify not found (it lives next to rip.sh)"
[ -f "$extract" ] || die "$extract not found (it lives next to rip.sh)"
preview=$root/preview_wav.py
# verify_raw.py gets numpy through uv (see its header), not the system Python.
command -v uv >/dev/null 2>&1 || die "uv not found in PATH (verify_raw.py runs under uv)"

[ -e "$dev" ] || die "$dev does not exist. Check 'diskutil list' — the device
       number changes when a disc is ejected and reinserted."

# Take the size from diskutil's "Disk Size", which on these discs is the
# data track counted in 2352-byte raw sectors (it matched the TOC length
# exactly). Not asking cdrdao for the TOC saves a round of the drive being
# grabbed and released, which makes macOS remount the disc and show another
# "not readable" dialog.
size=$(diskutil info "$dev" 2>/dev/null |
       awk -F'[()]' '/Disk Size/ {print $2}' | awk '{print $1}')
case "$size" in
  ''|*[!0-9]*) die "could not determine disc size — is a disc loaded?" ;;
esac
# A size that isn't whole raw sectors means the assumption above is wrong for
# this disc; stop rather than image the wrong amount.
[ $(( size % 2352 )) -eq 0 ] || die "disc size $size is not a multiple of
       2352; check 'cdrdao read-toc' for the real track length."
sectors=$(( size / 2352 ))
[ "$sectors" -ge 512 ] || die "disc size $size is implausibly small."

echo "device:  $dev"
echo "track:   $sectors sectors ($size bytes raw)"
echo

raw_ok=0

# From here on, paths are relative to the bag, as the manifest wants them.
mkdir -p "$bag/data" || die "could not create $bag/data"
cd "$bag" || die "could not enter $bag"
echo "bag:     $bag"
echo
[ -f bagit.txt ] || printf 'BagIt-Version: 1.0\nTag-File-Character-Encoding: UTF-8\n' > bagit.txt

diskutil unmountDisk "$dev" >/dev/null 2>&1 || true

# --- pass 1: ddrescue, raw sectors ----------------------------------------
# Uncached /dev/rdisk, not /dev/disk: through the buffered device about a
# fifth of the sectors came back duplicated in place of others, while
# ddrescue reported every read as good. The raw device returns sectors in
# order, but only at the drive's 2352-byte block size (-b 2048 is rejected).
# Explicit -s because the size can't always be interrogated from the device.
# A non-zero exit here is common and does not by itself mean failure, and a
# zero exit does not mean the image is right, so verify_raw.py judges it
# after pass 2.
echo "=== ddrescue -> $out.raw ==="
$SUDO ddrescue -b 2352 -s "$size" -r3 -v "$rdev" "$out.raw" "$out.map"
rc=$?
[ $rc -ne 0 ] && echo "(ddrescue exited $rc — assessing the mapfile)"

if [ ! -s "$out.raw" ]; then
  echo "FAIL: $out.raw is missing or empty" >&2
  if [ ! -e "$rdev" ]; then
    echo "      $rdev disappeared — another process may have taken the drive." >&2
  elif [ ! -r "$rdev" ] && [ -z "$SUDO" ]; then
    echo "      $rdev is not readable; retry with: SUDO=sudo $0 $*" >&2
  else
    echo "      See the ddrescue error above." >&2
  fi
fi
echo

# --- pass 2: cdrdao, user data --------------------------------------------
# Best-effort 2048-byte user-data dump for brute-force audio extraction.
# Whatever comes out comes out; errors and short reads are expected and not
# checked.
echo "=== cdrdao -> $out.bin ==="
diskutil unmountDisk "$dev" >/dev/null 2>&1 || true
cdrdao read-cd --datafile "$out.bin" --driver generic-mmc-raw "$out.cue"

echo

# --- verify ----------------------------------------------------------------
# Sector-by-sector check of the .raw: sync, header address, EDC, and user
# data against the .bin.
if [ -s "$out.raw" ]; then
  echo "=== verify $out.raw ==="
  bin_arg=()
  [ -s "$out.bin" ] && bin_arg=(--bin "$out.bin")
  # ${a[@]+...} because macOS bash 3.2 calls an empty array unbound under -u.
  if "$verify" "$out.raw" ${bin_arg[@]+"${bin_arg[@]}"} \
       --sectors "$sectors" --min-pct "$MIN_PCT"; then
    raw_ok=1
  else
    echo "      Rerun with the same NAME to retry (the mapfile resumes), or" >&2
    echo "      try a different optical drive." >&2
  fi
  echo
fi

# --- audio -----------------------------------------------------------------
# Everything after the Tascam's FAT region as one WAV. A failure here doesn't
# fail the disc: the images are the archival copy, and the WAV can be remade
# from the .bin at any time.
if [ -s "$out.bin" ]; then
  echo "=== extract_audio -> $out.wav ==="
  if ! python3 "$extract" "$out.bin" "$out.wav"; then
    rm -f "$out.wav"  # don't leave a partial WAV in the bag
    echo "WARN: audio extraction failed; the images are unaffected" >&2
  fi
  echo
fi

# --- listen ----------------------------------------------------------------
# A misread sample width or alignment turns the whole WAV into static, which
# is quicker to hear than to measure. Play a clip from each of three points in
# it and ask. Only when someone is at the terminal; the answer goes in the log
# but doesn't fail the disc.
if [ "$PREVIEW" != 0 ] && [ -s "$out.wav" ] && [ -t 0 ] &&
   command -v afplay >/dev/null 2>&1 && [ -f "$preview" ]; then
  echo "=== listen to $out.wav ==="
  tmp=$(mktemp -d -t "$name.preview")
  clip=$tmp/preview.wav
  if python3 "$preview" "$out.wav" "$clip" --seconds "$PREVIEW_SECONDS"; then
    while :; do
      echo "playing 3 x ${PREVIEW_SECONDS} s from about 25%, 50% and 75% of the way through..."
      afplay -v 0.5 "$clip"
      read -r -p "Music, static, or replay? [m/s/r] " ans || { echo; break; }
      case "$ans" in
        m*|M*) echo "listened: sounds like music"; break ;;
        s*|S*) echo "WARN: listened: sounds like static. Try extract_audio.py" >&2
               echo "      with --bits 16 or 24 and --skip 0/1/2 by hand." >&2
               break ;;
        *) ;;
      esac
    done
  fi
  rm -rf "$tmp"
  echo
fi

# --- summary ---------------------------------------------------------------
echo "=== $name ==="
ls -l "$out.raw" "$out.bin" "$out.wav" 2>/dev/null

# BagIt payload manifest: "<md5>  data/<file>" for every file in data/. A
# rerun replaces this disc's lines rather than appending duplicates.
manifest=manifest-md5.txt
touch "$manifest"
for f in "$out.raw" "$out.map" "$out.bin" "$out.cue" "$out.wav"; do
  [ -f "$f" ] || continue
  sum=$(md5 -q "$f")
  awk -v f="$f" '{ p = $0; sub(/^[^ \t]+[ \t]+/, "", p) } p != f' \
    "$manifest" > "$manifest.tmp" && mv "$manifest.tmp" "$manifest"
  printf '%s  %s\n' "$sum" "$f" | tee -a "$manifest"
done
echo

# Only the ddrescue image decides pass/fail. The cdrdao .bin is a convenience
# input for brute-force extraction, so a short, odd-sized or missing one is
# not a problem worth stopping for.
if [ "$raw_ok" -eq 1 ]; then
  echo "Image OK. Eject with: drutil eject"
  exit 0
else
  echo "Imaging failed — see above. Try reseating the disc or another drive." >&2
  exit 2
fi
