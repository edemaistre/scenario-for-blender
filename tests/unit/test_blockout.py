# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
from scenario.core.scene import blockout


def test_parses_rich_elements():
    text = '[{"name": "Well", "category": "water", "primitive": "cylinder", "position": [0,0,0.5], "size": [1.6,1.6,1], "rotation": 45, "group": "Center"}]'
    els = blockout.parse_plan(text)
    assert len(els) == 1
    el = els[0]
    assert el["name"] == "Well" and el["category"] == "water" and el["primitive"] == "cylinder"
    assert el["rotation"] == 45.0 and el["group"] == "Center"
    assert el["size"] == [1.6, 1.6, 1.0]


def test_tolerates_fence_prose_and_fills_defaults():
    text = 'Here you go:\n```json\n[{"name": "Wall", "size": [4, 0.3, 3]}]\n```'
    el = blockout.parse_plan(text)[0]
    assert el["primitive"] == "box"          # default primitive
    assert el["category"] == "other"          # default category
    assert el["group"] == "Blockout"          # default group
    assert el["position"] == [0.0, 0.0, 1.5]  # sits on the ground (z = size_z / 2)
    assert el["rotation"] == 0.0


def test_bad_enums_fall_back_and_values_clamp():
    text = '[{"name": "", "category": "spaceship", "primitive": "torus", "size": [99999, -5, "x"], "rotation": 9999, "position": [1e9,0,0]}]'
    el = blockout.parse_plan(text)[0]
    assert el["name"] == "Block 1"
    assert el["category"] == "other" and el["primitive"] == "box"
    assert el["size"] == [blockout.MAX_SIZE, blockout.MIN_SIZE, 1.0]
    assert el["rotation"] == 360.0
    assert el["position"][0] == blockout.MAX_COORD


def test_unparseable_returns_empty_and_count_is_capped():
    assert blockout.parse_plan("nope") == []
    assert blockout.parse_plan("") == []
    many = "[" + ",".join('{"name":"b"}' for _ in range(400)) + "]"
    assert len(blockout.parse_plan(many)) == blockout.MAX_ELEMENTS


def test_plan_summary_counts_by_category_and_group():
    els = blockout.parse_plan('[{"name":"a","category":"wall","group":"G1"},{"name":"b","category":"wall","group":"G2"},{"name":"c","category":"prop","group":"G1"}]')
    summary = blockout.plan_summary(els)
    assert summary["total"] == 3
    assert summary["by_category"] == {"wall": 2, "prop": 1}
    assert summary["by_group"] == {"G1": 2, "G2": 1}


def test_instruction_includes_scene_type_and_refine():
    base = blockout.instruction("a square", scene_type="exterior", scale="human")
    assert "market" not in base and "JSON array" in base and "a square" in base
    refine = blockout.instruction("add a tower", previous=[{"name": "x"}])
    assert "UPDATED" in refine and "add a tower" in refine
