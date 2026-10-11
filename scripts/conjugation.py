#!/usr/bin/env python3
"""
Uses Verbiste (verbs-fr.xml + conjugation-fr.xml) to compute all conjugations
of every verb and stores them in a SQLite database.

Usage:
    python verbiste_to_sqlite.py verbs-fr.xml conjugation-fr.xml conjugations.db

How it works:
    verbs-fr.xml:        <v><i>aberrer</i><t>aim:er</t></v>
    conjugation-fr.xml:  <template name="aim:er"> ... <p><i>e</i></p> ... </template>

    The template name has the form "<radical>:<ending>". The ending (here "er")
    is cut off the infinitive, leaving the verb stem ("aberr").
    Stem + the <i> ending from the template gives the conjugated form.

Database schema:
    verbs(id, infinitive, template)
    conjugations(id, verb_id, mood, tense, person, variant, form)

    person:  0-based index within the tense
             (6 persons: je, tu, il, nous, vous, ils; imperative: 3;
              past participle: 4 = m.sg, m.pl, f.sg, f.pl)
    variant: 0 = standard form, 1+ = alternative forms (e.g. "assied"/"assoit")
"""

import argparse
import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Readable labels for the person index of each tense.
PERSON_LABELS_6 = ["je", "tu", "il/elle", "nous", "vous", "ils/elles"]
PERSON_LABELS = {
    "imperative-present": ["tu", "nous", "vous"],
    "past-participle": ["masc. sg.", "masc. pl.", "fém. sg.", "fém. pl."],
}

SCHEMA = """
PRAGMA foreign_keys = ON;

DROP VIEW  IF EXISTS v_conjugations;
DROP TABLE IF EXISTS conjugations;
DROP TABLE IF EXISTS verbs;

CREATE TABLE verbs (
    id          INTEGER PRIMARY KEY,
    infinitive  TEXT NOT NULL UNIQUE,
    template    TEXT NOT NULL
);

CREATE TABLE conjugations (
    id        INTEGER PRIMARY KEY,
    verb_id   INTEGER NOT NULL REFERENCES verbs(id) ON DELETE CASCADE,
    mood      TEXT    NOT NULL,   -- e.g. indicative, subjunctive
    tense     TEXT    NOT NULL,   -- e.g. present, imperfect, future
    person    INTEGER NOT NULL,   -- 0-based index within the tense
    variant   INTEGER NOT NULL DEFAULT 0,
    form      TEXT    NOT NULL,
    UNIQUE (verb_id, mood, tense, person, variant)
);

CREATE INDEX idx_conj_verb ON conjugations(verb_id);
CREATE INDEX idx_conj_form ON conjugations(form);

-- Convenient view: query all conjugations of a word by its infinitive.
CREATE VIEW v_conjugations AS
SELECT v.infinitive, c.mood, c.tense, c.person, c.variant, c.form
FROM conjugations c
JOIN verbs v ON v.id = c.verb_id;
"""


def parse_templates(path: Path) -> dict:
    """
    Read conjugation-fr.xml and return, per template, a list of
    (mood, tense, person, variant, ending).
    """
    root = ET.parse(path).getroot()
    templates = {}

    for tpl in root.iter("template"):
        name = tpl.get("name")
        entries = []
        for mood in tpl:                       # infinitive, indicative, ...
            for tense in mood:                 # present, imperfect, ...
                for person_idx, p in enumerate(tense.findall("p")):
                    # Several <i> in one <p> = alternative forms.
                    # Empty/missing <i> (impersonal verbs) are skipped.
                    for variant, i in enumerate(p.findall("i")):
                        ending = (i.text or "").strip()
                        if ending:
                            entries.append(
                                (mood.tag, tense.tag, person_idx, variant, ending)
                            )
        templates[name] = entries
    return templates


def stem_of(infinitive: str, template: str) -> str | None:
    """
    Template "aim:er" -> ending "er"; verb stem = infinitive without that ending.
    Without a colon the whole infinitive counts as the ending (stem = "").
    """
    if ":" not in template:
        return ""
    ending = template.split(":", 1)[1]
    if ending == "":
        return infinitive
    if not infinitive.endswith(ending):
        return None
    return infinitive[: len(infinitive) - len(ending)]


def parse_verbs(path: Path) -> list:
    """Read verbs-fr.xml and return (infinitive, template) pairs."""
    root = ET.parse(path).getroot()
    verbs = []
    for v in root.iter("v"):
        inf = (v.findtext("i") or "").strip()
        tpl = (v.findtext("t") or "").strip()
        if inf and tpl:
            verbs.append((inf, tpl))
    return verbs


def build_database(verbs_xml: Path, conj_xml: Path, db_path: Path) -> None:
    templates = parse_templates(conj_xml)
    verbs = parse_verbs(verbs_xml)

    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)

    skipped = []
    total_forms = 0

    with conn:  # one transaction for everything -> much faster
        for infinitive, template in verbs:
            entries = templates.get(template)
            stem = stem_of(infinitive, template)
            if entries is None or stem is None:
                skipped.append((infinitive, template))
                continue

            cur = conn.execute(
                "INSERT OR IGNORE INTO verbs (infinitive, template) VALUES (?, ?)",
                (infinitive, template),
            )
            if cur.rowcount == 0:      # duplicate in verbs-fr.xml
                continue
            verb_id = cur.lastrowid

            rows = [
                (verb_id, mood, tense, person, variant, stem + ending)
                for mood, tense, person, variant, ending in entries
            ]
            conn.executemany(
                "INSERT OR IGNORE INTO conjugations "
                "(verb_id, mood, tense, person, variant, form) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            total_forms += len(rows)

    n_verbs = conn.execute("SELECT COUNT(*) FROM verbs").fetchone()[0]
    conn.close()

    print(f"{n_verbs} verbs, {total_forms} conjugation forms -> {db_path}")
    if skipped:
        print(f"Skipped ({len(skipped)}): template missing or does not match, e.g.:")
        for inf, tpl in skipped[:10]:
            print(f"  {inf}  ({tpl})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("verbs_xml", type=Path, help="Path to verbs-fr.xml")
    ap.add_argument("conjugation_xml", type=Path, help="Path to conjugation-fr.xml")
    ap.add_argument("db", type=Path, nargs="?", default=Path("conjugations.db"),
                    help="Output database (default: conjugations.db)")
    args = ap.parse_args()

    for p in (args.verbs_xml, args.conjugation_xml):
        if not p.exists():
            print(f"File not found: {p}", file=sys.stderr)
            return 1

    build_database(args.verbs_xml, args.conjugation_xml, args.db)
    return 0


if __name__ == "__main__":
    sys.exit(main())