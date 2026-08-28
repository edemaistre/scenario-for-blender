# Scenario for Blender P0 Implementation Plan (skeleton + Image lane)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A pure-Python Blender 4.2+ extension `scenario` that authenticates with a Scenario API key, lists models, renders a schema-driven Image lane in the N-panel with a live CU cost preview, submits generations through a non-blocking job manager, downloads results and loads them into Blender.

**Architecture:** `scenario/core/*` is plain Python (no `bpy`), tested with pytest and a fake HTTP transport. `scenario/blender/*` is the Blender glue: preferences, property groups, panels, operators, one `bpy.app.timers` pump that drains a thread-safe event queue filled by worker threads (HTTP, polling, downloads). Model records from `GET /v1/models/{id}` drive the parameter UI.

**Tech Stack:** Blender 4.2+ (tested on 5.1.1, Python 3.13), stdlib only (`urllib`, `ssl`, `json`, `threading`, `queue`), pytest for unit tests, Blender `--background` for integration tests, `blender --command extension build|validate|install-file` for packaging.

**Spec:** `docs/superpowers/specs/2026-08-28-scenario-for-blender-design.md`

## Global Constraints

- Extension id `scenario`, name `Scenario`, `blender_version_min = "4.2.0"`, licence `SPDX:GPL-3.0-or-later`, pure Python, no wheels.
- Every source file starts with `# SPDX-FileCopyrightText: 2026 Scenario Inc.` and `# SPDX-License-Identifier: GPL-3.0-or-later`.
- `bpy` only on the main thread. Workers never import `bpy`. `scenario/core/**` never imports `bpy`.
- No em dashes in any text (code, docs, UI strings).
- `dryRun` is a QUERY parameter (`?dryRun=true`). Never put `dryRun` in the body.
- Never write inside the add-on directory; state and caches go under `bpy.utils.extension_path_user(__package__, path=..., create=True)`.
- Check `bpy.app.online_access` before any network action in the UI.
- Never `rm`: move superseded files to `archive/`. Version deliverables before overwriting.
- Dev credentials live in git-ignored `.env.local` (`SCENARIO_API_KEY`, `SCENARIO_API_SECRET`, `SCENARIO_TEAM_ID`, `SCENARIO_PROJECT_ID`). Never print them. Paid calls only in explicitly opt-in smoke steps; dev cap about $30.
- Blender binary: `/Applications/Blender.app/Contents/MacOS/Blender` (5.1.1). Use `BLENDER` env var to override.
- Work on branch `p0-skeleton-image-lane`; merge into `main` with `git merge --no-ff` at the end of Task 11. Commit after every task.

---

### Task 1: Project scaffold, manifest, build and test harnesses

**Files:**
- Create: `scenario/blender_manifest.toml`
- Create: `scenario/__init__.py`
- Create: `scenario/core/__init__.py`, `scenario/core/api/__init__.py`, `scenario/core/schema/__init__.py`, `scenario/core/jobs/__init__.py`, `scenario/blender/__init__.py`
- Create: `scenario/blender/registry.py`
- Create: `tests/unit/conftest.py`, `tests/unit/test_package.py`
- Create: `pytest.ini`, `Makefile`, `tools/build.sh`, `tools/install_dev.sh`
- Modify: `.gitignore` (add `dist/`)

**Interfaces:**
- Produces: package `scenario` importable in plain Python (`import scenario.core` never imports bpy); `scenario.register()` / `scenario.unregister()` delegate to `scenario.blender.registry`.

- [ ] **Step 1: Create the branch and the failing unit test**

```bash
cd "/Users/emmanuel/Developer/pro/2026-02-05 Blender Plugin" && git checkout -b p0-skeleton-image-lane
```

`tests/unit/conftest.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Make the repo root importable so `import scenario.core...` works without Blender."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures"
```

`tests/unit/test_package.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import sys


def test_core_imports_without_bpy():
    import scenario  # noqa: F401
    import scenario.core  # noqa: F401

    assert "bpy" not in sys.modules
    assert callable(scenario.register)
    assert callable(scenario.unregister)
```

`pytest.ini`:
```ini
[pytest]
testpaths = tests/unit
addopts = -q
```

- [ ] **Step 2: Run the test to see it fail**

Run: `cd "/Users/emmanuel/Developer/pro/2026-02-05 Blender Plugin" && python3 -m pytest tests/unit/test_package.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scenario'` (install pytest first if missing: `python3 -m pip install --user pytest`).

- [ ] **Step 3: Create the package**

`scenario/blender_manifest.toml`:
```toml
schema_version = "1.0.0"

id = "scenario"
version = "0.1.0"
name = "Scenario"
tagline = "AI images, video, 3D and PBR materials from Scenario"
maintainer = "Scenario Inc. <support@scenario.com>"
type = "add-on"
website = "https://scenario.com"
tags = ["3D View", "Material", "Import-Export"]
blender_version_min = "4.2.0"
license = ["SPDX:GPL-3.0-or-later"]
copyright = ["2026 Scenario Inc."]

[permissions]
network = "Generate with your Scenario account (api.cloud.scenario.com)"
files = "Save generated media to disk and import it into the scene"

[build]
paths_exclude_pattern = [
  "__pycache__/",
  "/.git/",
  "/*.zip",
  ".DS_Store",
]
```

`scenario/__init__.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Scenario for Blender.

Entry point of the extension. Imports of bpy stay inside register/unregister
so that `scenario.core` is importable from plain Python (unit tests, tooling).
"""

__version__ = "0.1.0"


def register():
    from .blender import registry

    registry.register()


def unregister():
    from .blender import registry

    registry.unregister()
```

Each of `scenario/core/__init__.py`, `scenario/core/api/__init__.py`, `scenario/core/schema/__init__.py`, `scenario/core/jobs/__init__.py`, `scenario/blender/__init__.py` contains only:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
```

`scenario/blender/registry.py` (placeholder wiring, extended in Task 8):
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Registers every Blender class of the extension in dependency order."""
import logging

log = logging.getLogger("scenario")


def register():
    log.info("Scenario for Blender registered")


def unregister():
    log.info("Scenario for Blender unregistered")
```

`tools/build.sh`:
```bash
#!/bin/zsh
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
# Build and validate the extension zip with Blender's own CLI.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BLENDER="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
mkdir -p "$ROOT/dist"
"$BLENDER" --command extension build --source-dir "$ROOT/scenario" --output-dir "$ROOT/dist"
ZIP="$(ls -t "$ROOT"/dist/scenario-*.zip | head -1)"
"$BLENDER" --command extension validate "$ZIP"
echo "built $ZIP"
```

`tools/install_dev.sh`:
```bash
#!/bin/zsh
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
# Build, then install into the local user_default repository and enable it.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BLENDER="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
"$ROOT/tools/build.sh"
ZIP="$(ls -t "$ROOT"/dist/scenario-*.zip | head -1)"
"$BLENDER" --command extension install-file --repo user_default --enable "$ZIP"
echo "installed $ZIP into user_default (restart running Blender instances)"
```

`Makefile`:
```make
BLENDER ?= /Applications/Blender.app/Contents/MacOS/Blender

.PHONY: test test-blender build install
test:
	python3 -m pytest
test-blender:
	$(BLENDER) --background --python-exit-code 1 --python tests/blender/run_all.py
build:
	./tools/build.sh
install:
	./tools/install_dev.sh
```

Append to `.gitignore`: `dist/`. Then `chmod +x tools/*.sh`.

- [ ] **Step 4: Run the unit test and the build**

Run: `python3 -m pytest tests/unit/test_package.py -v` Expected: PASS.
Run: `./tools/build.sh` Expected: last lines contain `valid` (validate prints nothing on success in some versions; the script echoes `built .../scenario-0.1.0.zip`). If `install-file --enable` is rejected later, run `$BLENDER --command extension install-file --help` and drop the unsupported flag.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: extension scaffold, manifest, build and test harnesses"
```

---

### Task 2: REST client with Basic auth, retries and typed errors

**Files:**
- Create: `scenario/core/api/errors.py`, `scenario/core/api/transport.py`, `scenario/core/api/client.py`
- Test: `tests/unit/fakes.py`, `tests/unit/test_client.py`

**Interfaces:**
- Produces: `ScenarioError(status, reason, trace_id=None, body=None, path=None)`, `NetworkError(ScenarioError)`; `Transport.request(method, url, headers, body, timeout) -> (status, headers, bytes)`; `ScenarioClient(key, secret, base_url=..., transport=None, user_agent=..., sleep=time.sleep, max_retries=3)` with `.request(method, path, query=None, json_body=None, timeout=60, retries=None) -> dict`, `.get(path, **kw)`, `.post(path, **kw)`, `.put(path, **kw)`.

- [ ] **Step 1: Write the fake transport and failing tests**

`tests/unit/fakes.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fake HTTP transport: records requests, replays queued responses."""
import json
from collections import deque


class FakeTransport:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = deque(responses or [])
        self.raise_network = 0  # number of NetworkErrors to raise before serving

    def queue(self, status, body, headers=None):
        raw = body if isinstance(body, (bytes, bytearray)) else json.dumps(body).encode()
        self.responses.append((status, headers or {}, bytes(raw)))
        return self

    def request(self, method, url, headers, body, timeout=None):
        from scenario.core.api.errors import NetworkError

        self.calls.append({"method": method, "url": url, "headers": dict(headers), "body": body, "timeout": timeout})
        if self.raise_network:
            self.raise_network -= 1
            raise NetworkError(0, "network: fake failure")
        if not self.responses:
            raise AssertionError(f"no fake response queued for {method} {url}")
        return self.responses.popleft()

    def last_json(self):
        return json.loads(self.calls[-1]["body"])
```

`tests/unit/test_client.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import base64

import pytest

from fakes import FakeTransport
from scenario.core.api.client import ScenarioClient
from scenario.core.api.errors import NetworkError, ScenarioError


def make(transport, **kw):
    sleeps = []
    client = ScenarioClient("api_key", "secret", transport=transport, sleep=sleeps.append, **kw)
    return client, sleeps


def test_get_sends_basic_auth_and_query():
    t = FakeTransport().queue(200, {"models": []})
    client, _ = make(t)
    out = client.get("/models", query={"pageSize": 1, "privacy": "public"})
    assert out == {"models": []}
    call = t.calls[0]
    expected = "Basic " + base64.b64encode(b"api_key:secret").decode()
    assert call["headers"]["Authorization"] == expected
    assert call["method"] == "GET"
    assert call["url"] == "https://api.cloud.scenario.com/v1/models?pageSize=1&privacy=public"
    assert call["body"] is None


def test_post_sends_json_body_and_content_type():
    t = FakeTransport().queue(200, {"job": {"jobId": "job_1"}})
    client, _ = make(t)
    client.post("/generate/custom/model_x", json_body={"prompt": "hi", "numOutputs": 1})
    call = t.calls[0]
    assert call["headers"]["Content-Type"] == "application/json"
    assert t.last_json() == {"prompt": "hi", "numOutputs": 1}


def test_dry_run_status_269_is_success():
    t = FakeTransport().queue(269, {"creativeUnitsCost": 7.25})
    client, _ = make(t)
    assert client.post("/generate/custom/m", query={"dryRun": "true"}, json_body={})["creativeUnitsCost"] == 7.25
    assert t.calls[0]["url"].endswith("?dryRun=true")


def test_error_maps_reason_and_trace_id():
    t = FakeTransport().queue(400, {"reason": "Input prompt is required", "trace_id": "tr_1"})
    client, _ = make(t)
    with pytest.raises(ScenarioError) as exc:
        client.post("/generate/custom/m", json_body={})
    assert exc.value.status == 400
    assert exc.value.reason == "Input prompt is required"
    assert exc.value.trace_id == "tr_1"
    assert exc.value.path == "/generate/custom/m"


def test_403_message_field_is_used_as_reason():
    t = FakeTransport().queue(403, {"message": "API Keys cannot access protected resources"})
    client, _ = make(t)
    with pytest.raises(ScenarioError) as exc:
        client.get("/me")
    assert "protected resources" in exc.value.reason


def test_retries_on_503_then_succeeds():
    t = FakeTransport().queue(503, {"message": "busy"}).queue(200, {"ok": True})
    client, sleeps = make(t)
    assert client.get("/models") == {"ok": True}
    assert len(t.calls) == 2
    assert sleeps == [1.0]


def test_429_uses_remaining_seconds_capped():
    t = FakeTransport().queue(429, {"reason": "cooldown", "remainingSeconds": 900}).queue(200, {"ok": True})
    client, sleeps = make(t)
    client.get("/models")
    assert sleeps == [30.0]


def test_network_error_after_retries():
    t = FakeTransport()
    t.raise_network = 10
    client, sleeps = make(t, max_retries=2)
    with pytest.raises(NetworkError):
        client.get("/models")
    assert len(t.calls) == 3
    assert sleeps == [1.0, 2.0]


def test_non_json_body_becomes_reason_text():
    t = FakeTransport().queue(502, b"<html>Bad gateway</html>")
    client, _ = make(t, max_retries=0)
    with pytest.raises(ScenarioError) as exc:
        client.get("/models")
    assert "Bad gateway" in exc.value.reason
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/unit/test_client.py -v` Expected: FAIL with `ModuleNotFoundError: No module named 'scenario.core.api.client'`.

- [ ] **Step 3: Implement errors, transport and client**

`scenario/core/api/errors.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Typed errors raised by the Scenario REST client."""


class ScenarioError(Exception):
    """An HTTP-level or API-level failure. `status` is 0 for network failures."""

    def __init__(self, status, reason, *, trace_id=None, body=None, path=None):
        self.status = int(status)
        self.reason = str(reason)
        self.trace_id = trace_id
        self.body = body
        self.path = path
        suffix = f" (trace {trace_id})" if trace_id else ""
        super().__init__(f"{self.status} {self.reason}{suffix}")

    @property
    def is_auth(self):
        return self.status in (401, 403)


class NetworkError(ScenarioError):
    """DNS, TLS, timeout or connection failure. Retried by the client."""
```

`scenario/core/api/transport.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""HTTP transport over urllib. Never imports bpy. Runs in worker threads."""
import urllib.error
import urllib.request

from .errors import NetworkError


class UrllibTransport:
    """request(method, url, headers, body, timeout) -> (status, headers, bytes).

    HTTP error statuses are returned, not raised, so the client can decode the
    JSON error body. Only connection-level failures raise NetworkError.
    """

    def __init__(self, timeout=60):
        self.timeout = timeout

    def request(self, method, url, headers, body, timeout=None):
        req = urllib.request.Request(url, data=body, method=method, headers=dict(headers))
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                return resp.status, dict(resp.headers.items()), resp.read()
        except urllib.error.HTTPError as err:
            raw = err.read() if hasattr(err, "read") else b""
            return err.code, dict(err.headers.items()) if err.headers else {}, raw
        except OSError as err:  # URLError, timeouts, TLS and socket errors
            raise NetworkError(0, f"network: {err}") from err
```

`scenario/core/api/client.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Scenario REST client: Basic auth, JSON, query params, bounded retries."""
import base64
import json
import time
import urllib.parse

from .errors import NetworkError, ScenarioError
from .transport import UrllibTransport

DEFAULT_BASE_URL = "https://api.cloud.scenario.com/v1"
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_429_WAIT = 30.0


def _encode_query(query):
    items = []
    for key, value in query.items():
        if value is None:
            continue
        if isinstance(value, bool):
            value = "true" if value else "false"
        items.append((key, value))
    return urllib.parse.urlencode(items, doseq=True)


class ScenarioClient:
    def __init__(self, key, secret, *, base_url=DEFAULT_BASE_URL, transport=None,
                 user_agent="ScenarioBlender/0.1.0", sleep=time.sleep, max_retries=3):
        token = base64.b64encode(f"{key}:{secret}".encode("utf-8")).decode("ascii")
        self._auth = f"Basic {token}"
        self.base_url = base_url.rstrip("/")
        self.transport = transport or UrllibTransport()
        self.user_agent = user_agent
        self.sleep = sleep
        self.max_retries = max_retries

    # -- public helpers -------------------------------------------------
    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, **kw):
        return self.request("POST", path, **kw)

    def put(self, path, **kw):
        return self.request("PUT", path, **kw)

    def url(self, path, query=None):
        full = f"{self.base_url}/{path.lstrip('/')}"
        if query:
            encoded = _encode_query(query)
            if encoded:
                full = f"{full}?{encoded}"
        return full

    # -- core -----------------------------------------------------------
    def request(self, method, path, *, query=None, json_body=None, timeout=60, retries=None):
        url = self.url(path, query)
        body = json.dumps(json_body).encode("utf-8") if json_body is not None else None
        headers = {"Authorization": self._auth, "Accept": "application/json", "User-Agent": self.user_agent}
        if body is not None:
            headers["Content-Type"] = "application/json"
        attempts = self.max_retries if retries is None else retries
        delay = 1.0
        attempt = 0
        while True:
            try:
                status, _resp_headers, raw = self.transport.request(method, url, headers, body, timeout)
            except NetworkError:
                if attempt >= attempts:
                    raise
                self.sleep(delay)
                delay *= 2
                attempt += 1
                continue
            data = self._decode(raw)
            if status in RETRY_STATUSES and attempt < attempts:
                self.sleep(self._retry_delay(status, data, delay))
                delay *= 2
                attempt += 1
                continue
            if 200 <= status < 300:
                return data
            raise ScenarioError(status, self._reason(data, raw), trace_id=self._trace_id(data), body=data, path=path)

    @staticmethod
    def _decode(raw):
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {"_raw": raw.decode("utf-8", errors="replace")}

    @staticmethod
    def _reason(data, raw):
        if isinstance(data, dict):
            for key in ("reason", "message", "error", "detail"):
                value = data.get(key)
                if value:
                    return str(value)
            if "_raw" in data:
                return data["_raw"][:300]
            return json.dumps(data)[:300]
        return raw.decode("utf-8", errors="replace")[:300]

    @staticmethod
    def _trace_id(data):
        if isinstance(data, dict):
            return data.get("trace_id") or data.get("traceId")
        return None

    @staticmethod
    def _retry_delay(status, data, default):
        if status == 429 and isinstance(data, dict):
            remaining = data.get("remainingSeconds")
            if isinstance(remaining, (int, float)) and remaining > 0:
                return float(min(remaining, MAX_429_WAIT))
        return default
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/unit/test_client.py -v` Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(core): REST client with Basic auth, retries and typed errors"
```

