#!/usr/bin/env python3
"""
Build the app dictionary as SQL database.

Usage (run from the repo root; defaults follow the layout in SETUP.md):
    python scripts/build_dictionary.py --pair fr-de
    python scripts/build_dictionary.py --pair de-fr

    --pair     <source-language>-<target-language>; the user searches in the source language.
    --sources  Directory containing freedict/<src3>-<tgt3>.tei (e.g. fra-deu.tei) and wikiextract/<src>_raw-wiktextract-data.jsonl
               (default: sources)
    --verbiste Directory containing verbs-fr.xml and conjugation-fr.xml (only for source language fr;
               German verbs are not conjugated; default: <sources>/verbiste)
    --out      Output database (default: dist/dictionary-<pair>.db)
    --limit    process only the first N FreeDict entries (for testing)
    --no-wiktionary  Skip the Wiktionary scan (scanning the JSONL files takes several minutes)
"""

import argparse
import io
import json
import re
import sqlite3
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import conjugation  # Verbiste parser from conjugation.py

TEI = "{http://www.tei-c.org/ns/1.0}"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"

KIND_LEMMA, KIND_VARIANT, KIND_INFLECTION = 0, 1, 2

# FreeDict pos -> normalized part of speech used by the app
POS_NORMALIZE = {"n": "noun", "pn": "proper_noun", "v": "verb"}

# normalized part of speech -> possible pos values in Wiktextract (if missing: any)
WIKT_POS = {
    "noun": {"noun"},
    "proper_noun": {"name", "noun"},
    "verb": {"verb"},
    "adj": {"adj"},
    "adv": {"adv"},
    "preposition": {"prep"},
    "interjection": {"intj"},
    "numeral": {"num"},
    "abbreviation": {"abbrev"},
}

GENDER_SHORT = {"masculine": "masc", "feminine": "fem", "neuter": "neut"}
GENDER_TAG = {"masc": "masculine", "fem": "feminine", "neut": "neuter"}
# Forms with these tags are not inflected forms of the lemma (diminutive, auxiliary verb, ...)
SKIP_FORM_TAGS = {"diminutive", "abbreviation", "auxiliary", "synonym"}
ISO3 = {"de": "deu", "fr": "fra"}  # FreeDict file names
LANG_AUDIO_PREFIX = {"de": "De", "fr": "Fr"}

AUX_RE = re.compile(r"\b(avoir|être)\b")
WORD_RE = re.compile(r'^\{"word": ("(?:[^"\\]|\\.)*")')


def fold(text: str) -> str:
    """Lowercase without accents:'Élève' -> 'eleve', 'Straße' -> 'strasse'."""
    text = text.lower().replace("ß", "ss").replace("œ", "oe").replace("æ", "ae")
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def norm(text: str) -> str:
    return unicodedata.normalize("NFC", text).strip().lower()


def strip_ipa(ipa: str) -> str:
    return ipa.strip().strip("[]/\\").strip()


# --------------------------------------------------------------------------- FreeDict

def parse_freedict(path: Path, limit: int | None) -> list[dict]:
    entries = []
    # fra-deu.tei contains an invalid "<>" in its header (<encodingDesc><>) -> remove it before parsing.
    data = io.BytesIO(path.read_bytes().replace(b"<>", b""))
    for _, el in ET.iterparse(data, events=("end",)):
        if el.tag != TEI + "entry":
            continue
        form = el.find(TEI + "form")
        orths = [o.text.strip() for o in form.iter(TEI + "orth") if o.text and o.text.strip()] \
            if form is not None else []
        if orths:
            gram = el.find(TEI + "gramGrp")
            pos_raw = (gram.findtext(TEI + "pos") or "").strip() if gram is not None else ""
            senses = []
            for sense in el.findall(TEI + "sense"):
                quotes = [q.text.strip() for cit in sense.findall(TEI + "cit")
                          if cit.get("type") == "trans"
                          for q in cit.findall(TEI + "quote") if q.text and q.text.strip()]
                defs = [d.text.strip() for d in sense.iter(TEI + "def") if d.text and d.text.strip()]
                if quotes or defs:
                    senses.append((quotes, defs))
            entries.append({
                "lemma": orths[0],
                "variants": orths[1:],
                "pos": POS_NORMALIZE.get(pos_raw, pos_raw or "unknown"),
                "gender": (gram.findtext(TEI + "gen") or "").strip() or None if gram is not None else None,
                "ipa": next((strip_ipa(p.text) for p in form.findall(TEI + "pron") if p.text and p.text.strip()), None),
                "senses": senses,
            })
        el.clear()
        if limit and len(entries) >= limit:
            break
    return entries


# --------------------------------------------------------------------------- Wiktionary

