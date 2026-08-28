#!/bin/zsh
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
# Build and validate the extension zip with Blender's own CLI.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BLENDER="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
mkdir -p "$ROOT/dist"
"$BLENDER" --command extension build --source-dir "$ROOT/scenario" --output-dir "$ROOT/dist"
ZIP="$(ls -t "$ROOT"/dist/scenario-*.zip | head -1)"
"$BLENDER" --command extension validate "$ZIP"
echo "built $ZIP"
