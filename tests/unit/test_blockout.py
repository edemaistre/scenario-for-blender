# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
from scenario.core.scene import blockout


def test_parses_a_plain_json_array():
    boxes = blockout.parse_blockout('[{"name": "Well", "position": [0, 0, 0.5], "size": [1, 1, 1]}]')
    assert boxes == [{"name": "Well", "position": [0.0, 0.0, 0.5], "size": [1.0, 1.0, 1.0]}]


def test_tolerates_a_code_fence_and_prose():
    text = 'Sure! Here is the layout:\n```json\n[{"name": "Gate", "size": [3, 0.4, 4]}]\n```\nEnjoy.'
    boxes = blockout.parse_blockout(text)
    assert len(boxes) == 1
    assert boxes[0]["name"] == "Gate"
    assert boxes[0]["size"] == [3.0, 0.4, 4.0]
    assert boxes[0]["position"] == [0.0, 0.0, 2.0]  # default position sits the box on the ground (z = size_z / 2)


def test_clamps_bad_values_and_names():
    boxes = blockout.parse_blockout('[{"name": "", "size": [99999, -5, "x"], "position": [1e9, 0, 0]}]')
    assert boxes[0]["name"] == "Block 1"
    assert boxes[0]["size"] == [blockout.MAX_SIZE, blockout.MIN_SIZE, 1.0]
    assert boxes[0]["position"][0] == blockout.MAX_COORD


def test_unparseable_or_empty_returns_empty_list():
    assert blockout.parse_blockout("sorry, I can't do that") == []
    assert blockout.parse_blockout("") == []
    assert blockout.parse_blockout('{"not": "an array"}') == []


def test_caps_the_number_of_boxes():
    many = "[" + ",".join('{"name": "b", "size": [1,1,1]}' for _ in range(200)) + "]"
    assert len(blockout.parse_blockout(many)) == blockout.MAX_BOXES
