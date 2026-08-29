# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Turn a text description into a greybox layout: a list of named boxes (position + size). No bpy, so it is testable.

The Scenario LLM writes the layout as JSON; parse_blockout tolerates the usual noise (code fences, stray prose) and
clamps every value so a bad answer can never place a 10 km cube or a NaN."""
import json
import re

MAX_BOXES = 80
MIN_SIZE, MAX_SIZE = 0.05, 200.0
MAX_COORD = 500.0

INSTRUCTION = (
    "You lay out a rough 3D blockout (greybox) for a scene, as axis-aligned boxes a level designer would drop in "
    "before modelling. Output ONLY a JSON array, no prose, no code fence. Each element is "
    '{"name": "<short label>", "position": [x, y, z], "size": [x, y, z]} in metres, Z up, the ground at z = 0, so a '
    "box resting on the ground has position z = size_z / 2. Use 6 to 20 boxes, sensible real-world sizes, spread over "
    "the ground plane so pieces do not overlap. Scene to block out: "
)


def _num(value, default, lo, hi):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    if n != n or n in (float("inf"), float("-inf")):  # NaN / inf
        return default
    return max(lo, min(hi, n))


def _vec3(value, defaults, lo, hi):
    seq = value if isinstance(value, (list, tuple)) else []
    return [_num(seq[i] if i < len(seq) else defaults[i], defaults[i], lo, hi) for i in range(3)]


def _extract_json_array(text):
    """The JSON array from an LLM answer that may be wrapped in ```json ... ``` or trailing prose."""
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        return None


def parse_blockout(text):
    """A sanitised list of {"name", "position"[3], "size"[3]} boxes, at most MAX_BOXES. Empty list when unparseable."""
    data = _extract_json_array(text)
    if not isinstance(data, list):
        return []
    boxes = []
    for index, raw in enumerate(data[:MAX_BOXES]):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or f"Block {index + 1}").strip()[:60] or f"Block {index + 1}"
        size = _vec3(raw.get("size"), [1.0, 1.0, 1.0], MIN_SIZE, MAX_SIZE)
        position = _vec3(raw.get("position"), [0.0, 0.0, size[2] / 2.0], -MAX_COORD, MAX_COORD)
        boxes.append({"name": name, "position": position, "size": size})
    return boxes
