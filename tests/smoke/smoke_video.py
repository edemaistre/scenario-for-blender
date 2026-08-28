# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end smoke: a real Blender playblast through Seedance 2.0 (no Blender needed). Spends credits.

Gate: the dry run must quote at most MAX_CU, otherwise nothing is submitted.
Usage: SCENARIO_SMOKE=1 python3 tests/smoke/smoke_video.py
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
from scenario.core.api.generate import estimate  # noqa: E402
from scenario.core.jobs.manager import JobManager  # noqa: E402
from scenario.core.jobs.records import JobRegistry  # noqa: E402
from scenario.core.schema.params import build_body, parse_schema, validate  # noqa: E402
from scenario.core.scene import capture_plan  # noqa: E402

MAX_CU = 150
if os.environ.get("SCENARIO_SMOKE") != "1":
    sys.exit("set SCENARIO_SMOKE=1 to spend credits")
env = config.load_dotenv(ROOT / ".env.local")
creds = config.resolve_credentials(env.get("SCENARIO_API_KEY"), env.get("SCENARIO_API_SECRET"), environ={})
client = ScenarioClient(creds.key, creds.secret)
tmp = pathlib.Path(tempfile.mkdtemp(prefix="scenario-smoke-video-"))
paths = config.Paths(state_dir=tmp / "state", cache_dir=tmp / "cache", output_dir=tmp / "out")
record = Catalog(client, paths.cache_dir).get("model_bytedance-seedance-2-0")
schema = parse_schema(record)
clip = ROOT / "tests" / "fixtures" / "smoke" / "playblast_72f.mp4"  # 3 s at 24 fps: Seedance needs at least 2 s
print("uploading playblast", clip.stat().st_size, "bytes")
clip_asset = assets.upload_file(client, clip, kind="video")
print("clip asset:", clip_asset)
prompt = capture_plan.render_to_real_prompt("a copper teapot on a wooden table, the camera slowly pushes in", force_clay=True)
prompt = prompt.replace("@image1", "the description").replace("in the style of the description", "as a photoreal product shot")
body = build_body(schema.specs, {"prompt": prompt, "duration": 4, "resolution": "480p", "generateAudio": False}, files={"referenceVideos": [clip_asset]})
errors = validate(schema.specs, body)
print("validation:", errors or "ok")
quote = estimate(client, record.id, body)
print("dry run:", quote.cu_cost, "CU", quote.details)
if quote.cu_cost > MAX_CU:
    sys.exit(f"quote {quote.cu_cost} CU above the {MAX_CU} CU gate, not submitted")
manager = JobManager(lambda: client, JobRegistry(paths.registry_file), paths)
rec = manager.submit("video", "video", record.id, body)
deadline = time.time() + 900
while time.time() < deadline:
    for name, payload in manager.drain():
        if name == "job":
            print("status", payload.status, int(payload.progress * 100), "%")
        if name in ("job_done", "job_failed"):
            print(name, payload.status, "cu:", payload.cu_cost, "error:", payload.error, "files:", payload.files)
            sys.exit(0 if name == "job_done" else 1)
    time.sleep(3)
sys.exit("timeout")
