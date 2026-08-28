# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end smoke: one image to 3D (Tripo 3.1) through the core, plus free dry runs for the multi-view models.

Usage: SCENARIO_SMOKE=1 python3 tests/smoke/smoke_image_to_3d.py /path/to/image.png
"""
import os
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scenario.core import config  # noqa: E402
from scenario.core.api import assets  # noqa: E402
from scenario.core.api.catalog import Catalog  # noqa: E402
from scenario.core.api.client import ScenarioClient  # noqa: E402
from scenario.core.api.errors import ScenarioError  # noqa: E402
from scenario.core.api.generate import estimate  # noqa: E402
from scenario.core.jobs.manager import JobManager  # noqa: E402
from scenario.core.jobs.records import JobRegistry  # noqa: E402
from scenario.core.schema.params import build_body, parse_schema, validate  # noqa: E402
from scenario.core.scene import placement  # noqa: E402

MAX_CU = 120
if os.environ.get("SCENARIO_SMOKE") != "1":
    sys.exit("set SCENARIO_SMOKE=1 to spend credits")
image = pathlib.Path(sys.argv[1])
env = config.load_dotenv(ROOT / ".env.local")
creds = config.resolve_credentials(env.get("SCENARIO_API_KEY"), env.get("SCENARIO_API_SECRET"), environ={})
client = ScenarioClient(creds.key, creds.secret)
tmp = pathlib.Path(tempfile.mkdtemp(prefix="scenario-smoke-3d-"))
paths = config.Paths(state_dir=tmp / "state", cache_dir=tmp / "cache", output_dir=tmp / "out")
catalog = Catalog(client, paths.cache_dir)
asset_id = assets.upload_file(client, image, kind="image")
print("reference asset:", asset_id)
# free dry runs: multi-view models with two views (same image twice, only the price and the body shape matter)
for model_id, param in (("model_meshy-7-multi-image-to-3d", "images"), ("model_tripo-v3-1-multiview-to-3d", None)):
    try:
        rec = catalog.get(model_id)
        schema = parse_schema(rec)
        file_specs = [s for s in schema.specs if s.is_file]
        target = param if param and schema.by_name(param) else (file_specs[0].name if file_specs else None)
        spec = schema.by_name(target)
        files = {target: [asset_id, asset_id] if spec.ptype == "file_array" else [asset_id]}
        body = build_body(schema.specs, {}, files)
        errs = validate(schema.specs, body)
        quote = estimate(client, rec.id, body) if not errs else None
        print(f"multi-view dry run {model_id}: params={[s.name for s in file_specs]} body_keys={sorted(body)} errors={errs} quote={quote.cu_cost if quote else None} CU")
    except ScenarioError as err:
        print(f"multi-view dry run {model_id}: {err}")
# the paid run: Tripo 3.1 image to 3D
rec = catalog.get("model_tripo-v3-1-image-to-3d")
schema = parse_schema(rec)
image_spec = next(s for s in schema.specs if s.is_file)
body = build_body(schema.specs, {"texture": True, "pbr": True}, files={image_spec.name: [asset_id]})
print("tripo body:", body, "errors:", validate(schema.specs, body))
quote = estimate(client, rec.id, body)
print("tripo dry run:", quote.cu_cost, "CU")
if quote.cu_cost > MAX_CU:
    sys.exit(f"quote above {MAX_CU} CU, not submitted")
manager = JobManager(lambda: client, JobRegistry(paths.registry_file), paths)
job = manager.submit("3d", "3d", rec.id, body)
deadline = time.time() + 900
while time.time() < deadline:
    for name, payload in manager.drain():
        if name in ("job_done", "job_failed"):
            print(name, payload.status, "cu:", payload.cu_cost, "error:", payload.error)
            for f in payload.files:
                print("  file:", os.path.basename(f), os.path.getsize(f), "B", payload.asset_types.get(next((a for a in payload.asset_ids if True), ""), ""))
            primary, alternates = placement.pick_primary_mesh(payload.files)
            print("primary:", primary and os.path.basename(primary), "| summary:", placement.glb_summary(primary) if primary else None, "| alternates:", [os.path.basename(a) for a in alternates])
            print("OUT_DIR", paths.output_for("3d"))
            sys.exit(0 if name == "job_done" and primary else 1)
    time.sleep(3)
sys.exit("timeout")
