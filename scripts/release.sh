#!/usr/bin/env bash
# Cut a signed kw-mcp release into dist/release/ (see scripts/release.py and README "릴리스").
#   scripts/release.sh             real release: clean tree, HEAD tagged v<version>, keychain signing key
#   scripts/release.sh --dry-run   rehearsal signed with a throwaway key (dist/release-dry-run, not deployable)
#   scripts/release.sh stage DIR   copy just the extension's files into DIR
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run --frozen --quiet python scripts/release.py "$@"
