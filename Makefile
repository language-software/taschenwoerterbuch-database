.PHONY: sources build quick clean

# Download, verify and unpack all inputs (needs `gh` logged in for the Wiktextract snapshot)
sources:
	scripts/fetch_sources.sh

# Full build of both dictionaries into dist/
build:
	python3 scripts/build_dictionary.py --pair fr-de
	python3 scripts/build_dictionary.py --pair de-fr

# Quick test: small inputs, no Wiktextract
quick:
	scripts/fetch_sources.sh --no-wiktionary
	python3 scripts/build_dictionary.py --pair fr-de --no-wiktionary --limit 1000
	python3 scripts/build_dictionary.py --pair de-fr --no-wiktionary --limit 1000

# Remove build output and unpacked sources (keeps downloads/)
clean:
	rm -rf dist sources
