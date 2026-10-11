-- Schema of the app dictionary.
-- One language pair = one database (e.g. fr-de: search in French, translation into German).
-- The source language is stored in meta('source_lang'), the target language in meta('target_lang').

PRAGMA foreign_keys = ON;

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;

-- A dictionary entry = one lemma with its part of speech (FreeDict <entry>).
CREATE TABLE entry (
    id          INTEGER PRIMARY KEY,
    lemma       TEXT NOT NULL,
    pos         TEXT NOT NULL,          -- noun, verb, adj, adv, proper_noun, ...
    gender      TEXT,                   -- masc | fem | neut (FreeDict); gaps filled from Wiktionary, multiple e.g. 'masc/fem'
    plural      TEXT,                   -- Wiktionary forms (Tag plural)
    ipa         TEXT,                   -- without delimiters [] \\ //
    audio_url   TEXT,                   -- MP3 link (rule <Lang>-<word>.ogg, otherwise first recording, preferably from France)
    auxiliary   TEXT,                   -- auxiliary verb (avoir/être, haben/sein), verbs only
    template    TEXT,                   -- Verbiste template, French verbs only
    stem        TEXT                    -- verb stem; form = stem || conjugation_template.ending
);

-- Search index: lemma, variants and inflected forms -> entry.
-- term      = lowercase (NFC), accent-exact
-- term_fold = lowercase, without accents (é -> e) for tolerant search
CREATE TABLE lookup (
    term      TEXT    NOT NULL,
    term_fold TEXT    NOT NULL,
    entry_id  INTEGER NOT NULL REFERENCES entry(id) ON DELETE CASCADE,
    kind      INTEGER NOT NULL,         -- 0 = lemma, 1 = variant, 2 = inflected form
    PRIMARY KEY (term, entry_id)
) WITHOUT ROWID;
CREATE INDEX idx_lookup_fold ON lookup(term_fold);
CREATE INDEX idx_lookup_entry ON lookup(entry_id);

-- Sense = top-level FreeDict <sense>.
CREATE TABLE sense (
    id       INTEGER PRIMARY KEY,
    entry_id INTEGER NOT NULL REFERENCES entry(id) ON DELETE CASCADE,
    position INTEGER NOT NULL
);
CREATE INDEX idx_sense_entry ON sense(entry_id);

-- Translations (<quote>) in the target language; each one is individually clickable.
CREATE TABLE translation (
    sense_id INTEGER NOT NULL REFERENCES sense(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    text     TEXT    NOT NULL,
    PRIMARY KEY (sense_id, position)
) WITHOUT ROWID;

-- Explanations (<def>) of the sense, in the source language.
CREATE TABLE definition (
    sense_id INTEGER NOT NULL REFERENCES sense(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    text     TEXT    NOT NULL,
    PRIMARY KEY (sense_id, position)
) WITHOUT ROWID;

-- Conjugation patterns (Verbiste), only for French as the source language.
-- The form of a verb is entry.stem || ending.
-- person: 0-based index within the tense (see conjugation.py)
CREATE TABLE conjugation_template (
    template TEXT    NOT NULL,
    mood     TEXT    NOT NULL,
    tense    TEXT    NOT NULL,
    person   INTEGER NOT NULL,
    variant  INTEGER NOT NULL DEFAULT 0,
    ending   TEXT    NOT NULL,
    PRIMARY KEY (template, mood, tense, person, variant)
) WITHOUT ROWID;
