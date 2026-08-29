# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Scenario for Blender.

Entry point of the extension. Imports of bpy stay inside register/unregister
so that `scenario.core` is importable from plain Python (unit tests, tooling).
"""

__version__ = "0.9.2"


def register():
    from .blender import registry

    registry.register()


def unregister():
    from .blender import registry

    registry.unregister()
