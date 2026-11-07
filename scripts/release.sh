#!/usr/bin/env bash
# Cut a signed kw-mcp release into dist/release/ (see scripts/release.py and README "릴리스").
#   scripts/release.sh             real release: clean tree, HEAD tagged v<version>, a version above the
#                                  last release, keychain signing key (no npm code runs in it)
#   scripts/release.sh --last-latest-json FILE   also compare with the bridge's latest.json saved in FILE
#   scripts/release.sh --dry-run   rehearsal signed with a throwaway key (dist/release-dry-run, not deployable)
#   scripts/release.sh stage DIR   copy just the extension's files into DIR
#   scripts/release.sh pack FILE   pack the extension into FILE the way a release does
#   scripts/release.sh check-install   install this checkout like an agent update and self-test it
#   scripts/release.sh data        data-only release: HEAD's knowledge/rules files, data tests, signed into
#                                  dist/data/ (`data --dry-run`: throwaway key, dist/data-dry-run)
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run --frozen --quiet python scripts/release.py "$@"
