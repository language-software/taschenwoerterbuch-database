# taschenwoerterbuch-database

Builds the app's dictionary databases (`dictionary-fr-de`, `dictionary-de-fr`) from FreeDict, Verbiste and Wiktionary data and publishes them as GitHub Releases.

## How it works

```
 INPUT                    BUILD                         PUBLISH                     APP
 FreeDict    ─┐
 Verbiste    ─┼─► build_dictionary.py ─► dist/*.db ─► make_manifest.py ─► GitHub Release ─► manifest.json
 Wiktextract ─┘   (once per pair)                     (gzip + sha256)    (tag `data-*`)     then *.db.gz
```

- **Build** reads local files only and downloads nothing.
- **Publish** runs only in GitHub Actions, triggered by a `data-*` tag.
- **Wiktextract** is the only input you maintain by hand, as a snapshot release (`sources-YYYY.M`). kaikki.org keeps only the current file (2.8 GB gzipped, no dated versions), so builds are reproducible only from your own snapshot.
- FreeDict and Verbiste are small. `scripts/fetch_sources.sh` downloads them at the version pinned in `sources.lock` and checks the SHA-256. CI and local builds use the same script.

Two kinds of releases live in this repo:

| Release | Content | Created by | Frequency |
|---|---|---|---|
| `sources-YYYY.M` | Wiktextract snapshot (input) | you, manually | rare |
| `data-YYYY.M.N` | finished databases and `manifest.json` (output the app loads) | the workflow | every data change |

## Which task do I have?

| I want to… | Go to |
|---|---|
| Try a build on my machine | [A. Local build](#a-local-build) (`make quick` works right away; a full build needs D first) |
| Publish a new version | [B. Release](#b-release) |
| Update FreeDict or Verbiste | [C. Update a source](#c-update-a-source) |
| Use newer Wiktionary data | [D. New Wiktextract snapshot](#d-new-wiktextract-snapshot) |
| First-time setup of this repo | [E. First-time setup](#e-first-time-setup) |

Pinned versions and hashes: [`sources.lock`](sources.lock). Folder layout: [SETUP.md](SETUP.md).

---

## A. Local build

Run everything from the repo root. `downloads/`, `sources/` and `dist/` are git-ignored.

Pick one mode:

| Mode | Needs | Commands |
|---|---|---|
| **Quick test** (no Wiktionary data, always works) | internet | `make quick` |
| **Full build** | Wiktextract files, see below | `make sources build` |

**Where do the Wiktextract files come from?** The full build needs `fr_wiktextract.jsonl.gz` and `de_wiktextract.jsonl.gz` in `downloads/`. Either:
- they are in the `sources-*` release of this repo (`SOURCES_TAG` in `sources.lock`). Then `make sources` downloads them itself (needs `gh auth login`), or
- that release does not exist yet. Then first create the files and the release with [D](#d-new-wiktextract-snapshot), or at least copy the two `.gz` files into `downloads/` by hand. `make sources` then skips the `gh` download.

Notes:
- `scripts/fetch_sources.sh` downloads, checks the SHA-256 and unpacks. CI runs the same script. It reuses files already in `downloads/`.
- Versions and hashes live only in [`sources.lock`](sources.lock).
- Output: `dist/dictionary-<pair>.db`. Read the **data quality report** at the end. After `make quick` every entry shows "without Wiktionary match". That is expected.
- Without `make`: `scripts/fetch_sources.sh [--no-wiktionary]`, then `python3 scripts/build_dictionary.py --pair fr-de` (and `de-fr`). Extra flags: `--no-wiktionary`, `--limit N`, `--sources`, `--verbiste`, `--out`.
- `make clean` removes `dist/` and `sources/`.

## B. Release

1. Change code or data.
2. In `datasets.json`, raise `version` of every dataset whose content changed. Raise `schema` only for incompatible DB changes.
3. Commit and push.
4. `git tag data-2026.10.1 && git push origin data-2026.10.1` (format `data-YEAR.MONTH.COUNTER`).
5. Watch the Actions run, then open `https://github.com/<owner>/taschenwoerterbuch-database/releases/latest/download/manifest.json`.

Broken release: mark it pre-release or delete it. `latest` falls back to the previous one.

## C. Update a source

1. Pick a new version (FreeDict: https://download.freedict.org/dictionaries/fra-deu/ and `deu-fra`; Verbiste: https://sources.debian.org/src/verbiste/).
2. Download the files and run `shasum -a 256` on them.
3. Edit the version and hashes in [`sources.lock`](sources.lock). Nothing else.
4. `make sources build` (A), then release (B).

## D. New Wiktextract snapshot

1. Download `raw-wiktextract-data.jsonl.gz` from https://kaikki.org/dictionary/rawdata.html. Note the extraction date. Needs about 50 GB free disk.
2. Split by language into `fr_raw-wiktextract-data.jsonl` and `de_raw-wiktextract-data.jsonl`.
3. Shrink them (keeps only the fields the build reads):
   ```
   python scripts/prefilter_wiktextract.py --lang fr --input fr_raw-wiktextract-data.jsonl --output fr_wiktextract.jsonl.gz
   python scripts/prefilter_wiktextract.py --lang de --input de_raw-wiktextract-data.jsonl --output de_wiktextract.jsonl.gz
   ```
4. Check once that the filter loses nothing: build with the raw file and with the filtered file. The quality reports must be identical.
5. Publish the snapshot (each file must stay below 2 GiB):
   ```
   gh release create sources-2026.11 fr_wiktextract.jsonl.gz de_wiktextract.jsonl.gz \
     --title sources-2026.11 --notes "kaikki.org raw-wiktextract-data, extracted <date>"
   ```
6. Set `SOURCES_TAG` in [`sources.lock`](sources.lock).
7. Compare the quality report with the previous build, then release (B) with both datasets' `version` raised.

## E. First-time setup

1. Do D (create the first snapshot `sources-2026.10`).
2. Do A once with the filtered Wiktextract files.
3. `git status`: make sure no `.db`, `.gz`, `.jsonl` or `sources/` is staged. Then commit and push.
4. Test run: `git tag data-test-1 && git push origin data-test-1`. Check Actions, release and `manifest.json` (URLs, sizes, SHA-256). Clean up: `gh release delete data-test-1 --cleanup-tag`.
5. First real release: B.
6. Still open: `NOTICE.md` with sources and licenses (CC BY-SA, GPL). The app must show the credits.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `gh release download` fails (release not found) | The tag in `SOURCES_TAG` (`sources.lock`) does not exist, or `gh` is not logged in. Create the snapshot or fix the tag |
| `SHA-256 mismatch for ...` | Wrong hash in `sources.lock`, or the upstream file changed. Recompute and find out why |
| `No space left on device` in CI | Unpacked Wiktextract is too big. Use the filtered files |
| `File not found: sources/...` | Wrong folder layout. Expected: `sources/freedict/`, `sources/verbiste/`, `sources/wikiextract/` |
| Many "without Wiktionary match" | Wiktextract files missing, wrongly split, or `--no-wiktionary` was set |

## Open decisions

- Keep the Wiktextract prefilter (small snapshot, fast CI) or drop it (simpler, but CI must build the pairs one after another).
- `NOTICE.md` and `AGENTS.md` are missing.
