# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import sys


def test_core_imports_without_bpy():
    import scenario  # noqa: F401
    import scenario.core  # noqa: F401

    assert "bpy" not in sys.modules
    assert callable(scenario.register)
    assert callable(scenario.unregister)
