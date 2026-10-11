#!/usr/bin/env python3
"""
Shrink a raw Wiktextract JSONL dump to the fields build_dictionary.py reads.

Usage:
    python prefilter_wiktextract.py --lang fr --input fr_raw-wiktextract-data.jsonl --output fr_wiktextract.jsonl.gz

Keeps only records with lang_code == --lang and only the fields used by
compact_wiktionary() in build_dictionary.py. "word" stays the first key, because
scan_wiktionary() matches it with WORD_RE (^{"word": "..."). The output is gzipped;
gunzip it to wikiextract/<lang>_raw-wiktextract-data.jsonl before running the build.
"""

import argparse
import gzip
import json
import sys
from pathlib import Path

SOUND_KEYS = ("ipa", "audio", "mp3_url", "raw_tags")


def reduce_record(d: dict) -> dict:
    out = {"word": d["word"], "lang_code": d["lang_code"], "pos": d.get("pos", "")}
    if d.get("tags"):
        out["tags"] = d["tags"]
    forms = [{k: f[k] for k in ("form", "tags") if f.get(k)} for f in d.get("forms") or []]
    if forms:
        out["forms"] = forms
    sounds = [{k: s[k] for k in SOUND_KEYS if s.get(k)} for s in d.get("sounds") or []]
    sounds = [s for s in sounds if s]
    if sounds:
        out["sounds"] = sounds
    senses = [{"tags": s["tags"]} for s in d.get("senses") or [] if s.get("tags")]
    if senses:
        out["senses"] = senses
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lang", required=True, choices=["fr", "de"])
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()

    read = kept = 0
    with open(args.input, encoding="utf-8") as src, \
         gzip.GzipFile(args.output, "wb", compresslevel=9, mtime=0) as raw:
        for read, line in enumerate(src, 1):
            d = json.loads(line)
            if d.get("lang_code") != args.lang or "word" not in d:
                continue
            raw.write((json.dumps(reduce_record(d), ensure_ascii=False) + "\n").encode("utf-8"))
            kept += 1
            if read % 1_000_000 == 0:
                print(f"  ... {read:,} lines read, {kept:,} kept", file=sys.stderr)

    print(f"{read:,} lines read, {kept:,} kept -> {args.output} ({args.output.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
