#!/bin/zsh
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
# Build, then install into the local user_default repository and enable it.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BLENDER="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
"$ROOT/tools/build.sh"
ZIP="$(ls -t "$ROOT"/dist/scenario-*.zip | head -1)"
"$BLENDER" --command extension install-file --repo user_default --enable "$ZIP"
echo "installed $ZIP into user_default (restart running Blender instances)"
