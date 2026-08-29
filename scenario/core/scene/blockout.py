# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prompt to Blockout: turn a scene description into a structured greybox plan and back. No bpy, so it is testable.

An element is a primitive (box, cylinder, plane, wedge, cone, sphere) with a position, size, yaw and a semantic
category that decides its greybox colour and which sub-collection it lands in. The Scenario LLM writes the plan as
JSON; parse_plan tolerates the usual noise and clamps every value so a bad answer can never place a runaway shape."""
import json
import re

MAX_ELEMENTS = 200
MIN_SIZE, MAX_SIZE = 0.02, 500.0
MAX_COORD = 2000.0

PRIMITIVES = ("box", "cylinder", "plane", "wedge", "cone", "sphere")

# semantic categories: label + a readable greybox colour (linear-ish RGB, alpha 1). A wall reads grey, vegetation
# green, a light yellow, so the blockout is legible without modelling anything.
CATEGORIES = {
    "floor":      ("Floor",      (0.62, 0.62, 0.64)),
    "wall":       ("Wall",       (0.78, 0.78, 0.80)),
    "structure":  ("Structure",  (0.55, 0.62, 0.72)),
    "prop":       ("Prop",       (0.85, 0.62, 0.35)),
    "furniture":  ("Furniture",  (0.70, 0.52, 0.38)),
    "vegetation": ("Vegetation", (0.42, 0.62, 0.40)),
    "vehicle":    ("Vehicle",    (0.75, 0.40, 0.40)),
    "water":      ("Water",      (0.40, 0.60, 0.78)),
    "light":      ("Light",      (0.90, 0.82, 0.45)),
    "other":      ("Other",      (0.66, 0.66, 0.66)),
}
DEFAULT_CATEGORY = "other"

SCENE_TYPES = (
    ("exterior", "Exterior", "An outdoor scene: a square, a street, a courtyard"),
    ("interior", "Interior", "An indoor scene: a room, a hall, a shop"),
    ("level", "Game level", "A playable level layout: paths, cover, arenas, spawn points"),
    ("nature", "Nature", "A natural environment: terrain, rocks, trees, water"),
    ("architecture", "Architecture", "A building or structure: facades, floors, stairs"),
)
SCALES = (
    ("human", "Human", "Human scale, a few metres across"),
    ("room", "Room", "A single room or shop"),
    ("building", "Building", "A whole building or plot"),
    ("district", "District", "A block, street or district"),
)


def instruction(prompt, scene_type="exterior", scale="human", previous=None):
    """The LLM instruction. When `previous` (a plan) is given, it is a refinement of that plan."""
    kind = dict((k, v) for k, v, _ in SCENE_TYPES).get(scene_type, "scene")
    span = dict((k, v) for k, v, _ in SCALES).get(scale, "human")
    head = (
        "You design a 3D blockout (greybox) for a game or film scene, as a level designer would before modelling. "
        f"Kind: {kind}. Scale: {span}. Output ONLY a JSON array, no prose, no code fence. Each element is "
        '{"name": "<short label>", "category": "<one of floor|wall|structure|prop|furniture|vegetation|vehicle|water|light|other>", '
        '"primitive": "<one of box|cylinder|plane|wedge|cone|sphere>", "position": [x, y, z], "size": [x, y, z], '
        '"rotation": <yaw degrees>, "group": "<sub-group label, e.g. Buildings>"} in metres, Z up, ground at z = 0 so a '
        "shape resting on the ground has position z = size_z / 2. Use a plane or a thin box for floors and walls, a "
        "cylinder for pillars/wells/tree trunks, a wedge for ramps and roofs, a cone for spires/conifers, a sphere for "
        "bushes/domes. Compose a believable, non-overlapping layout with 15 to 60 elements grouped into a few named "
        "groups, with a floor or ground, walls or boundaries, structures, and props. "
    )
    if previous:
        return (head + "Here is the current plan as JSON; return an UPDATED full plan applying this change: "
                + str(prompt) + "\nCurrent plan:\n" + json.dumps(previous)[:6000])
    return head + "Scene to block out: " + str(prompt)


def _num(value, default, lo, hi):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    if n != n or n in (float("inf"), float("-inf")):
        return default
    return max(lo, min(hi, n))


def _vec3(value, defaults, lo, hi):
    seq = value if isinstance(value, (list, tuple)) else []
    return [_num(seq[i] if i < len(seq) else defaults[i], defaults[i], lo, hi) for i in range(3)]


def _recover_objects(text):
    """Every complete top-level {...} object inside an array text, for when the answer was cut off mid-element."""
    objects, depth, start, in_string, escape = [], 0, None, False, False
    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    objects.append(json.loads(text[start:i + 1]))
                except ValueError:
                    pass
                start = None
    return objects


def _extract_json_array(text):
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except ValueError:
            pass
    # the array was truncated (a capped output): recover the complete objects written before the cut
    if start != -1:
        recovered = _recover_objects(text[start:])
        if recovered:
            return recovered
    return None


def parse_plan(text):
    """A sanitised list of blockout elements (at most MAX_ELEMENTS). Empty list when unparseable."""
    data = _extract_json_array(text)
    if not isinstance(data, list):
        return []
    elements = []
    for index, raw in enumerate(data[:MAX_ELEMENTS]):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or f"Block {index + 1}").strip()[:60] or f"Block {index + 1}"
        category = str(raw.get("category") or DEFAULT_CATEGORY).strip().lower()
        if category not in CATEGORIES:
            category = DEFAULT_CATEGORY
        primitive = str(raw.get("primitive") or "box").strip().lower()
        if primitive not in PRIMITIVES:
            primitive = "box"
        size = _vec3(raw.get("size"), [1.0, 1.0, 1.0], MIN_SIZE, MAX_SIZE)
        position = _vec3(raw.get("position"), [0.0, 0.0, size[2] / 2.0], -MAX_COORD, MAX_COORD)
        rotation = _num(raw.get("rotation"), 0.0, -360.0, 360.0)
        group = str(raw.get("group") or "Blockout").strip()[:60] or "Blockout"
        elements.append({"name": name, "category": category, "primitive": primitive,
                         "position": position, "size": size, "rotation": rotation, "group": group})
    return elements


def plan_summary(elements):
    """Counts by category and by group, for the tab to show what was designed before or after building."""
    by_category, by_group = {}, {}
    for el in elements:
        by_category[el["category"]] = by_category.get(el["category"], 0) + 1
        by_group[el["group"]] = by_group.get(el["group"], 0) + 1
    return {"total": len(elements), "by_category": by_category, "by_group": by_group}
