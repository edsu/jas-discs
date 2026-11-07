#!/bin/bash
# Extract (or re-extract) the audio for discs already in the bag, listen to
# each, and add the WAVs that sound like music to the manifest.
#
# For each disc: extract_audio.py writes the WAV to a temporary file,
# preview_wav.py and afplay play 3 clips from it, and you answer music or
# static. Music moves the WAV to data/NAME.wav and puts its MD5 in the
# manifest; static leaves the bag as it was (any older WAV is removed from
# data/, since it wasn't in the manifest) and lists the disc at the end.
#
# usage: ./extract.sh [NAME...]
#   With no names: every disc in the bag whose WAV isn't in the manifest yet.
#
# Tunables (override from the environment):
#   BAG              the bag directory                         (default backups)
#   PREVIEW_SECONDS  length of each of the three preview clips (default 10)

set -uo pipefail

root=$(cd "$(dirname "$0")" && pwd)
BAG=${BAG:-$root/backups}
PREVIEW_SECONDS=${PREVIEW_SECONDS:-10}

die() { echo "error: $*" >&2; exit 1; }

for tool in python3 afplay md5; do
  command -v "$tool" >/dev/null 2>&1 || die "$tool not found in PATH"
done
for f in extract_audio.py preview_wav.py; do
  [ -f "$root/$f" ] || die "$root/$f not found"
done
[ -t 0 ] || die "run this at a terminal; it asks you about each disc"
cd "$BAG" || die "could not enter $BAG"
manifest=manifest-md5.txt
[ -f "$manifest" ] || die "no $manifest in $BAG"

if [ $# -gt 0 ]; then
  names=("$@")
else
  names=()
  for b in data/*.bin; do
    n=$(basename "$b" .bin)
    grep -q "  data/$n.wav\$" "$manifest" || names+=("$n")
  done
fi
[ ${#names[@]} -gt 0 ] || { echo "every disc's WAV is already in the manifest"; exit 0; }

tmp=$(mktemp -d -t extract)
trap 'rm -rf "$tmp"' EXIT

music=(); static=(); skipped=()
i=0
for n in "${names[@]}"; do
  i=$((i + 1))
  echo
  echo "=== [$i/${#names[@]}] $n ==="
  if [ ! -s "data/$n.bin" ]; then
    echo "WARN: no data/$n.bin; skipping" >&2
    skipped+=("$n"); continue
  fi
  if ! python3 "$root/extract_audio.py" "data/$n.bin" "$tmp/$n.wav"; then
    echo "WARN: extraction failed; nothing changed for $n" >&2
    skipped+=("$n"); rm -f "$tmp/$n.wav"; continue
  fi
  python3 "$root/preview_wav.py" "$tmp/$n.wav" "$tmp/preview.wav" \
    --seconds "$PREVIEW_SECONDS" || { skipped+=("$n"); continue; }

  ans=
  while :; do
    echo "playing 3 x ${PREVIEW_SECONDS} s..."
    afplay -v 0.5 "$tmp/preview.wav"
    read -r -p "Music, static, replay, or skip? [m/s/r/k] " ans || { echo; ans=q; }
    case "$ans" in m*|M*|s*|S*|k*|K*|q) break ;; esac
  done

  case "$ans" in
    m*|M*)
      mv "$tmp/$n.wav" "data/$n.wav"
      f="data/$n.wav"
      awk -v f="$f" '{ p = $0; sub(/^[^ \t]+[ \t]+/, "", p) } p != f' \
        "$manifest" > "$manifest.tmp" && mv "$manifest.tmp" "$manifest"
      printf '%s  %s\n' "$(md5 -q "$f")" "$f" | tee -a "$manifest"
      music+=("$n") ;;
    s*|S*)
      # A WAV in data/ that isn't in the manifest makes the bag invalid.
      grep -q "  data/$n.wav\$" "$manifest" || rm -f "data/$n.wav"
      static+=("$n") ;;
    *)
      skipped+=("$n") ;;
  esac
  rm -f "$tmp/$n.wav" "$tmp/preview.wav"
  [ "$ans" = q ] && break
done

echo
echo "=== done ==="
echo "music, added to the manifest: ${#music[@]}"
[ ${#static[@]} -gt 0 ] && printf 'static, left out: %s\n' "${static[*]}"
[ ${#skipped[@]} -gt 0 ] && printf 'skipped: %s\n' "${skipped[*]}"
exit 0
