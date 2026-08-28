# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
from scenario.core.api.catalog import param_override


def test_rodin_material_defaults_to_pbr_only_for_rodin():
    assert param_override("model_rodin-hyper3d-v2-5-text-to-3d", "material") == "PBR"
    assert param_override("model_rodin-hyper3d-v2-5", "material") == "PBR"
    assert param_override("model_meshy-7-txt23d", "material") is None
