# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Audit that every model the plugin can surface produces a correct request payload.

Fetches each surfaced model's live schema from /models/{id} (free, no generation), parses it with the
plugin's own parse_schema, and checks a set of invariants. Raw responses are cached under
scratchpad/schema-cache so re-runs are offline. No bpy. Run: python3 tools/audit_payloads.py
"""
import json
import os
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scenario.core.api import catalog as C
from scenario.core.api.client import ScenarioClient
from scenario.core.api.errors import ScenarioError, NetworkError
from scenario.core.schema.params import parse_schema

CACHE = pathlib.Path(os.environ.get("SCHEMA_CACHE", pathlib.Path(tempfile.gettempdir()) / "scenario-schema-cache"))
CACHE.mkdir(parents=True, exist_ok=True)

CONDITIONAL_WORDS = ("if no", "if not", "unless", "when no", "when not", "optional", "either", "or a ", "or an ", "instead of", "alternative", "if none")


def load_env():
    env = {}
    for line in (ROOT / ".env.local").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def surfaced_model_ids():
    """Every model id the plugin can put in front of a user: curated lane lists + edit3d tasks + materials."""
    ids, where = {}, {}
    def add(mid, ctx):
        where.setdefault(mid, []).append(ctx)
    for lane, models in C.DEFAULT_MODELS.items():
        for m in models:
            add(m, f"lane:{lane}")
    for task_id, _label, _desc, models in C.EDIT3D_TASKS:
        for m in models:
            add(m, f"edit3d:{task_id}")
    for m in C.PATINA_MODELS:
        add(m, "material")
    for m in where:
        ids[m] = where[m]
    return ids


def fetch(client, model_id):
    cache = CACHE / f"{model_id}.json"
    if cache.exists():
        return json.loads(cache.read_text()), None
    try:
        data = client.get(f"/models/{model_id}")
    except (ScenarioError, NetworkError) as err:
        return None, str(getattr(err, "reason", err))
    model = data.get("model") or data
    cache.write_text(json.dumps(model))
    time.sleep(0.15)
    return model, None


def audit_one(model_id, contexts, record, schema):
    """Return a list of (severity, code, message) findings for one model."""
    out = []
    specs = schema.specs
    files = [s for s in specs if s.is_file]
    req_files = [s for s in files if s.required_always]
    prompts = [s for s in specs if s.is_prompt]
    edit3d = any(c.startswith("edit3d") for c in contexts)
    only_edit3d = edit3d and not any(c.startswith("lane:") for c in contexts if not c.startswith("lane:edit3d"))
    mesh = C.mesh_param(record)
    resolved = {name for group in schema.one_of for name in group}  # names the parser already put in an either/or group

    # 1. Over-required inputs: a required file whose description says it is conditional (either/or with another input).
    for s in files:
        desc = (s.description or "").lower()
        if s.required_always and s.name not in resolved and any(w in desc for w in CONDITIONAL_WORDS):
            out.append(("HIGH", "conditional-required-file",
                        f"file '{s.name}' ({s.label}) is required_always but its description reads conditional: \"{s.description}\""))

    # 2. Either/or: >1 required file inputs of different kinds, or a required file plus a prompt that says 'if no ...'.
    req_files = [s for s in req_files if s.name not in resolved]
    if len(req_files) >= 2:
        kinds = ", ".join(f"{s.name}[{s.kind}]" for s in req_files)
        out.append(("MED", "multiple-required-files", f"{len(req_files)} required file inputs at once ({kinds}); the user must supply all of them"))
    for p in prompts:
        pdesc = (p.description or "").lower()
        if p.name not in resolved and any(w in pdesc for w in ("if no", "if not", "unless", "when no", "instead of")) and req_files:
            # only meaningful if the required file's OWN description is conditional (caught by check #1); otherwise
            # the prompt pairs with an optional sibling image (Meshy texturePrompt<->textureImage), which is fine.
            if any((f.description or "").lower().find("if no") >= 0 or (f.description or "").lower().find("when no") >= 0 for f in req_files):
                out.append(("HIGH", "prompt-is-alternative",
                            f"prompt '{p.name}' is an alternative to a required file, still blocked"))

    # 3. edit3d/3d models must have a detectable mesh input (kind 3d file).
    if (edit3d or "3d" in [c.split(":")[-1] for c in contexts]) and mesh is None and any(s.kind == "3d" for s in files) is False:
        needs_mesh = edit3d
        if needs_mesh:
            out.append(("HIGH", "no-mesh-param", "edit3d model but no file input with kind '3d'; the selected mesh cannot be attached"))

    # 4. A prompt exists but the model's only home is a lane that does not draw the prompt row.
    #    All generation lanes draw the prompt except material (Patina) and edit3d only draws it when prompt_name is set.
    if prompts and only_edit3d and not schema.prompt_name:
        out.append(("MED", "prompt-not-drawn", "has a prompt param but schema.prompt_name is unset, so the edit3d lane will not draw it"))

    # 5. required flag lost: raw says required true/dict but parse produced required_always False (parser bug).
    raw_by_name = {r.get("name"): r for r in record.parameters}
    for s in specs:
        raw = raw_by_name.get(s.name) or {}
        rr = raw.get("required")
        raw_required = rr is True or (isinstance(rr, dict) and rr.get("always"))
        if raw_required and not s.required_always and s.name not in resolved:
            out.append(("HIGH", "required-flag-lost", f"'{s.name}' is required in the API but parse_schema dropped required_always"))

    # 6. no prompt and no file and no settings at all -> empty payload (model unusable as wired).
    drawable = [s for s in specs if not s.is_prompt and not s.is_file]
    if not specs:
        out.append(("HIGH", "empty-schema", "no parameters in the schema at all"))
    return out


def main():
    env = load_env()
    client = ScenarioClient(env["SCENARIO_API_KEY"], env["SCENARIO_API_SECRET"],
                            base_url=env.get("SCENARIO_API_BASE", "https://api.cloud.scenario.com/v1"))
    ids = surfaced_model_ids()
    print(f"# Payload audit: {len(ids)} surfaced models\n")
    findings, failed = {}, {}
    schemas = {}
    for model_id in sorted(ids):
        model, err = fetch(client, model_id)
        if model is None:
            failed[model_id] = err
            continue
        record = C.ModelRecord.from_api(model)
        if not record.parameters:
            failed[model_id] = "no parameters/inputs in the record"
            continue
        schema = parse_schema(record)
        schemas[model_id] = (record, schema)
        f = audit_one(model_id, ids[model_id], record, schema)
        if f:
            findings[model_id] = f

    # Report
    order = {"HIGH": 0, "MED": 1, "LOW": 2}
    total = sum(len(v) for v in findings.values())
    print(f"Fetched {len(schemas)} schemas, {len(failed)} failed to fetch, {len(findings)} models with findings, {total} findings total.\n")
    if failed:
        print("## Fetch failures (curated id not resolvable)\n")
        for mid, err in sorted(failed.items()):
            print(f"- `{mid}` ({', '.join(ids[mid])}): {err}")
        print()
    print("## Findings\n")
    for model_id in sorted(findings, key=lambda m: (min(order[s] for s, _, _ in findings[m]), m)):
        rec, schema = schemas[model_id]
        print(f"### `{model_id}` — {rec.name}  [{', '.join(ids[model_id])}]")
        for sev, code, msg in sorted(findings[model_id], key=lambda x: order[x[0]]):
            print(f"- **{sev}** `{code}`: {msg}")
        io = ", ".join(f"{s.name}:{s.ptype}{'/'+s.kind if s.kind else ''}{'*' if s.required_always else ''}{'(prompt)' if s.is_prompt else ''}" for s in schema.specs)
        print(f"  - schema: {io}")
        print()


if __name__ == "__main__":
    main()
