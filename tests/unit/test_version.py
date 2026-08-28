# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_manifest_package_and_changelog_agree_on_the_version():
    manifest = re.search(r'^version = "([^"]+)"', (ROOT / "scenario" / "blender_manifest.toml").read_text(), re.M).group(1)
    package = re.search(r'^__version__ = "([^"]+)"', (ROOT / "scenario" / "__init__.py").read_text(), re.M).group(1)
    changelog_head = re.search(r"^## \[?(\d+\.\d+\.\d+)\]?", (ROOT / "CHANGELOG.md").read_text(), re.M).group(1)
    assert manifest == package
    assert manifest == changelog_head, "bump blender_manifest.toml and scenario/__init__.py when adding a CHANGELOG entry"