---

### Task 3: Credentials, paths and output filenames

**Files:**
- Create: `scenario/core/config.py`
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Produces: `Credentials(key, secret).valid`; `resolve_credentials(pref_key, pref_secret, environ=os.environ) -> Credentials`; `load_dotenv(path) -> dict`; `Paths(state_dir, cache_dir, output_dir)` with `.models_cache_dir`, `.registry_file`, `.output_for(kind)`; `KIND_SUBDIR`; `ext_for_mime(mime) -> str`; `output_filename(kind, model_id, job_id, index, ext, when=None) -> str`; `slug(text, limit=40) -> str`.

- [ ] **Step 1: Write failing tests**

`tests/unit/test_config.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import datetime as dt
import pathlib

from scenario.core import config


def test_env_overrides_prefs():
    creds = config.resolve_credentials("pref_key", "pref_secret", environ={"SCENARIO_API_KEY": " env_key ", "SCENARIO_API_SECRET": "env_secret"})
    assert creds.key == "env_key" and creds.secret == "env_secret" and creds.valid


def test_prefs_used_when_env_missing_and_invalid_when_empty():
    assert config.resolve_credentials("k", "s", environ={}).valid
    assert not config.resolve_credentials("", "s", environ={}).valid
    assert not config.resolve_credentials(None, None, environ={}).valid


def test_load_dotenv(tmp_path):
    p = tmp_path / ".env.local"
    p.write_text("# comment\nSCENARIO_API_KEY=abc\nSCENARIO_API_SECRET='quoted'\nEMPTY=\n")
    assert config.load_dotenv(p) == {"SCENARIO_API_KEY": "abc", "SCENARIO_API_SECRET": "quoted", "EMPTY": ""}
    assert config.load_dotenv(tmp_path / "missing") == {}


def test_paths_layout(tmp_path):
    paths = config.Paths(state_dir=tmp_path / "state", cache_dir=tmp_path / "cache", output_dir=tmp_path / "out")
    assert paths.models_cache_dir == tmp_path / "cache" / "models"
    assert paths.registry_file == tmp_path / "state" / "jobs.json"
    assert paths.output_for("image") == tmp_path / "out" / "images"
    assert paths.output_for("3d") == tmp_path / "out" / "3d"
    assert paths.output_for("material") == tmp_path / "out" / "materials"
    assert paths.output_for("weird") == tmp_path / "out" / "other"


def test_ext_for_mime():
    assert config.ext_for_mime("image/png") == "png"
    assert config.ext_for_mime("model/gltf-binary") == "glb"
    assert config.ext_for_mime("video/mp4") == "mp4"
    assert config.ext_for_mime("application/x-unknown") == "bin"
    assert config.ext_for_mime(None) == "bin"


def test_output_filename_is_readable_and_unique():
    when = dt.datetime(2026, 8, 28, 9, 30, 5)
    name = config.output_filename("image", "model_patina-material", "job_KWxxsnSdVXDFZRMsoCvLTmKY", 2, "png", when=when)
    assert name == "20260828_093005_patina-material_soCvLTmKY_02.png"
    assert config.slug("model_Google Gemini 3.1 🍌", limit=12) == "google-gemin"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/unit/test_config.py -v` Expected: FAIL (`cannot import name 'config'`).

- [ ] **Step 3: Implement**

