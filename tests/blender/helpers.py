# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Helpers for tests that run inside `blender --background`."""
import importlib
import pathlib

import bpy

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"


def addon_name():
    for name in bpy.context.preferences.addons.keys():
        if name == "scenario" or name.endswith(".scenario"):
            return name
    raise RuntimeError("scenario extension is not enabled: run ./tools/install_dev.sh first")


def addon():
    return importlib.import_module(addon_name())


def submodule(path):
    return importlib.import_module(f"{addon_name()}.{path}")


def reset_scene():
    bpy.ops.wm.read_homefile(use_empty=True)
