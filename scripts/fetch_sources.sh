#!/usr/bin/env bash
# Download, verify and unpack all build inputs into sources/ (versions from sources.lock).
# Usage: scripts/fetch_sources.sh [--no-wiktionary]
# Run from anywhere; paths are relative to the repo root.
set -euo pipefail

cd "$(dirname "$0")/.."
# shellcheck source=../sources.lock
. ./sources.lock

WIKTIONARY=1
[ "${1:-}" = "--no-wiktionary" ] && WIKTIONARY=0

DL=downloads
SRC=sources
mkdir -p "$DL" "$SRC/freedict" "$SRC/verbiste" "$SRC/wikiextract"

sha256() { if command -v sha256sum >/dev/null; then sha256sum "$1"; else shasum -a 256 "$1"; fi | cut -d' ' -f1; }

# fetch <url> <file in downloads/> <expected sha256>; skips the download if the file is already valid
fetch() {
  local url=$1 file="$DL/$2" want=$3
  if [ ! -f "$file" ] || [ "$(sha256 "$file")" != "$want" ]; then
    echo "Downloading $2"
    curl -sfL -o "$file" "$url"
  fi
  if [ "$(sha256 "$file")" != "$want" ]; then
    echo "SHA-256 mismatch for $file (expected $want)" >&2
    exit 1
  fi
}

freedict() {  # freedict <pair> <sha256>
  local f="freedict-$1-$FREEDICT_VERSION.src.tar.xz"
  fetch "https://download.freedict.org/dictionaries/$1/$FREEDICT_VERSION/$f" "$f" "$2"
  tar xf "$DL/$f" --strip-components=1 -C "$SRC/freedict" "$1/$1.tei"
}

verbiste() {  # verbiste <file> <sha256>
  fetch "https://sources.debian.org/data/main/v/verbiste/$VERBISTE_VERSION/data/$1" "$1" "$2"
  cp "$DL/$1" "$SRC/verbiste/$1"
}

freedict fra-deu "$FREEDICT_FRA_DEU_SHA256"
freedict deu-fra "$FREEDICT_DEU_FRA_SHA256"
verbiste verbs-fr.xml "$VERBISTE_VERBS_SHA256"
verbiste conjugation-fr.xml "$VERBISTE_CONJUGATION_SHA256"

if [ "$WIKTIONARY" = 1 ]; then
  for l in fr de; do
    if [ ! -f "$DL/${l}_wiktextract.jsonl.gz" ]; then
      echo "Downloading ${l}_wiktextract.jsonl.gz from release $SOURCES_TAG"
      gh release download "$SOURCES_TAG" --pattern "${l}_wiktextract.jsonl.gz" --dir "$DL" || {
        echo "Release $SOURCES_TAG not found or not accessible (is it created? see README section D)." >&2
        echo "Either create it, or put ${l}_wiktextract.jsonl.gz into $DL/, or run 'make quick' (no Wiktextract)." >&2
        exit 1
      }
    fi
    gunzip -c "$DL/${l}_wiktextract.jsonl.gz" > "$SRC/wikiextract/${l}_raw-wiktextract-data.jsonl"
  done
fi

echo "Sources ready in $SRC/"