`scenario/core/config.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Credentials, filesystem layout and output naming. No bpy."""
import datetime as dt
import os
import pathlib
import re
from dataclasses import dataclass

KIND_SUBDIR = {"image": "images", "video": "videos", "3d": "3d", "material": "materials"}

_MIME_EXT = {
    "image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/webp": "webp", "image/gif": "gif",
    "image/avif": "avif", "image/tiff": "tif", "video/mp4": "mp4", "video/webm": "webm",
    "model/gltf-binary": "glb", "model/gltf+json": "gltf", "model/x-fbx": "fbx", "model/obj": "obj",
    "model/x-3d-vox": "vox", "audio/mpeg": "mp3", "audio/wav": "wav", "audio/x-wav": "wav", "audio/ogg": "ogg",
    "application/octet-stream": "bin",
}


@dataclass(frozen=True)
class Credentials:
    key: str
    secret: str

    @property
    def valid(self):
        return bool(self.key and self.secret)


def resolve_credentials(pref_key, pref_secret, environ=None):
    environ = os.environ if environ is None else environ
    key = (environ.get("SCENARIO_API_KEY") or pref_key or "").strip()
    secret = (environ.get("SCENARIO_API_SECRET") or pref_secret or "").strip()
    return Credentials(key, secret)


def load_dotenv(path):
    """Minimal KEY=VALUE parser for dev scripts and tests. Never logs values."""
    path = pathlib.Path(path)
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[key.strip()] = value
    return out


@dataclass(frozen=True)
class Paths:
    state_dir: pathlib.Path
    cache_dir: pathlib.Path
    output_dir: pathlib.Path

    @property
    def models_cache_dir(self):
        return self.cache_dir / "models"

    @property
    def registry_file(self):
        return self.state_dir / "jobs.json"

    def output_for(self, kind):
        return self.output_dir / KIND_SUBDIR.get(kind, "other")


def ext_for_mime(mime):
    if not mime:
        return "bin"
    return _MIME_EXT.get(mime.split(";")[0].strip().lower(), "bin")


def slug(text, limit=40):
    text = str(text or "")
    if text.startswith("model_"):
        text = text[len("model_"):]
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text[:limit].rstrip("-") or "model"


def output_filename(kind, model_id, job_id, index, ext, when=None):
    when = when or dt.datetime.now()
    short_job = (job_id or "job")[-9:]
    return f"{when:%Y%m%d_%H%M%S}_{slug(model_id)}_{short_job}_{index:02d}.{ext}"
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/unit/test_config.py -v` Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(core): credentials resolution, paths and output naming"
```

---

### Task 4: Model catalog with disk cache, pagination and lane filters (plus recorded fixtures)

**Files:**
- Create: `scenario/core/api/catalog.py`
- Create: `tools/record_fixtures.py`
- Create: `tests/fixtures/models/*.json`, `tests/fixtures/models_list_page1.json`, copy `research/fixtures/patina-copper-512/` to `tests/fixtures/patina-copper-512/`
- Test: `tests/unit/test_catalog.py`

**Interfaces:**
- Consumes: `ScenarioClient.get`.
- Produces: `ModelRecord` (fields `id, name, short_description, capabilities, tags, type, status, privacy, raw`; properties `parameters`, `ui_config`, `deprecated_successor`, `lanes`); `Catalog(client, cache_dir)` with `fetch_list(privacy="public", page_size=100, max_pages=20) -> list[ModelRecord]`, `load_list_cached(privacy) -> list[ModelRecord] | None`, `get(model_id, refresh=False) -> ModelRecord`, `models_for_lane(lane, records) -> list[ModelRecord]`; constants `LANE_CAPS`, `PATINA_MODELS`, `DEFAULT_MODELS`, `GENERATION_LANES = ("image", "video", "3d", "material")`.

- [ ] **Step 1: Record fixtures from the live API (free GET calls)**

`tools/record_fixtures.py`:
```python
#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Record REST fixtures used by unit tests. Reads .env.local, never prints secrets.

Usage: python3 tools/record_fixtures.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scenario.core import config  # noqa: E402
from scenario.core.api.client import ScenarioClient  # noqa: E402

MODEL_IDS = [
    "model_patina-material", "model_patina", "model_patina-material-extract",
    "model_openai-gpt-image-2", "model_google-gemini-3-1-flash", "model_bytedance-seedance-2-0",
    "model_meshy-7-img23d", "model_meshy-7-txt23d", "model_tripo-v3-1-image-to-3d",
]


def main():
    env = config.load_dotenv(ROOT / ".env.local")
    creds = config.resolve_credentials(env.get("SCENARIO_API_KEY"), env.get("SCENARIO_API_SECRET"), environ={})
    if not creds.valid:
        sys.exit("no credentials in .env.local")
    client = ScenarioClient(creds.key, creds.secret)
    out = ROOT / "tests" / "fixtures" / "models"
    out.mkdir(parents=True, exist_ok=True)
    for model_id in MODEL_IDS:
        data = client.get(f"/models/{model_id}")
        (out / f"{model_id}.json").write_text(json.dumps(data, indent=1))
        print("saved", model_id)
    page1 = client.get("/models", query={"privacy": "public", "pageSize": 5})
    (ROOT / "tests" / "fixtures" / "models_list_page1.json").write_text(json.dumps(page1, indent=1))
    token = page1.get("nextPaginationToken")
    page2 = client.get("/models", query={"privacy": "public", "pageSize": 5, "paginationToken": token})
    first1 = page1["models"][0]["id"]
    first2 = page2["models"][0]["id"] if page2.get("models") else None
    print("pagination param 'paginationToken' works:", first1 != first2)
    if first1 == first2:
        page2b = client.get("/models", query={"privacy": "public", "pageSize": 5, "pageToken": token})
        print("fallback 'pageToken' works:", page2b["models"][0]["id"] != first1)


if __name__ == "__main__":
    main()
```

Run: `python3 tools/record_fixtures.py` and `cp -R research/fixtures/patina-copper-512 tests/fixtures/`. Read the printed pagination line: if `paginationToken` did not work but `pageToken` did, set `PAGE_TOKEN_PARAM = "pageToken"` in Step 3, otherwise keep `"paginationToken"`.

- [ ] **Step 2: Write failing tests**

`tests/unit/test_catalog.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json

from conftest import FIXTURES
from fakes import FakeTransport
from scenario.core.api.catalog import Catalog, ModelRecord, models_for_lane
from scenario.core.api.client import ScenarioClient


def load(name):
    return json.loads((FIXTURES / "models" / f"{name}.json").read_text())


def test_model_record_from_api_reads_schema_and_lanes():
    rec = ModelRecord.from_api(load("model_patina-material")["model"])
    assert rec.id == "model_patina-material"
    assert "txt2img" in rec.capabilities
    assert len(rec.parameters) == 15
    assert rec.ui_config["selects"]["maps"]["basecolor"] == "Base Color"
    assert rec.lanes == {"image", "material"}
    assert rec.deprecated_successor is None


def test_deprecated_tag_names_successor():
    rec = ModelRecord.from_api({"id": "model_old", "name": "Old", "capabilities": ["img23d"], "tags": ["deprecated:model_new"]})
    assert rec.deprecated_successor == "model_new"
    assert rec.lanes == {"3d"}


def test_fetch_list_paginates_and_caches(tmp_path):
    page1 = json.loads((FIXTURES / "models_list_page1.json").read_text())
    t = FakeTransport().queue(200, page1).queue(200, {"models": [{"id": "model_last", "name": "Last", "capabilities": ["txt2video"]}]})
    catalog = Catalog(ScenarioClient("k", "s", transport=t), tmp_path)
    records = catalog.fetch_list(privacy="public", page_size=5)
    assert len(records) == len(page1["models"]) + 1
    assert "pageSize=5" in t.calls[0]["url"] and "privacy=public" in t.calls[0]["url"]
    assert page1["nextPaginationToken"] in t.calls[1]["url"]
    cached = catalog.load_list_cached("public")
    assert [r.id for r in cached] == [r.id for r in records]
    assert catalog.load_list_cached("private") is None


def test_get_uses_disk_cache_then_refreshes(tmp_path):
    payload = load("model_patina-material")
    t = FakeTransport().queue(200, payload).queue(200, payload)
    catalog = Catalog(ScenarioClient("k", "s", transport=t), tmp_path)
    rec = catalog.get("model_patina-material")
    assert rec.name == "PATINA Material"
    assert (tmp_path / "models" / "model_patina-material.json").exists()
    catalog.get("model_patina-material")
    assert len(t.calls) == 1
    catalog.get("model_patina-material", refresh=True)
    assert len(t.calls) == 2


def test_models_for_lane_orders_curated_first_and_drops_deprecated():
    records = [
        ModelRecord.from_api({"id": "model_zeta", "name": "Zeta", "capabilities": ["txt2img"]}),
        ModelRecord.from_api({"id": "model_google-gemini-3-1-flash", "name": "Gemini", "capabilities": ["txt2img", "img2img"]}),
        ModelRecord.from_api({"id": "model_old", "name": "Old", "capabilities": ["txt2img"], "tags": ["deprecated:model_zeta"]}),
        ModelRecord.from_api({"id": "model_video", "name": "Vid", "capabilities": ["txt2video"]}),
        ModelRecord.from_api({"id": "model_patina", "name": "Patina maps", "capabilities": ["img2img"]}),
    ]
    image = [r.id for r in models_for_lane("image", records)]
    assert image[0] == "model_google-gemini-3-1-flash"
    assert "model_old" not in image and "model_video" not in image
    assert image[-1] == "model_zeta"
    assert [r.id for r in models_for_lane("material", records)] == ["model_patina"]
    assert [r.id for r in models_for_lane("video", records)] == ["model_video"]
```

- [ ] **Step 3: Run tests to verify they fail, then implement**

Run: `python3 -m pytest tests/unit/test_catalog.py -v` Expected: import failure.

`scenario/core/api/catalog.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Model catalog: fetch, cache on disk, filter by lane, curated ordering."""
import json
import pathlib
from dataclasses import dataclass, field

PAGE_TOKEN_PARAM = "paginationToken"

GENERATION_LANES = ("image", "video", "3d", "material")
LANE_CAPS = {
    "image": {"txt2img", "img2img"},
    "video": {"txt2video", "img2video", "video2video"},
    "3d": {"txt23d", "img23d"},
}
PATINA_MODELS = ("model_patina-material", "model_patina", "model_patina-material-extract")
DEFAULT_MODELS = {
    "image": ["model_openai-gpt-image-2", "model_google-gemini-3-1-flash", "model_bytedance-seedream-5-0-pro", "model_bytedance-seedream-5-0", "model_z-image"],
    "video": ["model_bytedance-seedance-2-0", "model_bytedance-seedance-2-5", "model_google-veo-3-1", "model_kling-3-0"],
    "3d": ["model_meshy-7-txt23d", "model_rodin-hyper3d-v2-5-text-to-3d", "model_tripo-v3-1-image-to-3d", "model_meshy-7-img23d", "model_hunyuan-3d-pro-3-1-i23d", "model_rodin-hyper3d-v2-5"],
    "material": list(PATINA_MODELS),
}


@dataclass
class ModelRecord:
    id: str
    name: str
    short_description: str = ""
    capabilities: tuple = ()
    tags: tuple = ()
    type: str = ""
    status: str = ""
    privacy: str = ""
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_api(cls, data):
        return cls(
            id=data.get("id", ""),
            name=data.get("name") or data.get("id", ""),
            short_description=data.get("shortDescription") or "",
            capabilities=tuple(c if isinstance(c, str) else c.get("type", "") for c in data.get("capabilities") or ()),
            tags=tuple(data.get("tags") or ()),
            type=data.get("type") or "",
            status=data.get("status") or "",
            privacy=data.get("privacy") or "",
            raw=dict(data),
        )

    @property
    def parameters(self):
        return list(self.raw.get("parameters") or self.raw.get("inputs") or [])

    @property
    def ui_config(self):
        return dict(self.raw.get("uiConfig") or {})

    @property
    def deprecated_successor(self):
        for tag in self.tags:
            if tag.startswith("deprecated:"):
                return tag.split(":", 1)[1] or None
        return None

    @property
    def lanes(self):
        caps = set(self.capabilities)
        lanes = {lane for lane, wanted in LANE_CAPS.items() if caps & wanted}
        if self.id in PATINA_MODELS:
            lanes.add("material")
        return lanes


def models_for_lane(lane, records):
    """Filter records usable in `lane`, deprecated models removed, curated models first."""
    curated = DEFAULT_MODELS.get(lane, [])
    rank = {model_id: index for index, model_id in enumerate(curated)}
    usable = [r for r in records if lane in r.lanes and r.deprecated_successor is None and r.status in ("", "trained")]
    if lane == "material":
        usable = [r for r in usable if r.id in PATINA_MODELS]
    return sorted(usable, key=lambda r: (rank.get(r.id, len(rank)), r.name.lower()))


class Catalog:
    def __init__(self, client, cache_dir):
        self.client = client
        self.cache_dir = pathlib.Path(cache_dir)

    # -- lists ------------------------------------------------------------
    def fetch_list(self, privacy="public", page_size=100, max_pages=20):
        records, token = [], None
        for _ in range(max_pages):
            query = {"privacy": privacy, "pageSize": page_size}
            if token:
                query[PAGE_TOKEN_PARAM] = token
            data = self.client.get("/models", query=query)
            records.extend(ModelRecord.from_api(m) for m in data.get("models") or [])
            token = data.get("nextPaginationToken")
            if not token:
                break
        self._write(self._list_file(privacy), [r.raw for r in records])
        return records

    def load_list_cached(self, privacy="public"):
        path = self._list_file(privacy)
        if not path.exists():
            return None
        return [ModelRecord.from_api(m) for m in json.loads(path.read_text(encoding="utf-8"))]

    # -- single records -----------------------------------------------------
    def get(self, model_id, refresh=False):
        path = self.cache_dir / "models" / f"{model_id}.json"
        if path.exists() and not refresh:
            return ModelRecord.from_api(json.loads(path.read_text(encoding="utf-8")))
        data = self.client.get(f"/models/{model_id}")
        model = data.get("model") or data
        self._write(path, model)
        return ModelRecord.from_api(model)

    def models_for_lane(self, lane, records):
        return models_for_lane(lane, records)

    # -- helpers ------------------------------------------------------------
    def _list_file(self, privacy):
        return self.cache_dir / f"list_{privacy}.json"

    @staticmethod
    def _write(path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/unit/test_catalog.py -v` Expected: 5 passed. (If the fixture list page has fewer than 2 models, re-run the recorder.)

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(core): model catalog with disk cache, pagination, lane filters and fixtures"
```

---

### Task 5: Schema parsing, request body building and validation

**Files:**
- Create: `scenario/core/schema/params.py`
- Test: `tests/unit/test_params.py`

**Interfaces:**
- Consumes: `ModelRecord.parameters`, `ModelRecord.ui_config`.
- Produces: `ParamSpec` dataclass (fields: `name, label, ptype, default, description, group, required_always, required_if_defined, allowed_values, allowed_labels, min, max, step, max_length, cost_impact, kind, is_prompt, is_array`; properties `is_file`, `is_integer`); `Schema(specs, resolution_presets, prompt_name)`; `parse_schema(record) -> Schema`; `build_body(specs, values, files, enabled=None) -> dict`; `validate(specs, body) -> list[str]`; `missing_required_files(specs, body) -> list[str]`.

- [ ] **Step 1: Write failing tests**

`tests/unit/test_params.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json

from conftest import FIXTURES
from scenario.core.api.catalog import ModelRecord
from scenario.core.schema.params import build_body, missing_required_files, parse_schema, validate


def record(name):
    return ModelRecord.from_api(json.loads((FIXTURES / "models" / f"{name}.json").read_text())["model"])


def spec_by_name(schema, name):
    return next(s for s in schema.specs if s.name == name)


def test_parse_patina_schema():
    schema = parse_schema(record("model_patina-material"))
    assert schema.prompt_name == "prompt"
    prompt = spec_by_name(schema, "prompt")
    assert prompt.required_always and prompt.is_prompt and prompt.max_length == 2048
    width = spec_by_name(schema, "width")
    assert width.ptype == "number" and width.is_integer and (width.min, width.max, width.step) == (512, 2048, 16)
    assert width.cost_impact and width.group == "Settings"
    maps = spec_by_name(schema, "maps")
    assert maps.ptype == "string_array" and maps.is_array
    assert maps.allowed_values == ("basecolor", "normal", "roughness", "metalness", "height")
    assert maps.allowed_labels["basecolor"] == "Base Color"
    upscale = spec_by_name(schema, "upscaleFactor")
    assert upscale.allowed_values == (0, 2, 4) and upscale.allowed_labels[0] == "None"
    mask = spec_by_name(schema, "mask")
    assert mask.is_file and mask.kind == "image" and not mask.is_array
    image = spec_by_name(schema, "image")
    assert image.required_if_defined == ("mask",)
    assert [p["label"] for p in schema.resolution_presets][:2] == ["1:1 (512x512)", "1:1 (1024x1024)"]


def test_parse_gemini_file_array_and_enum():
    schema = parse_schema(record("model_google-gemini-3-1-flash"))
    refs = spec_by_name(schema, "referenceImages")
    assert refs.is_file and refs.is_array and refs.kind == "image"
    res = spec_by_name(schema, "resolution")
    assert res.allowed_values == ("512", "1K", "2K", "4K") and res.default == "1K"


def test_build_body_matches_recorded_job_input():
    schema = parse_schema(record("model_patina-material"))
    job = json.loads((FIXTURES / "patina-copper-512" / "job.json").read_text())["job"]
    recorded = dict(job["metadata"]["input"])
    recorded.pop("modelId")
    recorded.pop("seed")
    values = {"prompt": "weathered copper patina with verdigris streaks", "width": 512.0, "height": 512.0,
              "maps": ["basecolor", "normal", "roughness", "metalness", "height"], "numOutputs": 1.0,
              "upscaleFactor": None, "tilingMode": "", "seed": None}
    body = build_body(schema.specs, values, files={})
    assert body == recorded


def test_build_body_files_scalar_vs_array_and_disabled_optionals():
    schema = parse_schema(record("model_google-gemini-3-1-flash"))
    body = build_body(schema.specs, {"prompt": "x", "resolution": "2K", "numOutputs": 2}, files={"referenceImages": ["asset_a", "asset_b"]},
                      enabled={"resolution": False})
    assert body["referenceImages"] == ["asset_a", "asset_b"]
    assert "resolution" not in body and body["numOutputs"] == 2
    patina = parse_schema(record("model_patina-material"))
    body = build_body(patina.specs, {"prompt": "x"}, files={"image": ["asset_1"]})
    assert body["image"] == "asset_1"


def test_validate_rules():
    schema = parse_schema(record("model_patina-material"))
    assert validate(schema.specs, {}) == ["Prompt is required"]
    errors = validate(schema.specs, {"prompt": "x" * 3000, "width": 100, "tilingMode": "diagonal", "mask": "asset_m"})
    assert "Prompt is longer than 2048 characters" in errors
    assert "Width must be between 512 and 2048" in errors
    assert "Tiling Mode must be one of both, horizontal, vertical" in errors
    assert "Image is required when Mask is set" in errors
    assert validate(schema.specs, {"prompt": "ok"}) == []


def test_missing_required_files():
    schema = parse_schema(record("model_patina"))
    assert missing_required_files(schema.specs, {}) == ["image"]
    assert missing_required_files(schema.specs, {"image": "asset_x"}) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/unit/test_params.py -v` Expected: import failure.

- [ ] **Step 3: Implement**

`scenario/core/schema/params.py`:
```python
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

    def by_name(self, name):
        return next((s for s in self.specs if s.name == name), None)


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
    return Schema(specs=specs, resolution_presets=presets, prompt_name=prompt_name)


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
        # numeric enum stored as string in the UI
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


def validate(specs, body):
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
    return errors


def missing_required_files(specs, body):
    return [s.name for s in specs if s.is_file and s.required_always and body.get(s.name) in (None, "", [])]


def _fmt(value):
    if value is None:
        return "?"
    return str(int(value)) if float(value).is_integer() else str(value)
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/unit/test_params.py -v` Expected: 6 passed. If `test_build_body_matches_recorded_job_input` fails on `numOutputs` type (recorded `1` vs `1.0`), confirm `is_integer` sees `step: 1` on the fixture and fix the coercion, not the test.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(core): schema parsing, body building and validation"
```

---

### Task 6: Generate, jobs, assets and uploads endpoints

**Files:**
- Create: `scenario/core/api/generate.py`, `scenario/core/api/jobs.py`, `scenario/core/api/assets.py`
- Test: `tests/unit/test_endpoints.py`

**Interfaces:**
- Produces: `generate.submit(client, model_id, body) -> dict job`; `generate.estimate(client, model_id, body) -> Estimate(cu_cost, discount, details)`; `jobs.get_job(client, job_id) -> dict`; `jobs.list_jobs(client, page_size=50, token=None) -> (list, next_token)`; `jobs.is_terminal(status)`, `jobs.is_success(status)`, `jobs.asset_ids(job)`, `jobs.upload_entity_id(job)`; `assets.get_asset(client, asset_id) -> dict`; `assets.download_file(url, dest, transport=None, timeout=300) -> pathlib.Path`; `assets.upload_image_base64(client, path, name=None) -> str`; `assets.upload_multipart(client, path, kind, content_type=None, transport=None, sleep=time.sleep) -> str`; `assets.upload_file(client, path, kind=None, transport=None) -> str`; `assets.kind_for_path(path) -> str`; `assets.mime_for_path(path) -> str`.

- [ ] **Step 1: Write failing tests**

`tests/unit/test_endpoints.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import base64
import json

from conftest import FIXTURES
from fakes import FakeTransport
from scenario.core.api import assets, generate, jobs
from scenario.core.api.client import ScenarioClient


def client(t):
    return ScenarioClient("k", "s", transport=t, sleep=lambda s: None)


def test_submit_and_estimate():
    job = json.loads((FIXTURES / "patina-copper-512" / "job.json").read_text())
    dry = json.loads((FIXTURES / "patina-copper-512" / "dryrun_response.json").read_text())
    t = FakeTransport().queue(200, job).queue(269, dry)
    c = client(t)
    submitted = generate.submit(c, "model_patina-material", {"prompt": "x"})
    assert submitted["jobId"] == "job_KWxxsnSdVXDFZRMsoCvLTmKY"
    assert t.calls[0]["url"].endswith("/generate/custom/model_patina-material")
    est = generate.estimate(c, "model_patina-material", {"prompt": "x"})
    assert est.cu_cost == 7.25 and est.details["quality-gate"] == 1.25
    assert t.calls[1]["url"].endswith("/generate/custom/model_patina-material?dryRun=true")
    assert "dryRun" not in t.last_json()


def test_job_helpers():
    job = json.loads((FIXTURES / "patina-copper-512" / "job.json").read_text())["job"]
    assert jobs.is_terminal("success") and jobs.is_terminal("failure") and jobs.is_terminal("canceled")
    assert not jobs.is_terminal("in-progress") and not jobs.is_terminal("queued")
    assert jobs.is_success("success") and not jobs.is_success("failure")
    assert len(jobs.asset_ids(job)) == 6
    assert jobs.upload_entity_id({"metadata": {"output": {"entityId": "asset_x"}}}) == "asset_x"
    assert jobs.upload_entity_id(job) is None


def test_get_and_list_jobs():
    t = FakeTransport().queue(200, {"job": {"jobId": "job_1", "status": "queued"}}).queue(200, {"jobs": [{"jobId": "job_2"}], "nextPaginationToken": "tok"})
    c = client(t)
    assert jobs.get_job(c, "job_1")["status"] == "queued"
    rows, token = jobs.list_jobs(c, page_size=20)
    assert rows[0]["jobId"] == "job_2" and token == "tok"
    assert "pageSize=20" in t.calls[1]["url"]


def test_get_asset_and_download(tmp_path):
    asset = json.loads((FIXTURES / "patina-copper-512" / "manifest.json").read_text())["assets"][0]
    t = FakeTransport().queue(200, {"asset": {"id": asset["assetId"], "url": "https://cdn.example/a.png", "mimeType": "image/png", "metadata": {"type": asset["type"]}}})
    c = client(t)
    rec = assets.get_asset(c, asset["assetId"])
    assert rec["mimeType"] == "image/png"
    dl = FakeTransport().queue(200, b"\x89PNG fake")
    dest = assets.download_file("https://cdn.example/a.png", tmp_path / "sub" / "a.png", transport=dl)
    assert dest.read_bytes() == b"\x89PNG fake"
    assert dl.calls[0]["headers"] == {} or "Authorization" not in dl.calls[0]["headers"]


def test_upload_image_base64(tmp_path):
    png = FIXTURES / "patina-copper-512" / "metallic.png"
    t = FakeTransport().queue(200, {"asset": {"id": "asset_new", "status": "imported"}})
    asset_id = assets.upload_image_base64(client(t), png, name="metallic.png")
    assert asset_id == "asset_new"
    body = t.last_json()
    assert body["name"] == "metallic.png"
    prefix = "data:image/png;base64,"
    assert body["image"].startswith(prefix)
    assert base64.b64decode(body["image"][len(prefix):]) == png.read_bytes()


def test_upload_multipart_flow(tmp_path):
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"0" * 1000)
    t = FakeTransport()
    t.queue(200, {"upload": {"id": "upl_1", "jobId": "job_u", "parts": [{"number": 1, "url": "https://s3.example/part1"}]}})
    t.queue(200, b"")  # PUT part
    t.queue(200, {"upload": {"id": "upl_1", "status": "validating"}})
    t.queue(200, {"job": {"jobId": "job_u", "status": "in-progress", "metadata": {"output": {}}}})
    t.queue(200, {"job": {"jobId": "job_u", "status": "success", "metadata": {"output": {"entityId": "asset_vid"}}}})
    asset_id = assets.upload_multipart(client(t), src, kind="video", transport=t, sleep=lambda s: None)
    assert asset_id == "asset_vid"
    create = t.calls[0]
    assert create["url"].endswith("/uploads")
    assert json.loads(create["body"]) == {"fileName": "clip.mp4", "fileSize": 1000, "contentType": "video/mp4", "kind": "video", "parts": 1}
    put = t.calls[1]
    assert put["method"] == "PUT" and put["url"] == "https://s3.example/part1" and put["body"] == b"0" * 1000
    assert "Authorization" not in put["headers"] and put["headers"]["Content-Type"] == "video/mp4"
    assert t.calls[2]["url"].endswith("/uploads/upl_1/action") and json.loads(t.calls[2]["body"]) == {"action": "complete"}
    assert t.calls[3]["url"].endswith("/jobs/job_u")


def test_kind_and_mime_for_path():
    assert assets.kind_for_path("a.PNG") == "image" and assets.mime_for_path("a.PNG") == "image/png"
    assert assets.kind_for_path("b.mp4") == "video" and assets.kind_for_path("c.glb") == "3d"
    assert assets.kind_for_path("d.wav") == "audio" and assets.mime_for_path("e.glb") == "model/gltf-binary"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/unit/test_endpoints.py -v` Expected: import failure.

- [ ] **Step 3: Implement**

`scenario/core/api/generate.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generation submit and dry-run cost estimate."""
from dataclasses import dataclass, field


@dataclass
class Estimate:
    cu_cost: float
    discount: float = 0.0
    details: dict = field(default_factory=dict)


def submit(client, model_id, body):
    data = client.post(f"/generate/custom/{model_id}", json_body=body)
    job = data.get("job") or {}
    if not job.get("jobId") and job.get("id"):
        job["jobId"] = job["id"]
    return job


def estimate(client, model_id, body):
    # dryRun MUST be a query parameter; in the body it is ignored and runs a paid job.
    data = client.post(f"/generate/custom/{model_id}", query={"dryRun": "true"}, json_body=body)
    return Estimate(
        cu_cost=float(data.get("creativeUnitsCost") or 0.0),
        discount=float(data.get("creativeUnitsDiscount") or 0.0),
        details=dict(data.get("costDetails") or {}),
    )
```

`scenario/core/api/jobs.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Job polling helpers."""

SUCCESS = {"success", "succeeded", "completed"}
FAILED = {"failure", "failed", "canceled", "cancelled", "error"}


def is_success(status):
    return (status or "").lower() in SUCCESS


def is_terminal(status):
    s = (status or "").lower()
    return s in SUCCESS or s in FAILED


def get_job(client, job_id):
    data = client.get(f"/jobs/{job_id}")
    return data.get("job") or data


def list_jobs(client, page_size=50, token=None, status=None):
    query = {"pageSize": page_size}
    if token:
        query["paginationToken"] = token
    if status:
        query["status"] = status
    data = client.get("/jobs", query=query)
    return list(data.get("jobs") or []), data.get("nextPaginationToken")


def asset_ids(job):
    return list(((job or {}).get("metadata") or {}).get("assetIds") or [])


def upload_entity_id(job):
    output = ((job or {}).get("metadata") or {}).get("output") or {}
    return output.get("entityId")


def progress(job):
    try:
        return float((job or {}).get("progress") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def cu_cost(job):
    billing = (job or {}).get("billing") or {}
    try:
        return float(billing.get("cuCost")) if billing.get("cuCost") is not None else None
    except (TypeError, ValueError):
        return None


def error_text(job):
    for key in ("error", "errorMessage", "failureReason", "reason"):
        value = (job or {}).get(key)
        if value:
            return str(value)
    return None
```

`scenario/core/api/assets.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Assets: read, download, upload (base64 or multipart)."""
import base64
import math
import pathlib
import time

from . import jobs
from .errors import ScenarioError
from .transport import UrllibTransport

BASE64_LIMIT = 3_500_000  # bytes, under the documented 4 MB cap for POST /assets
PART_SIZE = 32 * 1024 * 1024

_EXT_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
    ".avif": "image/avif", ".tif": "image/tiff", ".tiff": "image/tiff", ".heic": "image/heic", ".svg": "image/svg+xml",
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg", ".m4a": "audio/mp4",
    ".glb": "model/gltf-binary", ".gltf": "model/gltf+json", ".fbx": "model/x-fbx", ".obj": "model/obj",
    ".stl": "model/stl", ".ply": "model/ply", ".vox": "model/x-3d-vox",
}


def mime_for_path(path):
    return _EXT_MIME.get(pathlib.Path(str(path)).suffix.lower(), "application/octet-stream")


def kind_for_path(path):
    mime = mime_for_path(path)
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    return "3d"


def get_asset(client, asset_id):
    data = client.get(f"/assets/{asset_id}")
    return data.get("asset") or data


def asset_type(asset):
    return ((asset or {}).get("metadata") or {}).get("type") or ""


def download_file(url, dest, transport=None, timeout=300):
    """Download a signed CDN URL to `dest` (atomic rename). Never alters the query string."""
    transport = transport or UrllibTransport(timeout=timeout)
    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    status, _headers, raw = transport.request("GET", url, {}, None, timeout)
    if status >= 400:
        raise ScenarioError(status, f"download failed for {url[:80]}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(raw)
    tmp.replace(dest)
    return dest


def upload_image_base64(client, path, name=None):
    path = pathlib.Path(path)
    mime = mime_for_path(path)
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    data = client.post("/assets", json_body={"image": f"data:{mime};base64,{encoded}", "name": name or path.name})
    asset = data.get("asset") or data
    return asset["id"]


def upload_multipart(client, path, kind, content_type=None, transport=None, sleep=time.sleep, poll_interval=1.5, max_polls=120):
    path = pathlib.Path(path)
    transport = transport or client.transport
    content_type = content_type or mime_for_path(path)
    size = path.stat().st_size
    parts = max(1, math.ceil(size / PART_SIZE))
    created = client.post("/uploads", json_body={"fileName": path.name, "fileSize": size, "contentType": content_type, "kind": kind, "parts": parts})
    upload = created.get("upload") or created
    upload_id, job_id = upload["id"], upload.get("jobId")
    with path.open("rb") as handle:
        for part in sorted(upload.get("parts") or [], key=lambda p: p.get("number", 0)):
            chunk = handle.read(PART_SIZE)
            status, _h, raw = transport.request("PUT", part["url"], {"Content-Type": content_type}, chunk, 600)
            if status >= 400:
                raise ScenarioError(status, f"part {part.get('number')} upload failed: {raw[:200]!r}")
    client.post(f"/uploads/{upload_id}/action", json_body={"action": "complete"})
    for _ in range(max_polls):
        job = jobs.get_job(client, job_id)
        entity = jobs.upload_entity_id(job)
        if entity:
            return entity
        if jobs.is_terminal(job.get("status")) and not jobs.is_success(job.get("status")):
            raise ScenarioError(0, f"upload job {job_id} {job.get('status')}")
        sleep(poll_interval)
    raise ScenarioError(0, f"upload {upload_id} did not import in time")


def upload_file(client, path, kind=None, transport=None):
    path = pathlib.Path(path)
    kind = kind or kind_for_path(path)
    if kind == "image" and path.stat().st_size <= BASE64_LIMIT:
        return upload_image_base64(client, path)
    return upload_multipart(client, path, kind, transport=transport)
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/unit/test_endpoints.py -v` Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(core): generate, jobs, assets and upload endpoints"
```

---

### Task 7: Job records, registry and the threaded job manager

**Files:**
- Create: `scenario/core/jobs/records.py`, `scenario/core/jobs/manager.py`
- Test: `tests/unit/test_manager.py`

**Interfaces:**
- Consumes: Tasks 2 to 6.
- Produces: `JobRecord` (fields `local_id, lane, kind, model_id, body, job_id, status, progress, cu_cost, asset_ids, asset_types, files, error, created_at, updated_at, meta`; `to_dict/from_dict`; property `is_terminal`); `JobRegistry(path)` with `load()`, `save()`, `add(rec)`, `active() -> list`, `recent(limit=50) -> list`, `by_local_id(local_id)`, thread-safe; `EstimateResult(key, cu_cost, error)`; `JobManager(client_factory, registry, paths, poll_interval=2.5, sleep=time.sleep, downloader=download_file, uploader=upload_file)` with `submit(lane, kind, model_id, body, files=None, array_params=(), meta=None) -> JobRecord`, `estimate(key, model_id, body)`, `fetch_catalog(catalog, privacy="public", model_ids=())`, `drain() -> list[tuple]`, `resume()`, `has_active() -> bool`, `join(timeout=None)`. Event tuples: `("job", rec)`, `("job_done", rec)`, `("job_failed", rec)`, `("estimate", EstimateResult)`, `("catalog", {"privacy": str, "records": list, "detailed": list})`, `("error", str)`.

- [ ] **Step 1: Write failing tests**

`tests/unit/test_manager.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json

from conftest import FIXTURES
from fakes import FakeTransport
from scenario.core import config
from scenario.core.api.client import ScenarioClient
from scenario.core.jobs.manager import JobManager
from scenario.core.jobs.records import JobRecord, JobRegistry


def paths(tmp_path):
    return config.Paths(state_dir=tmp_path / "state", cache_dir=tmp_path / "cache", output_dir=tmp_path / "out")


def make_manager(tmp_path, transport, downloader=None, uploader=None):
    client = ScenarioClient("k", "s", transport=transport, sleep=lambda s: None)
    registry = JobRegistry(paths(tmp_path).registry_file)
    return JobManager(lambda: client, registry, paths(tmp_path), sleep=lambda s: None,
                      downloader=downloader or (lambda url, dest, **kw: dest.write_bytes(b"data") or dest),
                      uploader=uploader)


def events_of(kind, events):
    return [payload for name, payload in events if name == kind]


def test_record_roundtrip():
    rec = JobRecord.new(lane="image", kind="image", model_id="model_x", body={"prompt": "p"})
    rec.job_id = "job_1"
    again = JobRecord.from_dict(json.loads(json.dumps(rec.to_dict())))
    assert again.local_id == rec.local_id and again.job_id == "job_1" and again.status == "submitting"
    assert not again.is_terminal


def test_submit_runs_to_completion_and_downloads(tmp_path):
    job = json.loads((FIXTURES / "patina-copper-512" / "job.json").read_text())
    manifest = json.loads((FIXTURES / "patina-copper-512" / "manifest.json").read_text())
    running = {"job": dict(job["job"], status="in-progress", progress=0.4)}
    t = FakeTransport().queue(200, job).queue(200, running).queue(200, job)
    for asset in manifest["assets"]:
        t.queue(200, {"asset": {"id": asset["assetId"], "url": f"https://cdn/{asset['assetId']}", "mimeType": "image/png", "metadata": {"type": asset["type"]}}})
    manager = make_manager(tmp_path, t)
    rec = manager.submit("material", "material", "model_patina-material", {"prompt": "copper"})
    assert rec.status == "submitting"
    manager.join(timeout=5)
    events = manager.drain()
    kinds = [name for name, _ in events]
    assert kinds[0] == "job" and kinds[-1] == "job_done"
    done = events_of("job_done", events)[0]
    assert done.job_id == "job_KWxxsnSdVXDFZRMsoCvLTmKY" and done.status == "success" and done.cu_cost == 6.0
    assert len(done.files) == 6 and all((tmp_path / "out" / "materials") in p.parents for p in map(lambda s: __import__("pathlib").Path(s), done.files))
    assert done.asset_types[manifest["assets"][0]["assetId"]] == manifest["assets"][0]["type"]
    reloaded = JobRegistry(paths(tmp_path).registry_file)
    reloaded.load()
    assert reloaded.by_local_id(rec.local_id).status == "success"
    assert not manager.has_active()


def test_submit_uploads_files_first(tmp_path):
    t = FakeTransport().queue(200, {"job": {"jobId": "job_2", "status": "queued"}}).queue(200, {"job": {"jobId": "job_2", "status": "failure", "error": "nsfw"}})
    uploads = []

    def uploader(client, path, kind=None, transport=None):
        uploads.append(str(path))
        return f"asset_{len(uploads)}"

    manager = make_manager(tmp_path, t, uploader=uploader)
    manager.submit("image", "image", "model_g", {"prompt": "p"}, files={"referenceImages": ["/tmp/a.png", "/tmp/b.png"], "image": ["/tmp/c.png"]}, array_params={"referenceImages"})
    manager.join(timeout=5)
    body = json.loads(t.calls[0]["body"])
    assert body["referenceImages"] == ["asset_1", "asset_2"] and body["image"] == "asset_3"
    events = manager.drain()
    failed = events_of("job_failed", events)[0]
    assert failed.status == "failure" and failed.error == "nsfw"


def test_estimate_event_and_error(tmp_path):
    t = FakeTransport().queue(269, {"creativeUnitsCost": 13.25}).queue(400, {"reason": "Input prompt is required"})
    manager = make_manager(tmp_path, t)
    manager.estimate("image:model_g:1", "model_g", {"prompt": "p"})
    manager.estimate("image:model_g:2", "model_g", {})
    manager.join(timeout=5)
    results = events_of("estimate", manager.drain())
    by_key = {r.key: r for r in results}
    assert by_key["image:model_g:1"].cu_cost == 13.25 and by_key["image:model_g:1"].error is None
    assert by_key["image:model_g:2"].cu_cost is None and "prompt" in by_key["image:model_g:2"].error


def test_resume_polls_unfinished_jobs(tmp_path):
    registry = JobRegistry(paths(tmp_path).registry_file)
    rec = JobRecord.new(lane="image", kind="image", model_id="model_g", body={})
    rec.job_id, rec.status = "job_9", "in-progress"
    registry.add(rec)
    registry.save()
    t = FakeTransport().queue(200, {"job": {"jobId": "job_9", "status": "canceled"}})
    manager = make_manager(tmp_path, t)
    manager.registry.load()
    manager.resume()
    manager.join(timeout=5)
    assert events_of("job_failed", manager.drain())[0].status == "canceled"
    assert t.calls[0]["url"].endswith("/jobs/job_9")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/unit/test_manager.py -v` Expected: import failure.

- [ ] **Step 3: Implement records and manager**

`scenario/core/jobs/records.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Job records and the persisted registry (survives Blender restarts)."""
import json
import pathlib
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field

from ..api import jobs as jobs_api


@dataclass
class JobRecord:
    local_id: str
    lane: str
    kind: str
    model_id: str
    body: dict
    job_id: str = None
    status: str = "submitting"
    progress: float = 0.0
    cu_cost: float = None
    asset_ids: list = field(default_factory=list)
    asset_types: dict = field(default_factory=dict)
    files: list = field(default_factory=list)
    error: str = None
    created_at: float = 0.0
    updated_at: float = 0.0
    meta: dict = field(default_factory=dict)

    @classmethod
    def new(cls, lane, kind, model_id, body, meta=None, now=None):
        now = now if now is not None else time.time()
        return cls(local_id=uuid.uuid4().hex, lane=lane, kind=kind, model_id=model_id, body=dict(body), created_at=now, updated_at=now, meta=dict(meta or {}))

    @property
    def is_terminal(self):
        return self.status in ("failed",) or jobs_api.is_terminal(self.status)

    @property
    def is_success(self):
        return jobs_api.is_success(self.status)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)


class JobRegistry:
    def __init__(self, path):
        self.path = pathlib.Path(path)
        self._records = {}
        self._lock = threading.RLock()

    def load(self):
        with self._lock:
            self._records = {}
            if self.path.exists():
                try:
                    for item in json.loads(self.path.read_text(encoding="utf-8")):
                        rec = JobRecord.from_dict(item)
                        self._records[rec.local_id] = rec
                except (ValueError, TypeError, KeyError):
                    self._records = {}
        return self

    def save(self):
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = [r.to_dict() for r in sorted(self._records.values(), key=lambda r: r.created_at)]
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            tmp.replace(self.path)

    def add(self, rec):
        with self._lock:
            self._records[rec.local_id] = rec
        return rec

    def by_local_id(self, local_id):
        with self._lock:
            return self._records.get(local_id)

    def active(self):
        with self._lock:
            return [r for r in self._records.values() if not r.is_terminal]

    def recent(self, limit=50):
        with self._lock:
            return sorted(self._records.values(), key=lambda r: r.created_at, reverse=True)[:limit]

    def all(self):
        with self._lock:
            return list(self._records.values())
```

`scenario/core/jobs/manager.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Threaded job manager. Workers never touch bpy; results flow through a queue
that the Blender pump drains on the main thread."""
import datetime as dt
import logging
import queue
import threading
import time
from dataclasses import dataclass

from .. import config
from ..api import assets as assets_api
from ..api import generate as generate_api
from ..api import jobs as jobs_api
from ..api.errors import ScenarioError
from .records import JobRecord

log = logging.getLogger("scenario.jobs")


@dataclass
class EstimateResult:
    key: str
    cu_cost: float = None
    error: str = None


class JobManager:
    def __init__(self, client_factory, registry, paths, *, poll_interval=2.5, sleep=time.sleep,
                 downloader=assets_api.download_file, uploader=None):
        self.client_factory = client_factory
        self.registry = registry
        self.paths = paths
        self.poll_interval = poll_interval
        self.sleep = sleep
        self.downloader = downloader
        self.uploader = uploader or assets_api.upload_file
        self.events = queue.Queue()
        self._threads = []
        self._stop = threading.Event()

    # -- public API (main thread) -----------------------------------------
    def submit(self, lane, kind, model_id, body, files=None, array_params=(), meta=None):
        rec = JobRecord.new(lane=lane, kind=kind, model_id=model_id, body=body, meta=meta)
        self.registry.add(rec)
        self.registry.save()
        self._spawn(self._run_job, rec, dict(files or {}), set(array_params))
        return rec

    def estimate(self, key, model_id, body):
        self._spawn(self._run_estimate, key, model_id, dict(body))

    def fetch_catalog(self, catalog, privacy="public", model_ids=()):
        self._spawn(self._run_catalog, catalog, privacy, tuple(model_ids))

    def resume(self):
        for rec in self.registry.active():
            if rec.job_id:
                self._spawn(self._poll_job, rec)
            else:
                rec.status, rec.error = "failed", "Blender closed before the job was submitted"
                self.registry.save()

    def drain(self):
        out = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                return out

    def has_active(self):
        return any(t.is_alive() for t in self._threads)

    def join(self, timeout=None):
        deadline = None if timeout is None else time.time() + timeout
        for t in list(self._threads):
            remaining = None if deadline is None else max(0.0, deadline - time.time())
            t.join(remaining)
        self._threads = [t for t in self._threads if t.is_alive()]

    def shutdown(self):
        self._stop.set()

    # -- workers ------------------------------------------------------------
    def _spawn(self, target, *args):
        thread = threading.Thread(target=self._guard, args=(target,) + args, daemon=True, name=f"scenario-{target.__name__}")
        self._threads.append(thread)
        thread.start()
        return thread

    def _guard(self, target, *args):
        try:
            target(*args)
        except Exception as err:  # never let a worker die silently
            log.exception("worker %s failed", target.__name__)
            self.events.put(("error", str(err)))

    def _run_job(self, rec, files, array_params):
        client = self.client_factory()
        try:
            for param_name, paths in files.items():
                ids = [self.uploader(client, p) for p in paths]
                if not ids:
                    continue
                rec.body[param_name] = ids if param_name in array_params else ids[0]
            job = generate_api.submit(client, rec.model_id, rec.body)
        except ScenarioError as err:
            self._fail(rec, str(err))
            return
        rec.job_id = job.get("jobId")
        self._update_from_job(rec, job)
        self.events.put(("job", rec))
        self._poll_job(rec)

    def _poll_job(self, rec):
        client = self.client_factory()
        while not self._stop.is_set():
            self.sleep(self.poll_interval)
            try:
                job = jobs_api.get_job(client, rec.job_id)
            except ScenarioError as err:
                if err.status in (401, 403, 404):
                    self._fail(rec, str(err))
                    return
                self.events.put(("error", f"poll {rec.job_id}: {err}"))
                continue
            self._update_from_job(rec, job)
            if not rec.is_terminal:
                self.events.put(("job", rec))
                continue
            if rec.is_success:
                try:
                    self._download_results(client, rec)
                except ScenarioError as err:
                    self._fail(rec, f"download: {err}")
                    return
                self.registry.save()
                self.events.put(("job_done", rec))
            else:
                self._fail(rec, jobs_api.error_text(job) or rec.status)
            return

    def _download_results(self, client, rec):
        out_dir = self.paths.output_for(rec.kind)
        now = dt.datetime.now()
        for index, asset_id in enumerate(rec.asset_ids):
            asset = assets_api.get_asset(client, asset_id)
            rec.asset_types[asset_id] = assets_api.asset_type(asset)
            ext = config.ext_for_mime(asset.get("mimeType"))
            dest = out_dir / config.output_filename(rec.kind, rec.model_id, rec.job_id, index, ext, when=now)
            url = asset.get("url")
            if not url:
                raise ScenarioError(0, f"asset {asset_id} has no url")
            self.downloader(url, dest)
            rec.files.append(str(dest))

    def _update_from_job(self, rec, job):
        rec.status = (job.get("status") or rec.status).lower()
        rec.progress = jobs_api.progress(job)
        cost = jobs_api.cu_cost(job)
        if cost is not None:
            rec.cu_cost = cost
        ids = jobs_api.asset_ids(job)
        if ids:
            rec.asset_ids = ids
        rec.updated_at = time.time()
        self.registry.save()

    def _fail(self, rec, message):
        if not rec.is_terminal or rec.status == "submitting":
            rec.status = "failed"
        rec.error = message
        rec.updated_at = time.time()
        self.registry.save()
        self.events.put(("job_failed", rec))

    def _run_estimate(self, key, model_id, body):
        client = self.client_factory()
        try:
            est = generate_api.estimate(client, model_id, body)
            self.events.put(("estimate", EstimateResult(key=key, cu_cost=est.cu_cost)))
        except ScenarioError as err:
            self.events.put(("estimate", EstimateResult(key=key, error=err.reason)))

    def _run_catalog(self, catalog, privacy, model_ids):
        records = catalog.fetch_list(privacy=privacy)
        detailed = []
        for model_id in model_ids:
            try:
                detailed.append(catalog.get(model_id))
            except ScenarioError as err:
                log.warning("model %s: %s", model_id, err)
        self.events.put(("catalog", {"privacy": privacy, "records": records, "detailed": detailed}))
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/unit/test_manager.py -v` Expected: 5 passed. Then `python3 -m pytest` Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(core): job records, persisted registry and threaded job manager"
```

---

### Task 8: Preferences, runtime singletons, registry and the headless test harness

**Files:**
- Create: `scenario/prefs.py`, `scenario/blender/runtime.py`
- Modify: `scenario/blender/registry.py`
- Create: `tests/blender/run_all.py`, `tests/blender/helpers.py`, `tests/blender/test_register.py`

**Interfaces:**
- Produces: `ScenarioPreferences` (props `api_key`, `api_secret`, `output_dir`, `composer_enabled`, `mcp_port`, `mcp_allow_python`, `log_level`); `prefs.get_prefs(context=None)`; `runtime.state` (`RuntimeState` with `manager`, `catalog`, `records`, `lane_models`, `account_label`, `last_message`, `enum_cache`, `previews`); `runtime.paths()`, `runtime.credentials()`, `runtime.make_client()`, `runtime.ensure_manager()`, `runtime.ensure_catalog()`, `runtime.online()`, `runtime.enum_items(key)`, `runtime.set_enum_items(key, items)`, `runtime.set_message(text)`; `registry.register()/unregister()` registering classes from `prefs`, then (later tasks) `props`, `operators`, `panels`, and starting/stopping the pump.

- [ ] **Step 1: Write the headless harness and a failing test**

`tests/blender/helpers.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Helpers for tests that run inside `blender --background`."""
import importlib
import pathlib

import bpy

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"


def addon_name():
    for name in bpy.context.preferences.addons.keys():
        if name == "scenario" or name.endswith(".scenario"):
            return name
    raise RuntimeError("scenario extension is not enabled: run ./tools/install_dev.sh first")


def addon():
    return importlib.import_module(addon_name())


def submodule(path):
    return importlib.import_module(f"{addon_name()}.{path}")


def reset_scene():
    bpy.ops.wm.read_homefile(use_empty=True)
```

`tests/blender/run_all.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Discover and run tests/blender/test_*.py inside Blender. Exit code 1 on failure."""
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

suite = unittest.TestLoader().discover(str(HERE), pattern="test_*.py")
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful():
    sys.exit(1)
```

`tests/blender/test_register.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

import bpy

from helpers import addon, addon_name, submodule


class RegisterTests(unittest.TestCase):
    def test_extension_enabled_and_prefs_have_defaults(self):
        mod = addon()
        self.assertEqual(mod.__version__, "0.1.0")
        prefs = bpy.context.preferences.addons[addon_name()].preferences
        self.assertEqual(prefs.output_dir, "~/Downloads/Scenario")
        self.assertEqual(prefs.mcp_port, 9876)
        self.assertTrue(prefs.composer_enabled)

    def test_runtime_paths_live_outside_the_extension_dir(self):
        runtime = submodule("blender.runtime")
        paths = runtime.paths()
        self.assertTrue(str(paths.state_dir).endswith("state"))
        self.assertNotIn("extensions/user_default/scenario", str(paths.state_dir).replace("\\", "/") + "/")
        self.assertTrue(paths.state_dir.exists())

    def test_credentials_resolve_from_prefs(self):
        runtime = submodule("blender.runtime")
        prefs = bpy.context.preferences.addons[addon_name()].preferences
        prefs.api_key, prefs.api_secret = "k", "s"
        try:
            self.assertTrue(runtime.credentials().valid)
        finally:
            prefs.api_key, prefs.api_secret = "", ""
```

- [ ] **Step 2: Run to see it fail**

Run: `make test-blender` Expected: fails (extension not enabled or `prefs` module missing).

- [ ] **Step 3: Implement preferences, runtime and registry**

`scenario/prefs.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Add-on preferences: credentials, output folder, composer, MCP."""
import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty

PORTAL_KEYS_URL = "https://app.scenario.com/team"


class ScenarioPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    api_key: StringProperty(name="API Key", subtype='PASSWORD', description="Scenario API key (Project or Team scoped). Created in the Scenario portal")
    api_secret: StringProperty(name="API Secret", subtype='PASSWORD', description="Shown once when the key is created")
    output_dir: StringProperty(name="Output Folder", subtype='DIR_PATH', default="~/Downloads/Scenario", description="Generated files are saved here, one subfolder per kind")
    composer_enabled: BoolProperty(name="Floating composer in the viewport", default=True)
    mcp_port: IntProperty(name="MCP Port", default=9876, min=1024, max=65535)
    mcp_allow_python: BoolProperty(name="Allow connected agents to run Python", default=True, description="Agents connected through the local MCP server may execute bpy code in this Blender")
    log_level: EnumProperty(name="Log Level", items=[('INFO', "Info", ""), ('DEBUG', "Debug", "")], default='INFO')

    def draw(self, context):
        from .blender import runtime

        layout = self.layout
        box = layout.box()
        box.label(text="Account", icon='USER')
        box.prop(self, "api_key")
        box.prop(self, "api_secret")
        row = box.row(align=True)
        row.operator("wm.url_open", text="Create a key in the portal", icon='URL').url = PORTAL_KEYS_URL
        row.operator("scenario.test_connection", text="Test connection", icon='CHECKMARK')
        if runtime.state.account_label:
            box.label(text=runtime.state.account_label, icon='INFO')
        if not runtime.online():
            box.label(text="Allow Online Access is off in Blender's System preferences", icon='ERROR')
        layout.prop(self, "output_dir")
        layout.prop(self, "composer_enabled")
        box = layout.box()
        box.label(text="MCP server (agents)", icon='PLUGIN')
        box.prop(self, "mcp_port")
        box.prop(self, "mcp_allow_python")
        layout.prop(self, "log_level")


def get_prefs(context=None):
    context = context or bpy.context
    entry = context.preferences.addons.get(__package__)
    return entry.preferences if entry else None


CLASSES = (ScenarioPreferences,)
```

`scenario/blender/runtime.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Process-wide singletons shared by panels, operators and the pump (main thread only)."""
import logging
import os
import pathlib

import bpy

from .. import prefs as prefs_module
from ..core import config
from ..core.api.catalog import Catalog
from ..core.api.client import ScenarioClient
from ..core.api.errors import ScenarioError
from ..core.jobs.manager import JobManager
from ..core.jobs.records import JobRegistry

log = logging.getLogger("scenario")
PACKAGE = __package__.rsplit(".", 1)[0]  # the extension package, e.g. bl_ext.user_default.scenario


class RuntimeState:
    def __init__(self):
        self.manager = None
        self.catalog = None
        self.records = {}          # model_id -> ModelRecord (detailed)
        self.lane_models = {}      # lane -> list[ModelRecord]
        self.catalog_loaded = False
        self.catalog_loading = False
        self.account_label = ""
        self.last_message = ""
        self.enum_cache = {}       # key -> list of (id, name, desc) tuples kept alive for EnumProperty
        self.previews = None       # bpy.utils.previews collection, created lazily
        self.jobs_view = []        # JobRecord list shown in the panel (active + recent)

    def reset(self):
        self.__init__()


state = RuntimeState()


def prefs():
    return prefs_module.get_prefs()


def online():
    return bool(getattr(bpy.app, "online_access", True))


def paths():
    state_dir = pathlib.Path(bpy.utils.extension_path_user(PACKAGE, path="state", create=True))
    cache_dir = pathlib.Path(bpy.utils.extension_path_user(PACKAGE, path="cache", create=True))
    p = prefs()
    raw_out = p.output_dir if p and p.output_dir else "~/Downloads/Scenario"
    output_dir = pathlib.Path(os.path.expanduser(bpy.path.abspath(raw_out)))
    return config.Paths(state_dir=state_dir, cache_dir=cache_dir, output_dir=output_dir)


def credentials():
    p = prefs()
    return config.resolve_credentials(p.api_key if p else "", p.api_secret if p else "")


def make_client():
    creds = credentials()
    if not creds.valid:
        raise ScenarioError(0, "Add your Scenario API key and secret in Preferences")
    from .. import __version__

    return ScenarioClient(creds.key, creds.secret, user_agent=f"ScenarioBlender/{__version__}")


def ensure_manager():
    if state.manager is None:
        p = paths()
        registry = JobRegistry(p.registry_file).load()
        state.manager = JobManager(make_client, registry, p)
        state.manager.resume()
    return state.manager


def ensure_catalog():
    if state.catalog is None:
        state.catalog = Catalog(make_client(), paths().cache_dir)
    return state.catalog


def enum_items(key):
    return state.enum_cache.get(key) or [("NONE", "Loading...", "Model list not loaded yet")]


def set_enum_items(key, items):
    state.enum_cache[key] = [tuple(item) for item in items] or [("NONE", "None available", "")]


def set_message(text):
    state.last_message = text
    log.info(text)


def previews():
    import bpy.utils.previews

    if state.previews is None:
        state.previews = bpy.utils.previews.new()
    return state.previews


def shutdown():
    if state.manager:
        state.manager.shutdown()
    if state.previews is not None:
        import bpy.utils.previews

        bpy.utils.previews.remove(state.previews)
    state.reset()
```

`scenario/blender/registry.py` (replace the placeholder):
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Registers every Blender class of the extension in dependency order."""
import logging

import bpy

from .. import prefs

log = logging.getLogger("scenario")

_MODULES = []  # extended by later tasks: props, operators, panels


def _modules():
    from . import props, operators, panels  # noqa: F401  (added in Tasks 9 and 10)

    return [props, operators, panels]


def register():
    logging.basicConfig(level=logging.INFO)
    for cls in prefs.CLASSES:
        bpy.utils.register_class(cls)
    try:
        modules = _modules()
    except ImportError:
        modules = []
    for module in modules:
        module.register()
    from . import pump

    pump.start()
    log.info("Scenario for Blender registered")


def unregister():
    from . import pump, runtime

    pump.stop()
    try:
        modules = _modules()
    except ImportError:
        modules = []
    for module in reversed(modules):
        module.unregister()
    for cls in reversed(prefs.CLASSES):
        bpy.utils.unregister_class(cls)
    runtime.shutdown()
    log.info("Scenario for Blender unregistered")
```

Create a minimal `scenario/blender/pump.py` now so registration works (Task 10 fills it in):
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Main-thread pump: drains the job manager's event queue from a bpy.app.timers callback."""
import bpy


def start():
    return None


def stop():
    return None
```

- [ ] **Step 4: Build, install and run the headless tests**

Run: `./tools/install_dev.sh && make test-blender` Expected: `Ran 3 tests ... OK`. If `install-file` complains about `--enable`, run `$BLENDER --command extension install-file --help`, adapt the flag, and enable manually once with `$BLENDER --background --python-expr "import bpy; bpy.ops.preferences.addon_enable(module='bl_ext.user_default.scenario'); bpy.ops.wm.save_userpref()"`.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(blender): preferences, runtime singletons, registry and headless test harness"
```

---

### Task 9: Scene property groups and the schema-driven parameter UI

**Files:**
- Create: `scenario/blender/props.py`, `scenario/blender/params_ui.py`
- Test: `tests/blender/test_params_ui.py`

**Interfaces:**
- Produces: property groups `ScenarioParamValue` (fields `name, model_id, lane, ptype, label, str_value, int_value, float_value, bool_value, enum_value, multi_value, enabled, fmin, fmax, has_range`), `ScenarioReference` (`param_name, source, filepath, asset_id, label`), `ScenarioLaneState` (`lane, model_id (dynamic enum), prompt, params, references, estimate_state, estimate_cu, estimate_dirty_at, estimate_key, last_error`), `ScenarioSceneProps` (`lane` enum; pointers `image, video, three_d, material, render`; method `lane_state(lane=None)`); `bpy.types.Scene.scenario`; `props.LANE_ITEMS`, `props.mark_estimate_dirty(lane_state)`; `params_ui.sync_params(lane_state, schema, model_id)`, `params_ui.draw_params(layout, lane_state, schema)`, `params_ui.collect_values(lane_state, schema) -> (values, enabled)`, `params_ui.collect_file_refs(lane_state, schema) -> dict[param, list[ScenarioReference]]`, `params_ui.multi_selection(item) -> list[str]`, `params_ui.set_multi_selection(item, values)`.

- [ ] **Step 1: Write the failing headless test**

`tests/blender/test_params_ui.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import unittest

import bpy

from helpers import FIXTURES, reset_scene, submodule


def patina_schema():
    catalog = submodule("core.api.catalog")
    params = submodule("core.schema.params")
    data = json.loads((FIXTURES / "models" / "model_patina-material.json").read_text())["model"]
    return params.parse_schema(catalog.ModelRecord.from_api(data))


class ParamsUiTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.params_ui = submodule("blender.params_ui")
        self.params = submodule("core.schema.params")
        self.props = submodule("blender.props")
        self.lane = bpy.context.scene.scenario.lane_state("material")

    def test_sync_creates_items_with_defaults_and_labels(self):
        schema = patina_schema()
        self.params_ui.sync_params(self.lane, schema, "model_patina-material")
        names = [item.name for item in self.lane.params]
        self.assertIn("width", names)
        self.assertNotIn("prompt", names)   # prompt is drawn separately
        self.assertNotIn("image", names)    # files are references
        width = self.lane.params["width"]
        self.assertEqual(width.int_value, 1024)
        self.assertEqual((width.fmin, width.fmax), (512.0, 2048.0))
        maps = self.lane.params["maps"]
        self.assertEqual(self.params_ui.multi_selection(maps), ["basecolor", "normal", "roughness", "metalness", "height"])
        tiling = self.lane.params["tilingMode"]
        self.assertEqual(tiling.enum_value, "both")
        upscale = self.lane.params["upscaleFactor"]
        self.assertEqual(upscale.enum_value, "0")

    def test_collect_values_builds_the_recorded_body(self):
        schema = patina_schema()
        self.params_ui.sync_params(self.lane, schema, "model_patina-material")
        self.lane.prompt = "weathered copper patina with verdigris streaks"
        self.lane.params["width"].int_value = 512
        self.lane.params["height"].int_value = 512
        values, enabled = self.params_ui.collect_values(self.lane, schema)
        body = self.params.build_body(schema.specs, values, files={}, enabled=enabled)
        recorded = json.loads((FIXTURES / "patina-copper-512" / "job.json").read_text())["job"]["metadata"]["input"]
        recorded = {k: v for k, v in recorded.items() if k not in ("modelId", "seed")}
        for key, value in recorded.items():
            self.assertEqual(body.get(key), value, key)

    def test_disabled_optional_is_omitted_and_clamping_applies(self):
        schema = patina_schema()
        self.params_ui.sync_params(self.lane, schema, "model_patina-material")
        self.lane.params["upscaleFactor"].enabled = False
        self.lane.params["width"].int_value = 100_000
        self.assertEqual(self.lane.params["width"].int_value, 2048)
        values, enabled = self.params_ui.collect_values(self.lane, schema)
        self.assertFalse(enabled["upscaleFactor"])

    def test_sync_keeps_compatible_values_across_models_and_drops_others(self):
        schema = patina_schema()
        self.params_ui.sync_params(self.lane, schema, "model_patina-material")
        self.lane.params["width"].int_value = 768
        catalog = submodule("core.api.catalog")
        gemini = json.loads((FIXTURES / "models" / "model_google-gemini-3-1-flash.json").read_text())["model"]
        gschema = self.params.parse_schema(catalog.ModelRecord.from_api(gemini))
        self.params_ui.sync_params(self.lane, gschema, "model_google-gemini-3-1-flash")
        self.assertNotIn("width", [i.name for i in self.lane.params])
        self.assertEqual(self.lane.params["resolution"].enum_value, "1K")
        self.params_ui.sync_params(self.lane, schema, "model_patina-material")
        self.assertEqual(self.lane.params["width"].int_value, 1024)

    def test_references_group_by_param(self):
        schema = patina_schema()
        ref = self.lane.references.add()
        ref.param_name, ref.source, ref.filepath = "image", 'FILE', "/tmp/a.png"
        refs = self.params_ui.collect_file_refs(self.lane, schema)
        self.assertEqual([r.filepath for r in refs["image"]], ["/tmp/a.png"])
        self.assertEqual(refs.get("mask", []), [])
```

- [ ] **Step 2: Run to see it fail**

Run: `make test-blender` Expected: `ModuleNotFoundError` for `blender.props` / `blender.params_ui`.

- [ ] **Step 3: Implement props and params_ui**

`scenario/blender/props.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene-level property groups: one lane state per generation lane, schema-driven parameter values."""
import time

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty

from . import runtime

LANE_ITEMS = [
    ('image', "Image", "Text and reference images to images"),
    ('video', "Video", "Text, images or a Blender playblast to video"),
    ('3d', "3D", "Text or images to 3D models"),
    ('material', "Materials", "PBR materials with Patina"),
    ('render', "Render-to-real", "Viewport capture and playblast to styled stills and video"),
    ('mcp', "MCP", "Let agents build in this Blender"),
    ('history', "Generations", "Everything generated in this project"),
]
GENERATION_LANES = ("image", "video", "3d", "material", "render")
LANE_ATTR = {"image": "image", "video": "video", "3d": "three_d", "material": "material", "render": "render"}
REFERENCE_SOURCES = [
    ('FILE', "File", "An image or video file on disk"),
    ('VIEWPORT', "Viewport", "Capture the active 3D viewport at generate time"),
    ('RENDER', "Render Result", "The latest render result"),
    ('ASSET', "Scenario asset", "An asset already in your Scenario project"),
]


def mark_estimate_dirty(lane_state):
    lane_state.estimate_state = 'PENDING'
    lane_state.estimate_dirty_at = time.time()


def _param_items(self, context):
    return runtime.enum_items(("param", self.model_id, self.name))


def _on_param_update(self, context):
    if self.has_range:
        if self.float_value < self.fmin:
            self.float_value = self.fmin
        elif self.float_value > self.fmax:
            self.float_value = self.fmax
        if self.int_value < int(self.fmin):
            self.int_value = int(self.fmin)
        elif self.int_value > int(self.fmax):
            self.int_value = int(self.fmax)
    lane_state = _find_lane_state(context, self.lane)
    if lane_state is not None:
        mark_estimate_dirty(lane_state)


def _find_lane_state(context, lane):
    scene = getattr(context, "scene", None) or bpy.context.scene
    if scene is None or not lane:
        return None
    return scene.scenario.lane_state(lane)


class ScenarioParamValue(bpy.types.PropertyGroup):
    name: StringProperty()
    model_id: StringProperty()
    lane: StringProperty()
    ptype: StringProperty()
    label: StringProperty()
    str_value: StringProperty(update=_on_param_update)
    int_value: IntProperty(update=_on_param_update)
    float_value: FloatProperty(update=_on_param_update, precision=3)
    bool_value: BoolProperty(update=_on_param_update)
    enum_value: EnumProperty(items=_param_items, update=_on_param_update)
    multi_value: StringProperty(description="Comma separated selection for list parameters")
    enabled: BoolProperty(default=True, update=_on_param_update)
    fmin: FloatProperty(default=-1e9)
    fmax: FloatProperty(default=1e9)
    has_range: BoolProperty(default=False)


class ScenarioReference(bpy.types.PropertyGroup):
    param_name: StringProperty()
    source: EnumProperty(items=REFERENCE_SOURCES, default='FILE')
    filepath: StringProperty(subtype='FILE_PATH')
    asset_id: StringProperty()
    label: StringProperty()


def _model_items(self, context):
    return runtime.enum_items(("models", self.lane))


def _on_model_change(self, context):
    from . import generation

    generation.on_model_changed(context, self)


def _on_prompt_update(self, context):
    mark_estimate_dirty(self)


class ScenarioLaneState(bpy.types.PropertyGroup):
    lane: StringProperty()
    model_id: EnumProperty(name="Model", items=_model_items, update=_on_model_change)
    prompt: StringProperty(name="Prompt", description="What to generate", update=_on_prompt_update)
    params: CollectionProperty(type=ScenarioParamValue)
    references: CollectionProperty(type=ScenarioReference)
    estimate_state: EnumProperty(items=[('IDLE', "Idle", ""), ('PENDING', "Pending", ""), ('READY', "Ready", ""), ('ERROR', "Error", ""), ('UNAVAILABLE', "Unavailable", "")], default='IDLE')
    estimate_cu: FloatProperty(default=-1.0)
    estimate_dirty_at: FloatProperty(default=0.0)
    estimate_key: StringProperty()
    estimate_error: StringProperty()
    last_error: StringProperty()


class ScenarioSceneProps(bpy.types.PropertyGroup):
    lane: EnumProperty(name="Lane", items=LANE_ITEMS, default='image')
    image: PointerProperty(type=ScenarioLaneState)
    video: PointerProperty(type=ScenarioLaneState)
    three_d: PointerProperty(type=ScenarioLaneState)
    material: PointerProperty(type=ScenarioLaneState)
    render: PointerProperty(type=ScenarioLaneState)

    def lane_state(self, lane=None):
        lane = lane or self.lane
        attr = LANE_ATTR.get(lane)
        if attr is None:
            return None
        state = getattr(self, attr)
        if not state.lane:
            state.lane = lane
        return state


CLASSES = (ScenarioParamValue, ScenarioReference, ScenarioLaneState, ScenarioSceneProps)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.scenario = PointerProperty(type=ScenarioSceneProps)


def unregister():
    del bpy.types.Scene.scenario
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
```

`scenario/blender/params_ui.py`:
```python
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
    """Ensure one collection item per drawable spec; keep values whose name and type match."""
    existing = {item.name: item for item in lane_state.params}
    keep = {}
    for spec in schema.specs:
        if not _drawable(spec):
            continue
        item = existing.get(spec.name)
        compatible = item is not None and item.ptype == spec.ptype and item.model_id == model_id
        if item is None or not compatible:
            if item is not None:
                lane_state.params.remove(lane_state.params.find(spec.name))
            item = lane_state.params.add()
            item.name, item.ptype = spec.name, spec.ptype
            item.model_id, item.lane, item.label = model_id, lane_state.lane, spec.label
            _apply_default(item, spec)
        keep[spec.name] = True
        if spec.allowed_values and spec.ptype != "string_array":
            runtime.set_enum_items(("param", model_id, spec.name), [(str(v), spec.label_for(v), spec.description) for v in spec.allowed_values])
            valid = [str(v) for v in spec.allowed_values]
            if item.enum_value not in valid:
                item.enum_value = str(spec.default) if spec.default is not None and str(spec.default) in valid else valid[0]
    for index in range(len(lane_state.params) - 1, -1, -1):
        if lane_state.params[index].name not in keep:
            lane_state.params.remove(index)


def _apply_default(item, spec):
    item.has_range = spec.min is not None or spec.max is not None
    item.fmin = float(spec.min) if spec.min is not None else -1e9
    item.fmax = float(spec.max) if spec.max is not None else 1e9
    default = spec.default
    if spec.ptype == "number":
        value = default if isinstance(default, (int, float)) else (spec.min if spec.min is not None else 0)
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
```

- [ ] **Step 4: Register and run the headless tests**

Add to `scenario/blender/registry.py` `_modules()`: it already imports `props, operators, panels`; until Task 10 exists create stub modules `scenario/blender/operators.py` and `scenario/blender/panels.py` each with `def register(): pass` and `def unregister(): pass` (plus SPDX header), and a stub `scenario/blender/generation.py` with `def on_model_changed(context, lane_state): pass`. Then run `./tools/install_dev.sh && make test-blender` Expected: `Ran 8 tests ... OK`.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(blender): scene property groups and schema-driven parameter UI"
```

---

### Task 10: Pump, catalog loading, generation flow, operators, Image lane panel and image import

**Files:**
- Create: `scenario/blender/pump.py` (replace stub), `scenario/blender/handlers.py`, `scenario/blender/generation.py` (replace stub), `scenario/blender/operators.py` (replace stub), `scenario/blender/panels.py` (replace stub), `scenario/blender/apply_image.py`
- Test: `tests/blender/test_apply_image.py`, `tests/blender/test_generation.py`
- Create: `tools/gui_screenshot.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `pump.start()/stop()`, `pump.ESTIMATE_DEBOUNCE = 0.7`; `handlers.dispatch(event)`; `generation.on_model_changed(context, lane_state)`, `generation.schema_for(model_id) -> Schema | None`, `generation.request_estimate(scene, lane)`, `generation.submit_generation(context, lane) -> JobRecord`, `generation.lane_kind(lane) -> str`, `generation.request_catalog()`, `generation.set_catalog(records, detailed)`; operators `scenario.test_connection`, `scenario.refresh_catalog`, `scenario.generate`, `scenario.add_reference`, `scenario.remove_reference`, `scenario.toggle_multi`, `scenario.open_output_folder`, `scenario.show_image`, `scenario.apply_texture`, `scenario.add_plane`, `scenario.expand_prompt`; panels `SCENARIO_PT_main`, `SCENARIO_PT_jobs`, `SCENARIO_PT_results`; `apply_image.load_image(path, pack=True)`, `apply_image.show_in_image_editor(image)`, `apply_image.material_with_image(name, image)`, `apply_image.apply_as_texture(obj, image)`, `apply_image.add_as_plane(context, image)`, `apply_image.on_image_result(rec)`.

- [ ] **Step 1: Write the failing headless tests**

`tests/blender/test_apply_image.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

import bpy

from helpers import FIXTURES, reset_scene, submodule

ALBEDO = str(FIXTURES / "patina-copper-512" / "albedo.png")


class ApplyImageTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.apply_image = submodule("blender.apply_image")

    def test_load_image_packs(self):
        img = self.apply_image.load_image(ALBEDO)
        self.assertEqual(tuple(img.size), (512, 512))
        self.assertTrue(img.packed_file is not None)

    def test_apply_as_texture_links_base_color(self):
        bpy.ops.mesh.primitive_cube_add()
        cube = bpy.context.active_object
        img = self.apply_image.load_image(ALBEDO)
        mat = self.apply_image.apply_as_texture(cube, img)
        self.assertIs(cube.active_material, mat)
        tex = next(n for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE')
        bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        self.assertIs(tex.image, img)
        link = next(l for l in mat.node_tree.links if l.to_node is bsdf and l.to_socket.name == "Base Color")
        self.assertIs(link.from_node, tex)

    def test_add_as_plane_matches_aspect_and_cursor(self):
        img = self.apply_image.load_image(ALBEDO)
        bpy.context.scene.cursor.location = (1.0, 2.0, 3.0)
        plane = self.apply_image.add_as_plane(bpy.context, img)
        self.assertEqual(plane.type, 'MESH')
        self.assertAlmostEqual(plane.scale.x / plane.scale.y, 1.0, places=4)
        self.assertAlmostEqual(tuple(plane.location)[2], 3.0, places=4)
        self.assertEqual(len(plane.data.materials), 1)

    def test_on_image_result_loads_every_file(self):
        records = submodule("core.jobs.records")
        rec = records.JobRecord.new(lane="image", kind="image", model_id="model_x", body={})
        rec.files = [ALBEDO, str(FIXTURES / "patina-copper-512" / "normal.png")]
        rec.job_id = "job_t"
        names = self.apply_image.on_image_result(rec)
        self.assertEqual(len(names), 2)
        self.assertTrue(all(name in bpy.data.images for name in names))
```

`tests/blender/test_generation.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import unittest

import bpy

from helpers import FIXTURES, reset_scene, submodule


class GenerationTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.generation = submodule("blender.generation")
        self.runtime = submodule("blender.runtime")
        self.catalog = submodule("core.api.catalog")
        self.handlers = submodule("blender.handlers")
        self.runtime.state.reset()
        patina = json.loads((FIXTURES / "models" / "model_patina-material.json").read_text())["model"]
        gemini = json.loads((FIXTURES / "models" / "model_google-gemini-3-1-flash.json").read_text())["model"]
        records = [self.catalog.ModelRecord.from_api(patina), self.catalog.ModelRecord.from_api(gemini)]
        self.handlers.dispatch(("catalog", {"privacy": "public", "records": records, "detailed": records}))

    def test_catalog_event_fills_lane_enums_and_syncs_params(self):
        items = self.runtime.enum_items(("models", "image"))
        ids = [i[0] for i in items]
        self.assertEqual(ids[0], "model_google-gemini-3-1-flash")
        self.assertIn("model_patina-material", ids)
        self.assertEqual([i[0] for i in self.runtime.enum_items(("models", "material"))], ["model_patina-material"])
        lane = bpy.context.scene.scenario.lane_state("image")
        self.assertEqual(lane.model_id, "model_google-gemini-3-1-flash")
        self.assertIn("resolution", [p.name for p in lane.params])

    def test_estimate_event_updates_lane_state(self):
        lane = bpy.context.scene.scenario.lane_state("image")
        lane.estimate_key = "image:k1"
        lane.estimate_state = 'PENDING'
        est = submodule("core.jobs.manager").EstimateResult(key="image:k1", cu_cost=13.25)
        self.handlers.dispatch(("estimate", est))
        self.assertEqual(lane.estimate_state, 'READY')
        self.assertAlmostEqual(lane.estimate_cu, 13.25)
        bad = submodule("core.jobs.manager").EstimateResult(key="image:k1", error="Input prompt is required")
        self.handlers.dispatch(("estimate", bad))
        self.assertEqual(lane.estimate_state, 'ERROR')
        self.assertIn("prompt", lane.estimate_error)

    def test_build_request_from_scene_state(self):
        lane = bpy.context.scene.scenario.lane_state("image")
        lane.prompt = "a copper teapot"
        lane.params["resolution"].enum_value = "2K"
        ref = lane.references.add()
        ref.param_name, ref.source, ref.filepath = "referenceImages", 'FILE', str(FIXTURES / "patina-copper-512" / "albedo.png")
        request = self.generation.build_request(bpy.context.scene, "image")
        self.assertEqual(request.model_id, "model_google-gemini-3-1-flash")
        self.assertEqual(request.body["prompt"], "a copper teapot")
        self.assertEqual(request.body["resolution"], "2K")
        self.assertEqual(request.files["referenceImages"], [str(FIXTURES / "patina-copper-512" / "albedo.png")])
        self.assertIn("referenceImages", request.array_params)
        self.assertEqual(request.errors, [])

    def test_job_done_event_for_image_loads_images(self):
        records = submodule("core.jobs.records")
        rec = records.JobRecord.new(lane="image", kind="image", model_id="model_x", body={})
        rec.job_id, rec.status = "job_done_1", "success"
        rec.files = [str(FIXTURES / "patina-copper-512" / "albedo.png")]
        self.handlers.dispatch(("job_done", rec))
        self.assertTrue(any(img.filepath.endswith("albedo.png") for img in bpy.data.images))
        self.assertTrue(any(r.job_id == "job_done_1" for r in self.runtime.state.jobs_view))
```

- [ ] **Step 2: Run to see them fail**

Run: `make test-blender` Expected: failures for missing `blender.apply_image`, `blender.handlers`, `generation.build_request`.

- [ ] **Step 3: Implement apply_image**

`scenario/blender/apply_image.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bring image results into Blender: datablocks, Image Editor window, textures, planes."""
import logging
import pathlib

import bpy

from . import runtime

log = logging.getLogger("scenario.image")


def _ensure_nodes(mat):
    if bpy.app.version < (5, 0, 0):
        mat.use_nodes = True
    if mat.node_tree is None:  # very old files
        mat.use_nodes = True
    return mat.node_tree


def load_image(path, pack=True):
    path = str(pathlib.Path(path))
    image = bpy.data.images.load(path, check_existing=True)
    if pack and image.packed_file is None:
        try:
            image.pack()
        except RuntimeError as err:
            log.warning("could not pack %s: %s", path, err)
    return image


def show_in_image_editor(image):
    """Prefer an existing Image Editor; otherwise open a new window showing the image."""
    wm = bpy.context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == 'IMAGE_EDITOR':
                area.spaces.active.image = image
                area.tag_redraw()
                return True
    if not wm.windows:
        return False
    window = wm.windows[0]
    try:
        with bpy.context.temp_override(window=window, screen=window.screen, area=window.screen.areas[0]):
            bpy.ops.wm.window_new()
        new_window = wm.windows[-1]
        area = new_window.screen.areas[0]
        area.type = 'IMAGE_EDITOR'
        area.spaces.active.image = image
        return True
    except (RuntimeError, IndexError) as err:
        log.warning("could not open an image window: %s", err)
        return False


def material_with_image(name, image):
    mat = bpy.data.materials.new(name)
    tree = _ensure_nodes(mat)
    nodes, links = tree.nodes, tree.links
    bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None) or nodes.new("ShaderNodeBsdfPrincipled")
    output = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None) or nodes.new("ShaderNodeOutputMaterial")
    if not any(l.to_node is output for l in links):
        links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    tex.location = (bsdf.location.x - 400, bsdf.location.y)
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def apply_as_texture(obj, image):
    mat = material_with_image(f"Scenario {image.name}", image)
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
    obj.active_material_index = 0
    _material_preview()
    return mat


def add_as_plane(context, image):
    scene = context.scene
    width, height = image.size[0] or 1, image.size[1] or 1
    aspect = width / height
    bpy.ops.mesh.primitive_plane_add(location=scene.cursor.location)
    plane = context.active_object
    plane.name = f"Scenario {image.name}"
    plane.scale = (aspect if aspect >= 1 else 1.0, 1.0 if aspect >= 1 else 1.0 / aspect, 1.0)
    region = _first_region_3d(context)
    if region is not None:
        plane.rotation_euler = region.view_rotation.to_euler()
    plane.data.materials.append(material_with_image(f"Scenario {image.name}", image))
    _material_preview()
    return plane


def on_image_result(rec):
    names = []
    for index, path in enumerate(rec.files):
        if not pathlib.Path(path).exists():
            continue
        image = load_image(path)
        names.append(image.name)
        if index == 0:
            show_in_image_editor(image)
    runtime.set_message(f"{len(names)} image(s) ready from {rec.model_id}")
    return names


def _first_region_3d(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                return area.spaces.active.region_3d
    return None


def _material_preview():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                shading = area.spaces.active.shading
                if shading.type == 'SOLID':
                    shading.type = 'MATERIAL'
```

- [ ] **Step 4: Implement generation, handlers and pump**

`scenario/blender/generation.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Glue between scene state, schemas, estimates and the job manager (main thread)."""
import logging
import time
from dataclasses import dataclass, field

import bpy

from . import params_ui, props, runtime
from ..core.api.catalog import DEFAULT_MODELS, models_for_lane
from ..core.api.errors import ScenarioError
from ..core.schema.params import build_body, missing_required_files, parse_schema, validate

log = logging.getLogger("scenario.generation")

LANE_KIND = {"image": "image", "video": "video", "3d": "3d", "material": "material", "render": "video"}
_schemas = {}


def lane_kind(lane):
    return LANE_KIND.get(lane, "image")


def schema_for(model_id):
    if not model_id or model_id == "NONE":
        return None
    schema = _schemas.get(model_id)
    if schema is None:
        record = runtime.state.records.get(model_id)
        if record is None:
            return None
        schema = parse_schema(record)
        _schemas[model_id] = schema
    return schema


def request_catalog():
    if runtime.state.catalog_loading or not runtime.online():
        return False
    try:
        manager = runtime.ensure_manager()
        catalog = runtime.ensure_catalog()
    except ScenarioError as err:
        runtime.set_message(err.reason)
        return False
    wanted = [m for lane in DEFAULT_MODELS for m in DEFAULT_MODELS[lane]]
    cached = catalog.load_list_cached("public")
    if cached:
        detailed = []
        for model_id in wanted:
            path = catalog.cache_dir / "models" / f"{model_id}.json"
            if path.exists():
                detailed.append(catalog.get(model_id))
        set_catalog(cached, detailed)
    runtime.state.catalog_loading = True
    manager.fetch_catalog(catalog, "public", wanted)
    return True


def set_catalog(records, detailed):
    for rec in detailed:
        runtime.state.records[rec.id] = rec
        _schemas.pop(rec.id, None)
    for rec in records:
        runtime.state.records.setdefault(rec.id, rec)
    for lane in props.GENERATION_LANES:
        lane_records = models_for_lane("video" if lane == "render" else lane, records)
        runtime.state.lane_models[lane] = lane_records
        runtime.set_enum_items(("models", lane), [(r.id, r.name, r.short_description) for r in lane_records])
    runtime.state.catalog_loaded = True
    runtime.state.catalog_loading = False
    for scene in bpy.data.scenes:
        for lane in props.GENERATION_LANES:
            lane_state = scene.scenario.lane_state(lane)
            on_model_changed(bpy.context, lane_state)


def ensure_record(model_id):
    """Return a detailed record (with parameters); fetch synchronously if only the list entry is known."""
    record = runtime.state.records.get(model_id)
    if record is not None and record.parameters:
        return record
    catalog = runtime.ensure_catalog()
    record = catalog.get(model_id)
    runtime.state.records[model_id] = record
    _schemas.pop(model_id, None)
    return record


def on_model_changed(context, lane_state):
    model_id = lane_state.model_id
    if not model_id or model_id == "NONE":
        return
    try:
        ensure_record(model_id)
    except ScenarioError as err:
        lane_state.last_error = err.reason
        return
    schema = schema_for(model_id)
    if schema is None:
        return
    params_ui.sync_params(lane_state, schema, model_id)
    props.mark_estimate_dirty(lane_state)


@dataclass
class Request:
    lane: str
    kind: str
    model_id: str
    body: dict
    files: dict = field(default_factory=dict)
    array_params: set = field(default_factory=set)
    errors: list = field(default_factory=list)
    pending_captures: list = field(default_factory=list)


def build_request(scene, lane, for_estimate=False):
    lane_state = scene.scenario.lane_state(lane)
    model_id = lane_state.model_id
    schema = schema_for(model_id)
    if schema is None:
        return Request(lane, lane_kind(lane), model_id, {}, errors=["Model not loaded yet"])
    values, enabled = params_ui.collect_values(lane_state, schema)
    refs = params_ui.collect_file_refs(lane_state, schema)
    files, array_params, asset_ids = {}, set(), {}
    for spec in schema.specs:
        if not spec.is_file:
            continue
        if spec.ptype == "file_array":
            array_params.add(spec.name)
        for ref in refs.get(spec.name, []):
            if ref.source == 'ASSET' and ref.asset_id:
                asset_ids.setdefault(spec.name, []).append(ref.asset_id)
            elif ref.source == 'FILE' and ref.filepath:
                files.setdefault(spec.name, []).append(bpy.path.abspath(ref.filepath))
            elif ref.source == 'RENDER':
                path = _save_render_result(scene)
                if path:
                    files.setdefault(spec.name, []).append(path)
    body = build_body(schema.specs, values, asset_ids, enabled=enabled)
    errors = validate(schema.specs, {**body, **{k: v for k, v in files.items()}})
    if for_estimate:
        missing = missing_required_files(schema.specs, {**body, **files})
        if missing:
            errors.append("Add a reference to see the cost")
    return Request(lane, lane_kind(lane), model_id, body, files, array_params, errors)


def request_estimate(scene, lane):
    lane_state = scene.scenario.lane_state(lane)
    request = build_request(scene, lane, for_estimate=True)
    if request.errors:
        lane_state.estimate_state = 'UNAVAILABLE'
        lane_state.estimate_error = request.errors[0]
        return
    key = f"{lane}:{request.model_id}:{time.time():.3f}"
    lane_state.estimate_key = key
    lane_state.estimate_state = 'PENDING'
    try:
        runtime.ensure_manager().estimate(key, request.model_id, request.body)
    except ScenarioError as err:
        lane_state.estimate_state = 'ERROR'
        lane_state.estimate_error = err.reason


def submit_generation(context, lane):
    scene = context.scene
    lane_state = scene.scenario.lane_state(lane)
    request = build_request(scene, lane)
    if request.errors:
        raise ScenarioError(0, "; ".join(request.errors))
    manager = runtime.ensure_manager()
    rec = manager.submit(lane, request.kind, request.model_id, request.body, files=request.files, array_params=request.array_params,
                         meta={"prompt": lane_state.prompt, "model_name": runtime.state.records[request.model_id].name if request.model_id in runtime.state.records else request.model_id})
    runtime.state.jobs_view.insert(0, rec)
    lane_state.last_error = ""
    runtime.set_message(f"Submitted to {rec.meta.get('model_name', rec.model_id)}")
    return rec


def _save_render_result(scene):
    image = bpy.data.images.get("Render Result")
    if image is None:
        return None
    path = runtime.paths().cache_dir / "captures" / f"render_{int(time.time())}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        image.save_render(str(path), scene=scene)
    except RuntimeError as err:
        log.warning("no render result to save: %s", err)
        return None
    return str(path)
```

`scenario/blender/handlers.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Applies job-manager events on the main thread."""
import logging

import bpy

from . import apply_image, generation, props, runtime

log = logging.getLogger("scenario.handlers")

RESULT_HANDLERS = {"image": apply_image.on_image_result}


def dispatch(event):
    name, payload = event
    if name == "catalog":
        generation.set_catalog(payload["records"], payload["detailed"])
    elif name == "estimate":
        _on_estimate(payload)
    elif name in ("job", "job_done", "job_failed"):
        _on_job(name, payload)
    elif name == "error":
        runtime.set_message(str(payload))


def _on_estimate(result):
    for scene in bpy.data.scenes:
        for lane in props.GENERATION_LANES:
            lane_state = scene.scenario.lane_state(lane)
            if lane_state.estimate_key != result.key:
                continue
            if result.error:
                lane_state.estimate_state = 'ERROR'
                lane_state.estimate_error = result.error
            else:
                lane_state.estimate_state = 'READY'
                lane_state.estimate_cu = float(result.cu_cost or 0.0)
                lane_state.estimate_error = ""


def _on_job(name, rec):
    view = runtime.state.jobs_view
    if not any(r.local_id == rec.local_id for r in view):
        view.insert(0, rec)
    del view[50:]
    if name == "job_done":
        handler = RESULT_HANDLERS.get(rec.kind)
        if handler is None:
            runtime.set_message(f"{rec.kind} result ready in {rec.files[0] if rec.files else 'output folder'}")
            return
        try:
            handler(rec)
        except Exception as err:  # keep the pump alive, surface the failure
            log.exception("applying result failed")
            runtime.set_message(f"Result downloaded but could not be applied: {err}")
    elif name == "job_failed":
        runtime.set_message(f"Generation failed: {rec.error or rec.status}")
```

`scenario/blender/pump.py` (replace the stub):
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Main-thread pump: drains the job manager's event queue from a bpy.app.timers callback."""
import logging
import time

import bpy

from . import generation, handlers, props, runtime

log = logging.getLogger("scenario.pump")
ESTIMATE_DEBOUNCE = 0.7
ACTIVE_INTERVAL = 0.25
IDLE_INTERVAL = 0.6
_running = False


def start():
    global _running
    if bpy.app.background or _running:
        return
    bpy.app.timers.register(_tick, first_interval=0.5, persistent=True)
    _running = True


def stop():
    global _running
    if _running:
        try:
            bpy.app.timers.unregister(_tick)
        except ValueError:
            pass
    _running = False


def _tick():
    try:
        _process()
    except Exception:  # an exception here would silently kill the timer
        log.exception("pump tick failed")
    manager = runtime.state.manager
    return ACTIVE_INTERVAL if manager is not None and manager.has_active() else IDLE_INTERVAL


def _process():
    manager = runtime.state.manager
    changed = False
    if manager is not None:
        for event in manager.drain():
            handlers.dispatch(event)
            changed = True
    if not runtime.state.catalog_loaded and not runtime.state.catalog_loading and runtime.credentials().valid:
        generation.request_catalog()
    now = time.time()
    for scene in bpy.data.scenes:
        for lane in props.GENERATION_LANES:
            lane_state = scene.scenario.lane_state(lane)
            if lane_state.estimate_state == 'PENDING' and lane_state.estimate_dirty_at and now - lane_state.estimate_dirty_at >= ESTIMATE_DEBOUNCE:
                lane_state.estimate_dirty_at = 0.0
                if runtime.credentials().valid and runtime.online():
                    generation.request_estimate(scene, lane)
                changed = True
    if changed:
        redraw()


def redraw():
    wm = bpy.context.window_manager
    if wm is None:
        return
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type in ('VIEW_3D', 'PREFERENCES'):
                for region in area.regions:
                    if region.type in ('UI', 'HEADER', 'WINDOW'):
                        region.tag_redraw()
```

- [ ] **Step 5: Implement operators and panels**

`scenario/blender/operators.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators: connection test, catalog refresh, generate, references, results."""
import os

import bpy
from bpy.props import EnumProperty, IntProperty, StringProperty

from . import apply_image, generation, params_ui, props, runtime
from ..core.api.errors import ScenarioError


class SCENARIO_OT_test_connection(bpy.types.Operator):
    bl_idname = "scenario.test_connection"
    bl_label = "Test Scenario connection"
    bl_description = "Check the API key against Scenario and show the team and project it belongs to"

    def execute(self, context):
        if not runtime.online():
            self.report({'ERROR'}, "Allow Online Access is disabled in Blender's preferences")
            return {'CANCELLED'}
        try:
            data = runtime.make_client().get("/teams", timeout=15)
        except ScenarioError as err:
            runtime.state.account_label = ""
            self.report({'ERROR'}, f"Scenario: {err.reason}")
            return {'CANCELLED'}
        teams = data.get("teams") or []
        if not teams:
            runtime.state.account_label = "Connected (no team visible)"
        else:
            team = teams[0]
            projects = team.get("projects") or []
            project = projects[0]["name"] if projects else "?"
            runtime.state.account_label = f"{team.get('name', 'team')} / {project} ({team.get('plan', '')})"
        runtime.state.catalog_loaded = False
        self.report({'INFO'}, runtime.state.account_label)
        return {'FINISHED'}


class SCENARIO_OT_refresh_catalog(bpy.types.Operator):
    bl_idname = "scenario.refresh_catalog"
    bl_label = "Refresh models"
    bl_description = "Reload the model list from Scenario"

    def execute(self, context):
        runtime.state.catalog_loading = False
        if generation.request_catalog():
            self.report({'INFO'}, "Refreshing models")
            return {'FINISHED'}
        self.report({'WARNING'}, runtime.state.last_message or "Could not refresh (check preferences)")
        return {'CANCELLED'}


class SCENARIO_OT_generate(bpy.types.Operator):
    bl_idname = "scenario.generate"
    bl_label = "Generate"
    bl_description = "Submit this generation to Scenario"
    lane: StringProperty(default="image")

    @classmethod
    def poll(cls, context):
        return runtime.online() and runtime.credentials().valid

    def execute(self, context):
        try:
            rec = generation.submit_generation(context, self.lane)
        except ScenarioError as err:
            context.scene.scenario.lane_state(self.lane).last_error = err.reason
            self.report({'ERROR'}, err.reason)
            return {'CANCELLED'}
        self.report({'INFO'}, f"Generating with {rec.meta.get('model_name', rec.model_id)}")
        return {'FINISHED'}


class SCENARIO_OT_add_reference(bpy.types.Operator):
    bl_idname = "scenario.add_reference"
    bl_label = "Add reference"
    bl_description = "Attach a file, the render result or a viewport capture to this parameter"
    lane: StringProperty()
    param_name: StringProperty()
    source: EnumProperty(items=props.REFERENCE_SOURCES, default='FILE')
    filepath: StringProperty(subtype='FILE_PATH')
    filter_glob: StringProperty(default="*.png;*.jpg;*.jpeg;*.webp;*.mp4;*.mov;*.webm;*.glb;*.fbx;*.obj", options={'HIDDEN'})

    def invoke(self, context, event):
        if self.source == 'FILE':
            context.window_manager.fileselect_add(self)
            return {'RUNNING_MODAL'}
        return self.execute(context)

    def execute(self, context):
        lane_state = context.scene.scenario.lane_state(self.lane)
        ref = lane_state.references.add()
        ref.param_name, ref.source = self.param_name, self.source
        if self.source == 'FILE':
            ref.filepath = self.filepath
            ref.label = os.path.basename(self.filepath)
        else:
            ref.label = dict((k, v) for k, v, _ in props.REFERENCE_SOURCES)[self.source]
        props.mark_estimate_dirty(lane_state)
        return {'FINISHED'}


class SCENARIO_OT_remove_reference(bpy.types.Operator):
    bl_idname = "scenario.remove_reference"
    bl_label = "Remove reference"
    lane: StringProperty()
    index: IntProperty()

    def execute(self, context):
        lane_state = context.scene.scenario.lane_state(self.lane)
        if 0 <= self.index < len(lane_state.references):
            lane_state.references.remove(self.index)
            props.mark_estimate_dirty(lane_state)
        return {'FINISHED'}


class SCENARIO_OT_toggle_multi(bpy.types.Operator):
    bl_idname = "scenario.toggle_multi"
    bl_label = "Toggle option"
    lane: StringProperty()
    param_name: StringProperty()
    value: StringProperty()

    def execute(self, context):
        lane_state = context.scene.scenario.lane_state(self.lane)
        index = lane_state.params.find(self.param_name)
        if index < 0:
            return {'CANCELLED'}
        item = lane_state.params[index]
        selected = params_ui.multi_selection(item)
        if self.value in selected:
            selected.remove(self.value)
        else:
            selected.append(self.value)
        params_ui.set_multi_selection(item, selected)
        props.mark_estimate_dirty(lane_state)
        return {'FINISHED'}


class SCENARIO_OT_open_output_folder(bpy.types.Operator):
    bl_idname = "scenario.open_output_folder"
    bl_label = "Open output folder"

    def execute(self, context):
        path = runtime.paths().output_dir
        path.mkdir(parents=True, exist_ok=True)
        bpy.ops.wm.path_open(filepath=str(path))
        return {'FINISHED'}


class SCENARIO_OT_show_image(bpy.types.Operator):
    bl_idname = "scenario.show_image"
    bl_label = "Show image"
    filepath: StringProperty()

    def execute(self, context):
        image = apply_image.load_image(self.filepath)
        apply_image.show_in_image_editor(image)
        return {'FINISHED'}


class SCENARIO_OT_apply_texture(bpy.types.Operator):
    bl_idname = "scenario.apply_texture"
    bl_label = "Apply as texture"
    bl_description = "Create a material with this image as Base Color on the active mesh"
    filepath: StringProperty()

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        apply_image.apply_as_texture(context.active_object, apply_image.load_image(self.filepath))
        return {'FINISHED'}


class SCENARIO_OT_add_plane(bpy.types.Operator):
    bl_idname = "scenario.add_plane"
    bl_label = "Add as plane"
    bl_description = "Add a view-facing plane at the 3D cursor with this image"
    filepath: StringProperty()

    def execute(self, context):
        apply_image.add_as_plane(context, apply_image.load_image(self.filepath))
        return {'FINISHED'}


class SCENARIO_OT_expand_prompt(bpy.types.Operator):
    bl_idname = "scenario.expand_prompt"
    bl_label = "Edit prompt"
    lane: StringProperty()
    prompt: StringProperty(name="Prompt")

    def invoke(self, context, event):
        self.prompt = context.scene.scenario.lane_state(self.lane).prompt
        return context.window_manager.invoke_props_dialog(self, width=600)

    def draw(self, context):
        self.layout.prop(self, "prompt", text="")

    def execute(self, context):
        context.scene.scenario.lane_state(self.lane).prompt = self.prompt
        return {'FINISHED'}


CLASSES = (SCENARIO_OT_test_connection, SCENARIO_OT_refresh_catalog, SCENARIO_OT_generate, SCENARIO_OT_add_reference,
           SCENARIO_OT_remove_reference, SCENARIO_OT_toggle_multi, SCENARIO_OT_open_output_folder, SCENARIO_OT_show_image,
           SCENARIO_OT_apply_texture, SCENARIO_OT_add_plane, SCENARIO_OT_expand_prompt)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
```

`scenario/blender/panels.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""N-panel: account strip, lane tabs, schema-driven lane forms, running jobs, results."""
import os

import bpy

from . import generation, params_ui, props, runtime

LANE_PLACEHOLDER = {"video": "Video lane arrives in P2", "render": "Render-to-real arrives in P2", "mcp": "MCP server arrives in P3", "history": "Generations history arrives in P1"}


def draw_account_strip(layout, context):
    creds = runtime.credentials()
    row = layout.row(align=True)
    if not creds.valid:
        row.label(text="Add your API key in Preferences", icon='ERROR')
        row.operator("preferences.addon_show", text="", icon='PREFERENCES').module = runtime.PACKAGE
        return False
    if not runtime.online():
        row.label(text="Online access is disabled", icon='ERROR')
        return False
    row.label(text=runtime.state.account_label or "Scenario", icon='CHECKMARK')
    row.operator("scenario.refresh_catalog", text="", icon='FILE_REFRESH')
    row.operator("preferences.addon_show", text="", icon='PREFERENCES').module = runtime.PACKAGE
    return True


def draw_references(layout, lane_state, schema):
    refs = params_ui.collect_file_refs(lane_state, schema)
    for spec in schema.specs:
        if not spec.is_file:
            continue
        box = layout.box()
        header = box.row()
        count = len(refs.get(spec.name, []))
        label = spec.label + (" (required)" if spec.required_always else "")
        header.label(text=f"{label}  {count}" + (f"/{spec.max_length}" if spec.max_length else ""), icon='IMAGE_DATA' if spec.kind == 'image' else 'FILE')
        add = header.operator_menu_enum("scenario.add_reference", "source", text="Add", icon='ADD')
        add.lane, add.param_name = lane_state.lane, spec.name
        for index, ref in enumerate(lane_state.references):
            if ref.param_name != spec.name:
                continue
            row = box.row(align=True)
            row.label(text=ref.label or ref.filepath or ref.source, icon='DOT')
            remove = row.operator("scenario.remove_reference", text="", icon='X')
            remove.lane, remove.index = lane_state.lane, index


def draw_generate_lane(layout, context, lane):
    lane_state = context.scene.scenario.lane_state(lane)
    if not runtime.state.catalog_loaded:
        layout.label(text="Loading models...", icon='TIME')
        return
    layout.prop(lane_state, "model_id", text="Model")
    record = runtime.state.records.get(lane_state.model_id)
    if record is not None and record.short_description:
        layout.label(text=record.short_description[:70], icon='INFO')
    schema = generation.schema_for(lane_state.model_id)
    if schema is None:
        layout.label(text=lane_state.last_error or "Model schema not loaded", icon='ERROR')
        return
    row = layout.row(align=True)
    row.prop(lane_state, "prompt", text="")
    row.operator("scenario.expand_prompt", text="", icon='GREASEPENCIL').lane = lane
    draw_references(layout, lane_state, schema)
    params_ui.draw_params(layout, lane_state, schema)
    row = layout.row(align=True)
    row.scale_y = 1.4
    text = "Generate"
    if lane_state.estimate_state == 'READY':
        text = f"Generate  ({lane_state.estimate_cu:g} CU)"
    elif lane_state.estimate_state == 'PENDING':
        text = "Generate  (estimating...)"
    row.operator("scenario.generate", text=text, icon='PLAY').lane = lane
    if lane_state.estimate_state in ('ERROR', 'UNAVAILABLE') and lane_state.estimate_error:
        layout.label(text=lane_state.estimate_error[:80], icon='INFO')
    if lane_state.last_error:
        layout.label(text=lane_state.last_error[:80], icon='ERROR')


class SCENARIO_PT_main(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Scenario"
    bl_label = "Scenario"

    def draw(self, context):
        layout = self.layout
        if not draw_account_strip(layout, context):
            return
        scenario = context.scene.scenario
        grid = layout.grid_flow(columns=4, align=True)
        grid.prop(scenario, "lane", expand=True)
        lane = scenario.lane
        if lane in ("image", "3d", "material"):
            draw_generate_lane(layout, context, lane)
        else:
            layout.label(text=LANE_PLACEHOLDER.get(lane, ""), icon='INFO')
        if runtime.state.last_message:
            layout.label(text=runtime.state.last_message[:80])


class SCENARIO_PT_jobs(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Scenario"
    bl_label = "Running"
    bl_parent_id = "SCENARIO_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return any(not r.is_terminal for r in runtime.state.jobs_view)

    def draw(self, context):
        for rec in runtime.state.jobs_view:
            if rec.is_terminal:
                continue
            row = self.layout.row()
            row.label(text=f"{rec.meta.get('model_name', rec.model_id)}  {rec.status} {int(rec.progress * 100)}%", icon='TIME')


class SCENARIO_PT_results(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Scenario"
    bl_label = "Results"
    bl_parent_id = "SCENARIO_PT_main"

    def draw(self, context):
        layout = self.layout
        layout.operator("scenario.open_output_folder", icon='FILE_FOLDER')
        shown = 0
        for rec in runtime.state.jobs_view:
            if not rec.is_terminal:
                continue
            box = layout.box()
            title = rec.meta.get("prompt") or rec.meta.get("model_name") or rec.model_id
            box.label(text=title[:60], icon='CHECKMARK' if rec.is_success else 'ERROR')
            if rec.error:
                box.label(text=rec.error[:70])
            for path in rec.files[:6]:
                if rec.kind == "image":
                    icon_id = _thumbnail(path)
                    row = box.row(align=True)
                    if icon_id:
                        row.template_icon(icon_value=icon_id, scale=3.0)
                    col = row.column(align=True)
                    col.operator("scenario.show_image", text="Show").filepath = path
                    col.operator("scenario.apply_texture", text="Apply as texture").filepath = path
                    col.operator("scenario.add_plane", text="Add as plane").filepath = path
                else:
                    box.label(text=os.path.basename(path), icon='FILE')
            shown += 1
            if shown >= 8:
                break
        if shown == 0:
            layout.label(text="Nothing generated yet")


def _thumbnail(path):
    if not os.path.exists(path) or not path.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        return 0
    previews = runtime.previews()
    key = path
    if key not in previews:
        previews.load(key, path, 'IMAGE')
    return previews[key].icon_id


CLASSES = (SCENARIO_PT_main, SCENARIO_PT_jobs, SCENARIO_PT_results)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
```

- [ ] **Step 6: Run the headless tests, then the placeholder-asset probe**

Run: `./tools/install_dev.sh && make test-blender` Expected: `Ran 16 tests ... OK`.
Probe (free, decides how file params are estimated): `set -a; source .env.local; set +a; curl -s -o /dev/null -w '%{http_code}\n' -u "$SCENARIO_API_KEY:$SCENARIO_API_SECRET" -H 'Content-Type: application/json' -X POST "$SCENARIO_API_BASE/generate/custom/model_google-gemini-3-1-flash?dryRun=true" -d '{"prompt":"x","referenceImages":["asset_placeholder000000000000"]}'`. If it prints `269`, placeholders are accepted: in `generation.build_request` (for_estimate branch) replace the `missing`/errors logic by substituting `"asset_placeholder000000000000"` for each pending file so the estimate includes reference cost. If it prints `400`, keep the current behaviour (cost hidden until upload).

- [ ] **Step 7: GUI screenshot check**

`tools/gui_screenshot.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Open Blender with the Scenario panel visible, screenshot it, quit.

Usage: blender --python tools/gui_screenshot.py -- /abs/out.png [lane]
"""
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "/tmp/scenario-panel.png"
LANE = argv[1] if len(argv) > 1 else "image"


def _shot():
    window = bpy.context.window_manager.windows[0]
    area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
    space = area.spaces.active
    space.show_region_ui = True
    bpy.context.scene.scenario.lane = LANE
    ui_region = next(r for r in area.regions if r.type == 'UI')
    try:
        ui_region.active_panel_category = "Scenario"
    except (AttributeError, TypeError):
        pass
    with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=ui_region):
        bpy.ops.screen.screenshot(filepath=OUT)
    print("screenshot saved", OUT)
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(_shot, first_interval=4.0)
```

Run: `mkdir -p ~/Developer/scratch/playwright-screenshots/scenario-blender && /Applications/Blender.app/Contents/MacOS/Blender --python tools/gui_screenshot.py -- ~/Developer/scratch/playwright-screenshots/scenario-blender/p0-image-lane.png image` then open the PNG with the Read tool and check: the Scenario tab shows the account strip, the lane tabs, a model dropdown, the prompt row, the reference box and a Generate button with a CU figure (the API key must be set in Preferences first: set it once via `--python-expr` using the values from `.env.local`, never typed into a commit).

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat(blender): pump, catalog loading, Image lane panel, operators and image import"
```

---

### Task 11: Viewport header popover, opt-in smoke test, docs and merge

**Files:**
- Create: `scenario/blender/popover.py`, `tests/smoke/smoke_image.py`, `CHANGELOG.md`
- Modify: `scenario/blender/registry.py` (add `popover` to `_modules()`), `README.md`, `CLAUDE.md`
- Test: `tests/blender/test_popover.py`

**Interfaces:**
- Produces: `SCENARIO_PT_popover` (INSTANCED header popover with model, prompt, Generate for the active lane), `popover.register()/unregister()` (appends `draw_header_button` to `bpy.types.VIEW3D_HT_header`).

- [ ] **Step 1: Write the failing headless test**

`tests/blender/test_popover.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

import bpy

from helpers import submodule


class PopoverTests(unittest.TestCase):
    def test_popover_panel_registered_and_header_hooked(self):
        popover = submodule("blender.popover")
        self.assertTrue(hasattr(bpy.types, "SCENARIO_PT_popover"))
        self.assertIn('INSTANCED', bpy.types.SCENARIO_PT_popover.bl_options)
        draw_funcs = [f.__name__ for f in bpy.types.VIEW3D_HT_header._dyn_ui_initialize()]
        self.assertIn(popover.draw_header_button.__name__, draw_funcs)
```

- [ ] **Step 2: Run to see it fail**

Run: `make test-blender` Expected: `ModuleNotFoundError: blender.popover`.

- [ ] **Step 3: Implement the popover**

`scenario/blender/popover.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""A native floating composer: a header button opening a popover with model, prompt and Generate."""
import bpy

from . import generation, runtime


class SCENARIO_PT_popover(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_label = "Scenario"
    bl_options = {'INSTANCED'}
    bl_ui_units_x = 22

    def draw(self, context):
        layout = self.layout
        scenario = context.scene.scenario
        if not runtime.credentials().valid:
            layout.label(text="Add your API key in Preferences", icon='ERROR')
            return
        row = layout.row(align=True)
        row.prop(scenario, "lane", text="")
        lane = scenario.lane if scenario.lane in ("image", "3d", "material") else "image"
        lane_state = scenario.lane_state(lane)
        if not runtime.state.catalog_loaded:
            layout.label(text="Loading models...", icon='TIME')
            return
        layout.prop(lane_state, "model_id", text="")
        layout.prop(lane_state, "prompt", text="")
        text = "Generate"
        if lane_state.estimate_state == 'READY':
            text = f"Generate  ({lane_state.estimate_cu:g} CU)"
        layout.operator("scenario.generate", text=text, icon='PLAY').lane = lane
        if lane_state.last_error:
            layout.label(text=lane_state.last_error[:60], icon='ERROR')
        _ = generation  # keeps the import explicit for readers: the popover shares generation state


def draw_header_button(self, context):
    if context.space_data is None or context.space_data.type != 'VIEW_3D':
        return
    self.layout.popover(panel="SCENARIO_PT_popover", text="Scenario", icon='SHADERFX')


def register():
    bpy.utils.register_class(SCENARIO_PT_popover)
    bpy.types.VIEW3D_HT_header.append(draw_header_button)


def unregister():
    bpy.types.VIEW3D_HT_header.remove(draw_header_button)
    bpy.utils.unregister_class(SCENARIO_PT_popover)
```

In `scenario/blender/registry.py`, change `_modules()` to import and return `[props, operators, panels, popover]`.

- [ ] **Step 4: Run the headless tests and take a screenshot of the popover**

Run: `./tools/install_dev.sh && make test-blender` Expected: `Ran 17 tests ... OK`.
Screenshot: `/Applications/Blender.app/Contents/MacOS/Blender --python tools/gui_screenshot.py -- ~/Developer/scratch/playwright-screenshots/scenario-blender/p0-header.png image` and confirm the "Scenario" button sits in the viewport header (open the PNG with Read).

- [ ] **Step 5: Opt-in smoke test (spends about 13 CU) and record the outcome**

`tests/smoke/smoke_image.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end smoke: one small Gemini image through the core (no Blender). Spends credits.

Usage: SCENARIO_SMOKE=1 python3 tests/smoke/smoke_image.py
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

if os.environ.get("SCENARIO_SMOKE") != "1":
    sys.exit("set SCENARIO_SMOKE=1 to spend credits")
env = config.load_dotenv(ROOT / ".env.local")
creds = config.resolve_credentials(env.get("SCENARIO_API_KEY"), env.get("SCENARIO_API_SECRET"), environ={})
client = ScenarioClient(creds.key, creds.secret)
tmp = pathlib.Path(tempfile.mkdtemp(prefix="scenario-smoke-"))
paths = config.Paths(state_dir=tmp / "state", cache_dir=tmp / "cache", output_dir=tmp / "out")
catalog = Catalog(client, paths.cache_dir)
record = catalog.get("model_google-gemini-3-1-flash")
schema = parse_schema(record)
body = build_body(schema.specs, {"prompt": "a small copper teapot on a wooden table, studio light", "resolution": "512", "numOutputs": 1}, files={})
manager = JobManager(lambda: client, JobRegistry(paths.registry_file), paths)
manager.estimate("smoke", record.id, body)
manager.join(timeout=30)
print("estimate:", [e for e in manager.drain() if e[0] == "estimate"])
rec = manager.submit("image", "image", record.id, body)
deadline = time.time() + 300
while time.time() < deadline:
    events = manager.drain()
    for name, payload in events:
        print(name, getattr(payload, "status", payload))
        if name in ("job_done", "job_failed"):
            print("files:", payload.files, "cu:", payload.cu_cost, "error:", payload.error)
            sys.exit(0 if name == "job_done" else 1)
    time.sleep(1)
sys.exit("timeout")
```

Run: `SCENARIO_SMOKE=1 python3 tests/smoke/smoke_image.py` Expected: an estimate event with a CU figure, then `job_done` with one PNG path. Note the CU spent in the commit message.

- [ ] **Step 6: Docs**

`CHANGELOG.md`:
```markdown
# Changelog

## 0.1.0 (P0, 2026-08-28)
- Extension skeleton (Blender 4.2+, pure Python), preferences with API key and secret, output folder.
- REST client with Basic auth, retries, dry-run cost preview.
- Model catalog with disk cache, schema-driven parameter UI.
- Image lane: prompt, references (file, render result), live CU estimate on the Generate button, results loaded as images with Show / Apply as texture / Add as plane.
- Threaded job manager with persisted registry (unfinished jobs resume after restart).
- Viewport header popover.
```

Update `README.md`: add `scenario/`, `tests/`, `tools/`, `dist/` (ignored) to the file list, a "Run it" section (`./tools/install_dev.sh`, restart Blender, Preferences > Add-ons > Scenario: paste key and secret, N-panel > Scenario tab), a "Tests" section (`make test`, `make test-blender`, `SCENARIO_SMOKE=1 python3 tests/smoke/smoke_image.py`), and append the CU spent so far. Update `CLAUDE.md` state line to "P0 done, P1 next" and keep the resume line.

- [ ] **Step 7: Merge**

```bash
make test && make test-blender && git add -A && git commit -m "feat(blender): header popover, smoke test, P0 docs" && git checkout main && git merge --no-ff p0-skeleton-image-lane -m "Merge P0: skeleton and Image lane" && git log --oneline | head -3
```
