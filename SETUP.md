# Folder layout and sources

Versions and hashes: [`sources.lock`](sources.lock). Procedures: [README.md](README.md).

| Source | Where it comes from |
|---|---|
| FreeDict | `https://download.freedict.org/dictionaries/<pair>/<version>/freedict-<pair>-<version>.src.tar.xz` |
| Verbiste | `https://sources.debian.org/data/main/v/verbiste/<version>/data/<file>` |
| Wiktextract | release `SOURCES_TAG` of this repo (`fr_wiktextract.jsonl.gz`, `de_wiktextract.jsonl.gz`). Record the kaikki.org extraction date in that release's notes |

Local folders (all git-ignored):

```
downloads/   files as downloaded (kept between runs)
sources/     what the build reads (default --sources), created by scripts/fetch_sources.sh
├── freedict/fra-deu.tei, deu-fra.tei
├── verbiste/verbs-fr.xml, conjugation-fr.xml
└── wikiextract/fr_raw-wiktextract-data.jsonl, de_raw-wiktextract-data.jsonl
dist/        build output
```
