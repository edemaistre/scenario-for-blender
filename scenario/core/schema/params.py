# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Turn a model record's parameter schema into UI specs and request bodies."""
from dataclasses import dataclass, field

FILE_TYPES = ("file", "file_array")


@dataclass
class ParamSpec:
    name: str
    label: str
    ptype: str  # string | number | boolean | file | file_array | string_array
    default: object = None
    description: str = ""
    group: str = "Settings"
    required_always: bool = False
    required_if_defined: tuple = ()
    allowed_values: tuple = ()
    allowed_labels: dict = field(default_factory=dict)
    min: float = None
    max: float = None
    step: float = None
    max_length: int = None
    cost_impact: bool = False
    kind: str = None  # image | video | audio | 3d for files
    is_prompt: bool = False
    is_array: bool = False

    @property
    def is_file(self):
        return self.ptype in FILE_TYPES

    @property
    def is_integer(self):
        if self.ptype != "number":
            return False
        candidates = [v for v in (self.step, self.default, self.min, self.max) if isinstance(v, (int, float))]
        if self.allowed_values:
            candidates.extend(v for v in self.allowed_values if isinstance(v, (int, float)))
        return bool(candidates) and all(float(v).is_integer() for v in candidates)

    def label_for(self, value):
        return self.allowed_labels.get(value, str(value))


@dataclass
class Schema:
    specs: list
    resolution_presets: list = field(default_factory=list)
    prompt_name: str = None
    one_of: list = field(default_factory=list)  # groups where at least one member must be provided (either image or prompt)

    def by_name(self, name):
        return next((s for s in self.specs if s.name == name), None)


# Some models mark a file input `required: true` when it is really required only in the absence of an alternative
# (Rodin Bang: "Provide a reference image ... if no prompt is provided"). Faithfully requiring it blocks the valid
# prompt-only path. We relax such a file to optional and instead require at least one of the either/or group.
CONDITIONAL_MARKERS = ("if no ", "if not ", "when no ", "when not ", "unless ", "if none")


def _is_conditional(description):
    text = (description or "").lower()
    return any(marker in text for marker in CONDITIONAL_MARKERS)


def _parse_required(raw):
    if isinstance(raw, bool):
        return raw, ()
    if isinstance(raw, dict):
        always = bool(raw.get("always"))
        if_defined = tuple(sorted((raw.get("ifDefined") or {}).keys()))
        return always, if_defined
    return False, ()


def parse_schema(record):
    ui = record.ui_config
    selects = ui.get("selects") or {}
    specs = []
    for raw in record.parameters:
        name = raw.get("name")
        if not name:
            continue
        ptype = raw.get("type") or "string"
        always, if_defined = _parse_required(raw.get("required"))
        allowed = tuple(raw.get("allowedValues") or raw.get("allowed_values") or ())
        labels = {}
        for key, label in (selects.get(name) or {}).items():
            match = next((v for v in allowed if str(v) == str(key)), key)
            labels[match] = label
        specs.append(ParamSpec(
            name=name,
            label=raw.get("label") or name,
            ptype=ptype,
            default=raw.get("default"),
            description=raw.get("description") or "",
            group=raw.get("group") or ("Prompt" if raw.get("prompt") else "Settings"),
            required_always=always,
            required_if_defined=if_defined,
            allowed_values=allowed,
            allowed_labels=labels,
            min=raw.get("min"),
            max=raw.get("max"),
            step=raw.get("step"),
            max_length=raw.get("maxLength") or raw.get("max_length"),
            cost_impact=bool(raw.get("costImpact") or raw.get("cost_impact")),
            kind=raw.get("kind"),
            is_prompt=bool(raw.get("prompt")),
            is_array=ptype in ("file_array", "string_array") or bool(raw.get("array")),
        ))
    presets = []
    res = ui.get("resolutionComponent") or {}
    for preset in res.get("presets") or []:
        presets.append({"label": preset.get("label"), "width": preset.get("width"), "height": preset.get("height"),
                        "width_param": res.get("widthInput", "width"), "height_param": res.get("heightInput", "height")})
    prompt_name = next((s.name for s in specs if s.is_prompt), None)
    one_of = []
    if prompt_name:
        # a required file whose own description says it applies only "if no prompt" is an alternative to the prompt,
        # not a hard requirement: relax it and require at least one of {that file(s), the prompt}.
        conditional = [s for s in specs if s.is_file and s.required_always and _is_conditional(s.description)]
        if conditional:
            for spec in conditional:
                spec.required_always = False
            one_of.append(tuple([s.name for s in conditional] + [prompt_name]))
    return Schema(specs=specs, resolution_presets=presets, prompt_name=prompt_name, one_of=one_of)


def _coerce(spec, value):
    if spec.ptype == "number":
        if isinstance(value, str):
            value = float(value) if value.strip() else None
            if value is None:
                return None
        return int(round(value)) if spec.is_integer else float(value)
    if spec.ptype == "boolean":
        return bool(value)
    if spec.ptype == "string_array":
        return [str(v) for v in value]
    if spec.allowed_values and not isinstance(spec.allowed_values[0], str):
        for candidate in spec.allowed_values:
            if str(candidate) == str(value):
                return candidate
    return value


def build_body(specs, values, files, enabled=None):
    """Flat request body. Unset optionals are omitted; arrays stay arrays; files become asset ids."""
    body = {}
    for spec in specs:
        if enabled is not None and not spec.required_always and not enabled.get(spec.name, True):
            continue
        if spec.is_file:
            ids = list(files.get(spec.name) or [])
            if not ids:
                continue
            body[spec.name] = ids if spec.ptype == "file_array" else ids[0]
            continue
        value = values.get(spec.name)
        if value is None or value == "" or (isinstance(value, (list, tuple)) and len(value) == 0):
            continue
        coerced = _coerce(spec, value)
        if coerced is None:
            continue
        body[spec.name] = coerced
    return body


def validate(specs, body, one_of=()):
    errors = []
    for spec in specs:
        value = body.get(spec.name)
        present = value is not None and value != "" and value != []
        if spec.required_always and not present:
            errors.append(f"{spec.label} is required")
            continue
        if not present:
            continue
        if spec.max_length and isinstance(value, str) and len(value) > spec.max_length:
            errors.append(f"{spec.label} is longer than {spec.max_length} characters")
        if spec.allowed_values and spec.ptype != "string_array" and value not in spec.allowed_values:
            options = ", ".join(str(v) for v in spec.allowed_values)
            errors.append(f"{spec.label} must be one of {options}")
        if spec.ptype == "number" and isinstance(value, (int, float)) and not spec.allowed_values:
            lo, hi = spec.min, spec.max
            if (lo is not None and value < lo) or (hi is not None and value > hi):
                errors.append(f"{spec.label} must be between {_fmt(lo)} and {_fmt(hi)}")
    by_name = {s.name: s for s in specs}
    for spec in specs:
        for dep_name in spec.required_if_defined:
            dep = by_name.get(dep_name)
            if dep is not None and body.get(dep_name) not in (None, "", []) and body.get(spec.name) in (None, "", []):
                errors.append(f"{spec.label} is required when {dep.label} is set")
    for group in one_of:
        if not any(body.get(name) not in (None, "", []) for name in group):
            labels = [(by_name[name].label if name in by_name else name) for name in group]
            errors.append("Provide one of: " + " or ".join(labels))
    return errors


def missing_required_files(specs, body):
    return [s.name for s in specs if s.is_file and s.required_always and body.get(s.name) in (None, "", [])]


def _fmt(value):
    if value is None:
        return "?"
    return str(int(value)) if float(value).is_integer() else str(value)
