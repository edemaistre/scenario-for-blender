#!/bin/zsh
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
# Build the extension and generate a static extension repository (index.json + zips + html) under dist/repo.
# Host dist/repo on any static server; users add its index.json URL once in Preferences > Get Extensions > Repositories.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BLENDER="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
"$ROOT/tools/build.sh"
REPO="$ROOT/dist/repo"
mkdir -p "$REPO"
cp "$(ls -t "$ROOT"/dist/scenario-*.zip | head -1)" "$REPO/"
"$BLENDER" --command extension server-generate --repo-dir "$REPO" --html
echo "repository ready: $REPO/index.json (serve dist/repo over HTTPS and add that URL in Blender)"
