# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bridge between ParamSpec schemas and the ScenarioParamValue collection, plus drawing."""
from . import runtime

SEP = ","


def multi_selection(item):
    return [v for v in item.multi_value.split(SEP) if v]


def set_multi_selection(item, values):
    item.multi_value = SEP.join(str(v) for v in values)


def _drawable(spec):
    return not spec.is_prompt and not spec.is_file


def sync_params(lane_state, schema, model_id):
    """Ensure one collection item per drawable spec; keep values whose name, type and model match."""
    existing = {item.name: item for item in lane_state.params}
    keep = {}
    for spec in schema.specs:
        if not _drawable(spec):
            continue
        item = existing.get(spec.name)
        compatible = item is not None and item.ptype == spec.ptype and item.model_id == model_id
        created = False
        if item is None or not compatible:
            if item is not None:
                lane_state.params.remove(lane_state.params.find(spec.name))
            item = lane_state.params.add()
            item.name, item.ptype = spec.name, spec.ptype
            item.model_id, item.lane, item.label = model_id, lane_state.lane, spec.label
            _apply_default(item, spec, schema)
            created = True
        keep[spec.name] = True
        if spec.allowed_values and spec.ptype != "string_array":
            # Blender rejects empty enum identifiers: an empty option means "unset", modelled by the enable toggle.
            options = [v for v in spec.allowed_values if str(v) != ""]
            if not options:
                continue
            runtime.set_enum_items(("param", model_id, spec.name), [(str(v), spec.label_for(v), spec.description) for v in options])
            valid = [str(v) for v in options]
            has_default = spec.default is not None and str(spec.default) in valid
            default = str(spec.default) if has_default else valid[0]
            if created or item.enum_value not in valid:
                item.enum_value = default
            if created and not has_default and not spec.required_always:
                item.enabled = False
    for index in range(len(lane_state.params) - 1, -1, -1):
        if lane_state.params[index].name not in keep:
            lane_state.params.remove(index)


def _numeric_fallback(spec, schema=None):
    """A sensible value when the schema has no default: preset, then 1024 for sizes, then the range."""
    lo = spec.min if spec.min is not None else 0
    hi = spec.max if spec.max is not None else lo
    if schema is not None:
        for preset in schema.resolution_presets:
            if preset.get("width_param") == spec.name and preset.get("width"):
                return preset["width"]
            if preset.get("height_param") == spec.name and preset.get("height"):
                return preset["height"]
    if spec.name.lower() in ("width", "height"):
        return max(lo, min(1024, hi if hi else 1024))
    return lo


def _apply_default(item, spec, schema=None):
    item.has_range = spec.min is not None or spec.max is not None
    item.fmin = float(spec.min) if spec.min is not None else -1e9
    item.fmax = float(spec.max) if spec.max is not None else 1e9
    default = spec.default
    if spec.ptype == "number":
        value = default if isinstance(default, (int, float)) else _numeric_fallback(spec, schema)
        if spec.is_integer:
            item.int_value = int(value)
        else:
            item.float_value = float(value)
    elif spec.ptype == "boolean":
        item.bool_value = bool(default)
    elif spec.ptype == "string_array":
        set_multi_selection(item, default or [])
    elif spec.ptype == "string" and not spec.allowed_values:
        item.str_value = default if isinstance(default, str) else ""
    item.enabled = True


def collect_values(lane_state, schema):
    values, enabled = {}, {}
    if schema.prompt_name:
        values[schema.prompt_name] = lane_state.prompt
    for spec in schema.specs:
        if not _drawable(spec):
            continue
        index = lane_state.params.find(spec.name)
        if index < 0:
            continue
        item = lane_state.params[index]
        enabled[spec.name] = bool(item.enabled) or spec.required_always
        if spec.ptype == "number":
            values[spec.name] = item.int_value if spec.is_integer else item.float_value
        elif spec.ptype == "boolean":
            values[spec.name] = item.bool_value
        elif spec.ptype == "string_array":
            values[spec.name] = multi_selection(item)
        elif spec.allowed_values:
            values[spec.name] = item.enum_value if item.enum_value != "NONE" else None
        else:
            values[spec.name] = item.str_value
    return values, enabled


def collect_file_refs(lane_state, schema):
    refs = {spec.name: [] for spec in schema.specs if spec.is_file}
    for ref in lane_state.references:
        if ref.param_name in refs:
            refs[ref.param_name].append(ref)
    return refs


def draw_params(layout, lane_state, schema, exclude=()):
    groups = {}
    for spec in schema.specs:
        if not _drawable(spec) or spec.name in exclude:
            continue
        groups.setdefault(spec.group or "Settings", []).append(spec)
    for group, specs in groups.items():
        box = layout.box()
        box.label(text=group)
        for spec in specs:
            index = lane_state.params.find(spec.name)
            if index < 0:
                continue
            item = lane_state.params[index]
            row = box.row(align=True)
            if not spec.required_always:
                row.prop(item, "enabled", text="")
            sub = row.row(align=True)
            sub.enabled = item.enabled or spec.required_always
            label = spec.label + (" (cost)" if spec.cost_impact else "")
            if spec.ptype == "boolean":
                sub.prop(item, "bool_value", text=label)
            elif spec.ptype == "number" and not spec.allowed_values:
                sub.prop(item, "int_value" if spec.is_integer else "float_value", text=label)
            elif spec.ptype == "string_array":
                col = sub.column(align=True)
                col.label(text=label)
                grid = col.grid_flow(columns=2, align=True)
                selected = set(multi_selection(item))
                for value in spec.allowed_values:
                    op = grid.operator("scenario.toggle_multi", text=spec.label_for(value), depress=str(value) in selected)
                    op.lane, op.param_name, op.value = lane_state.lane, spec.name, str(value)
            elif spec.allowed_values:
                sub.prop(item, "enum_value", text=label)
            else:
                sub.prop(item, "str_value", text=label)
