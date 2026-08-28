# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end smoke: one 512 px Patina material through the core (no Blender). Spends credits.

Usage: SCENARIO_SMOKE=1 python3 tests/smoke/smoke_material.py
"""
import os
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scenario.core import config  # noqa: E402
from scenario.core.api.catalog import Catalog  # noqa: E402
from scenario.core.api.client import ScenarioClient  # noqa: E402
from scenario.core.jobs.manager import JobManager  # noqa: E402
from scenario.core.jobs.records import JobRegistry  # noqa: E402
from scenario.core.schema.params import build_body, parse_schema  # noqa: E402
from scenario.core.scene import material_plan  # noqa: E402

if os.environ.get("SCENARIO_SMOKE") != "1":
    sys.exit("set SCENARIO_SMOKE=1 to spend credits")
env = config.load_dotenv(ROOT / ".env.local")
creds = config.resolve_credentials(env.get("SCENARIO_API_KEY"), env.get("SCENARIO_API_SECRET"), environ={})
client = ScenarioClient(creds.key, creds.secret)
tmp = pathlib.Path(tempfile.mkdtemp(prefix="scenario-smoke-material-"))
paths = config.Paths(state_dir=tmp / "state", cache_dir=tmp / "cache", output_dir=tmp / "out")
catalog = Catalog(client, paths.cache_dir)
record = catalog.get("model_patina-material")
schema = parse_schema(record)
body = build_body(schema.specs, {"prompt": "mossy stone wall", "width": 512, "height": 512, "numOutputs": 1}, files={})
manager = JobManager(lambda: client, JobRegistry(paths.registry_file), paths)
manager.estimate("smoke", record.id, body)
manager.join(timeout=30)
print("estimate:", [(e[1].cu_cost, e[1].error) for e in manager.drain() if e[0] == "estimate"])
rec = manager.submit("material", "material", record.id, body)
deadline = time.time() + 400
while time.time() < deadline:
    for name, payload in manager.drain():
        if name in ("job_done", "job_failed"):
            print(name, payload.status, "cu:", payload.cu_cost, "error:", payload.error)
            print("files:", len(payload.files), "types:", sorted(payload.asset_types.values()))
            plan = material_plan.plan_material("smoke", material_plan.roles_from_record(payload))
            print("plan roles:", sorted(plan.textures), "invert smoothness:", plan.invert_smoothness)
            print("output dir:", paths.output_for("material"))
            sys.exit(0 if name == "job_done" and len(payload.files) == 6 else 1)
    time.sleep(1)
sys.exit("timeout")