def compact_wiktionary(d: dict, word: str, lang: str) -> dict:
    """Reduce a Wiktextract entry to the fields the app dictionary needs."""
    forms = d.get("forms") or []

    plural = None
    for f in forms:
        tags = f.get("tags") or []
        form = (f.get("form") or "").strip()
        if "plural" in tags and form and " " not in form and not SKIP_FORM_TAGS & set(tags):
            if plural is None or "nominative" in tags:
                plural = form
                if "nominative" in tags:
                    break

    auxiliary = None
    for f in forms:
        tags = set(f.get("tags") or [])
        form = (f.get("form") or "").strip()
        if lang == "fr" and {"infinitive", "past"} <= tags:
            m = AUX_RE.search(form)                     # "avoir lu" -> avoir, "s’être tu" -> être
            if m:
                auxiliary = m.group(1)
                break
        if lang == "de" and {"auxiliary", "perfect"} <= tags and form:
            auxiliary = form                            # "haben" / "sein"
            break
    if lang == "fr" and auxiliary is None and any("pronominal" in (f.get("tags") or []) for f in forms):
        auxiliary = "être"                              # pronominal verbs form the perfect with être

    inflections = set()
    for f in forms if not (lang == "de" and d.get("pos") == "verb") else []:  # German verbs: out of scope
        tags = set(f.get("tags") or [])
        form = (f.get("form") or "").strip().rstrip("!")
        if form and " " not in form and not SKIP_FORM_TAGS & tags:
            inflections.add(form)

    audio_name = f"{LANG_AUDIO_PREFIX.get(lang, lang.capitalize())}-{word}.ogg".lower()
    ipa, audio, fallback = None, None, None
    for s in d.get("sounds") or []:
        if ipa is None and s.get("ipa"):
            ipa = strip_ipa(s["ipa"])
        if not s.get("mp3_url"):
            continue
        if audio is None and (s.get("audio") or "").lower() == audio_name:
            audio = s["mp3_url"]
        # Fallback: first recording, preferably from France
        if fallback is None or (not fallback[1] and any("France" in t for t in s.get("raw_tags") or [])):
            fallback = (s["mp3_url"], any("France" in t for t in s.get("raw_tags") or []))
    audio = audio or (fallback[0] if fallback else None)

    genders = set(d.get("tags") or [])
    for sense in d.get("senses") or []:
        genders |= set(sense.get("tags") or [])
    genders = [g for g in ("masculine", "feminine", "neuter") if g in genders]

    return {
        "tags": set(d.get("tags") or []),
        "genders": genders,
        "plural": plural,
        "auxiliary": auxiliary,
        "ipa": ipa,
        "audio": audio,
        "inflections": inflections,
    }


def scan_wiktionary(path: Path, lang: str, wanted: set[str]) -> dict:
    """Stream the JSONL file once and collect (word, pos) -> [entry, ...] for all wanted words."""
    found: dict[tuple[str, str], list[dict]] = {}
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            m = WORD_RE.match(line)
            if not m:
                continue
            word = json.loads(m.group(1))
            if word not in wanted:
                continue
            d = json.loads(line)
            if d.get("lang_code") != lang:
                continue
            found.setdefault((word, d.get("pos", "")), []).append(compact_wiktionary(d, word, lang))
            if n % 1_000_000 == 0:
                print(f"  ... {n:,} lines read", file=sys.stderr)
    return found


def wiktionary_candidates(found: dict, entry: dict) -> list[dict]:
    """All Wiktionary entries for a lemma and part of speech (Wiktionary splits homographs into several entries)."""
    allowed = WIKT_POS.get(entry["pos"])
    candidates = []
    for pos in (allowed or {p for (w, p) in found if w == entry["lemma"]}):
        candidates += found.get((entry["lemma"], pos), [])
    return candidates


def pick_wiktionary(candidates: list[dict], entry: dict) -> dict | None:
    if not candidates:
        return None
    gender_tag = GENDER_TAG.get(entry["gender"] or "")
    if gender_tag:
        for c in candidates:
            if gender_tag in c["tags"]:
                return c
    return candidates[0]


# --------------------------------------------------------------------------- Build

def build(args) -> None:
    src, tgt = args.pair.split("-")
    freedict = args.sources / "freedict" / f"{ISO3[src]}-{ISO3[tgt]}.tei"
    wikt = args.sources / "wikiextract" / f"{src}_raw-wiktextract-data.jsonl"
    use_verbiste = src == "fr"
    for p in [freedict] + ([] if args.no_wiktionary else [wikt]):
        if not p.exists():
            sys.exit(f"File not found: {p}")
    if use_verbiste:
        verbs_xml = args.verbiste / "verbs-fr.xml"
        conj_xml = args.verbiste / "conjugation-fr.xml"
        for p in (verbs_xml, conj_xml):
            if not p.exists():
                sys.exit(f"File not found: {p}")

    print(f"Reading FreeDict: {freedict}")
    entries = parse_freedict(freedict, args.limit)
    print(f"  {len(entries):,} entries")

    found = {}
    if not args.no_wiktionary:
        print(f"Scanning Wiktionary: {wikt}")
        found = scan_wiktionary(wikt, src, {e["lemma"] for e in entries})
        print(f"  {sum(len(v) for v in found.values()):,} matching entries")

    templates, verb_template = {}, {}
    if use_verbiste:
        templates = conjugation.parse_templates(conj_xml)
        verb_template = dict(conjugation.parse_verbs(verbs_xml))

    if args.out.exists():
        args.out.unlink()
    conn = sqlite3.connect(args.out)
    conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))

    stats = dict(total=0, no_wikt=0, noun_no_gender=0, verb=0, verb_no_template=0,
                 verb_no_aux=0, no_audio=0, gender_filled=0)
    used_templates = set()

    with conn:
        for e in entries:
            candidates = wiktionary_candidates(found, e) if found else []
            w = pick_wiktionary(candidates, e)
            template = stem = None
            verb_forms = set()
            if use_verbiste and e["pos"] == "verb":
                base = re.sub(r"^(se |s['’])", "", e["lemma"])
                tpl = verb_template.get(base)
                stem = conjugation.stem_of(base, tpl) if tpl else None
                if tpl and stem is not None and tpl in templates:
                    template = tpl
                    used_templates.add(tpl)
                    verb_forms = {stem + ending for *_, ending in templates[tpl]}
                else:
                    stem = None

            gender = e["gender"]
            if not gender and w and e["pos"] in ("noun", "proper_noun") and w["genders"]:
                gender = "/".join(GENDER_SHORT[g] for g in w["genders"])      # e.g. "masc/fem"
                stats["gender_filled"] += 1

            cur = conn.execute(
                "INSERT INTO entry (lemma, pos, gender, plural, ipa, audio_url, auxiliary, template, stem) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (e["lemma"], e["pos"], gender,
                 w["plural"] if w and e["pos"] in ("noun", "proper_noun") else None,
                 e["ipa"] or (w and w["ipa"]),
                 w and w["audio"],
                 w and w["auxiliary"] if e["pos"] == "verb" else None,
                 template, stem),
            )
            eid = cur.lastrowid

            lookup = {norm(e["lemma"]): KIND_LEMMA}
            for v in e["variants"]:
                lookup.setdefault(norm(v), KIND_VARIANT)
            for form in verb_forms | (w["inflections"] if w else set()) | ({w["plural"]} if w and e["pos"] in ("noun", "proper_noun") and w["plural"] else set()):
                lookup.setdefault(norm(form), KIND_INFLECTION)
            conn.executemany(
                "INSERT INTO lookup (term, term_fold, entry_id, kind) VALUES (?, ?, ?, ?)",
                [(t, fold(t), eid, k) for t, k in lookup.items()],
            )

            for pos_idx, (quotes, defs) in enumerate(e["senses"]):
                sid = conn.execute("INSERT INTO sense (entry_id, position) VALUES (?, ?)", (eid, pos_idx)).lastrowid
                conn.executemany("INSERT OR IGNORE INTO translation VALUES (?, ?, ?)",
                                 [(sid, i, q) for i, q in enumerate(quotes)])
                conn.executemany("INSERT OR IGNORE INTO definition VALUES (?, ?, ?)",
                                 [(sid, i, d) for i, d in enumerate(defs)])

            stats["total"] += 1
            stats["no_wikt"] += w is None
            if e["pos"] == "noun" and not gender:
                stats["noun_no_gender"] += 1
            if e["pos"] == "verb":
                stats["verb"] += 1
                stats["verb_no_aux"] += not (w and w["auxiliary"])
                stats["verb_no_template"] += use_verbiste and template is None
            stats["no_audio"] += not (w and w["audio"])

        for tpl in used_templates:
            conn.executemany(
                "INSERT OR IGNORE INTO conjugation_template VALUES (?, ?, ?, ?, ?, ?)",
                [(tpl, *row) for row in templates[tpl]],
            )

        conn.executemany("INSERT INTO meta VALUES (?, ?)", [
            ("source_lang", src), ("target_lang", tgt), ("schema_version", "1"),
            ("entries", str(stats["total"])),
        ])

    conn.execute("ANALYZE")
    conn.commit()
    conn.execute("VACUUM")
    conn.close()

    print(f"\n{args.out}  ({args.out.stat().st_size / 1e6:.1f} MB)")
    print("Data quality report:")
    print(f"  Entries total:                  {stats['total']:,}")
    print(f"  without Wiktionary match:       {stats['no_wikt']:,}")
    print(f"  Nouns without gender:           {stats['noun_no_gender']:,}")
    print(f"  Verbs:                          {stats['verb']:,}")
    print(f"  Verbs without auxiliary:        {stats['verb_no_aux']:,}")
    if use_verbiste:
        print(f"  Verbs without Verbiste tpl:     {stats['verb_no_template']:,}")
    print(f"  Entries without audio link:     {stats['no_audio']:,}")
    print(f"  Gender filled from Wiktionary:  {stats['gender_filled']:,}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pair", required=True, choices=["fr-de", "de-fr"])
    ap.add_argument("--sources", type=Path, default=Path("sources"))
    ap.add_argument("--verbiste", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--no-wiktionary", action="store_true")
    args = ap.parse_args()
    args.verbiste = args.verbiste or args.sources / "verbiste"
    args.out = args.out or Path("dist") / f"dictionary-{args.pair}.db"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    build(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
