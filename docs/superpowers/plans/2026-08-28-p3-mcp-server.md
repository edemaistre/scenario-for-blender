# Scenario for Blender P3 Implementation Plan (local MCP server)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let agents (Claude Code, Cursor, Claude Desktop, Codex) build and generate inside the open Blender through a local MCP server that exposes Blender scene tools and Scenario generation tools, with a copy-paste setup from the MCP tab and a consent switch for Python execution.

**Architecture:** `scenario/mcp/protocol.py` is pure Python: JSON-RPC 2.0 + MCP methods (`initialize`, `notifications/initialized`, `ping`, `tools/list`, `tools/call`) dispatching to a tool registry, unit-tested. `scenario/mcp/server.py` runs a stdlib `http.server` on `127.0.0.1:<port>` in a background thread (Streamable HTTP, JSON responses, bearer token), and hands every `tools/call` to the main thread through a request queue drained by the pump (`server.process_pending()`), each request waiting on an Event with a timeout. `scenario/mcp/tools_blender.py` and `tools_scenario.py` implement the tools on the main thread. `scenario/mcp/stdio_shim.py` is a standalone script (no bpy) bridging stdio JSON-RPC to the local HTTP server for clients without HTTP transport. A CLI sub-command `scenario-mcp` serves headless with a blocking loop.

**Tech Stack:** stdlib `http.server`, `threading`, `queue`, `json`, `secrets`; Blender `bpy.app.timers` pump; `bpy.utils.register_cli_command`.

**Spec:** `docs/superpowers/specs/2026-08-28-scenario-for-blender-design.md` (3.1 `mcp/`, 4 MCP lane)

## Global Constraints

Same as the P0 plan, plus:
- Bind to `127.0.0.1` only. Every request needs `Authorization: Bearer <token>`; the token is generated per Blender session (`secrets.token_urlsafe(24)`), shown in the MCP panel and embedded in the copied configs. Unauthorized: 401.
- `execute_python` runs only when the preference `mcp_allow_python` is on (default on) and the result reports stdout/stderr and the `result` dict; `sys.exit`, `wm.quit_blender`, `wm.read_factory_settings`, `wm.read_factory_userpref`, `wm.read_userpref` are blocked with a readable error.
- Requests are capped at 10 MiB; a tool call that takes longer than 120 s on the main thread returns a JSON-RPC error (-32000, "timeout") without killing the server.
- Never start the server when `bpy.app.online_access` is False (loopback is still a network socket; follow the Blender Lab convention) and surface why in the panel.
- Branch `p3-mcp-server`, merge `--no-ff` into `main` at the end.

---

### Task 24: MCP protocol and tool registry (pure Python)

**Files:**
- Create: `scenario/mcp/__init__.py`, `scenario/mcp/protocol.py`
- Test: `tests/unit/test_mcp_protocol.py`

**Interfaces:**
- `ToolSpec(name, description, input_schema: dict, handler: Callable[[dict], dict|str|list])`; `Registry()` with `.add(spec)`, `.get(name)`, `.list_payload() -> list[dict]`.
- `handle_message(message: dict, registry, server_info, executor=None) -> dict | None`: returns the JSON-RPC response (None for notifications). `executor(handler, arguments) -> result` lets the server run handlers on the main thread; default calls the handler directly.
- Result conversion: `str` -> `[{"type": "text", "text": str}]`; `dict` -> text with `json.dumps`; a dict with `{"_image": base64, "mimeType": ...}` -> image content; exceptions -> `{"isError": true}` with the message.
- Error codes: -32700 parse, -32600 invalid request, -32601 method not found, -32602 invalid params (unknown tool), -32000 tool timeout.
- `PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")`; `initialize` echoes the client's version when supported, else the latest.

- [ ] **Step 1: Failing tests**

`tests/unit/test_mcp_protocol.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json

from scenario.mcp import protocol

INFO = {"name": "scenario-blender", "version": "0.4.0"}


def registry():
    reg = protocol.Registry()
    reg.add(protocol.ToolSpec("echo", "Echo arguments", {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}, lambda args: {"echo": args["text"]}))
    reg.add(protocol.ToolSpec("boom", "Always fails", {"type": "object", "properties": {}}, lambda args: (_ for _ in ()).throw(RuntimeError("kaput"))))
    reg.add(protocol.ToolSpec("shot", "Image", {"type": "object", "properties": {}}, lambda args: {"_image": "aGk=", "mimeType": "image/png"}))
    return reg


def test_initialize_echoes_supported_version_and_lists_tools_capability():
    resp = protocol.handle_message({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}, registry(), INFO)
    assert resp["id"] == 1 and resp["result"]["protocolVersion"] == "2025-03-26"
    assert resp["result"]["serverInfo"] == INFO and "tools" in resp["result"]["capabilities"]
    newer = protocol.handle_message({"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": "2099-01-01"}}, registry(), INFO)
    assert newer["result"]["protocolVersion"] == protocol.PROTOCOL_VERSIONS[0]


def test_notifications_return_none_and_ping_returns_empty_result():
    assert protocol.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}, registry(), INFO) is None
    assert protocol.handle_message({"jsonrpc": "2.0", "id": 3, "method": "ping"}, registry(), INFO)["result"] == {}


def test_tools_list_and_call_text_result():
    reg = registry()
    listed = protocol.handle_message({"jsonrpc": "2.0", "id": 4, "method": "tools/list"}, reg, INFO)["result"]["tools"]
    assert [t["name"] for t in listed] == ["echo", "boom", "shot"] and listed[0]["inputSchema"]["required"] == ["text"]
    called = protocol.handle_message({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "echo", "arguments": {"text": "hi"}}}, reg, INFO)
    content = called["result"]["content"]
    assert content[0]["type"] == "text" and json.loads(content[0]["text"]) == {"echo": "hi"}
    assert called["result"].get("isError") is not True


def test_tool_errors_and_unknown_tools():
    reg = registry()
    failed = protocol.handle_message({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "boom", "arguments": {}}}, reg, INFO)
    assert failed["result"]["isError"] is True and "kaput" in failed["result"]["content"][0]["text"]
    unknown = protocol.handle_message({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "nope"}}, reg, INFO)
    assert unknown["error"]["code"] == -32602
    missing = protocol.handle_message({"jsonrpc": "2.0", "id": 8, "method": "no/such"}, reg, INFO)
    assert missing["error"]["code"] == -32601
    bad = protocol.handle_message({"id": 9}, reg, INFO)
    assert bad["error"]["code"] == -32600


def test_image_results_and_executor_hook():
    reg = registry()
    shot = protocol.handle_message({"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {"name": "shot", "arguments": {}}}, reg, INFO)
    assert shot["result"]["content"][0] == {"type": "image", "data": "aGk=", "mimeType": "image/png"}
    seen = []

    def executor(handler, arguments):
        seen.append(arguments)
        return handler(arguments)

    protocol.handle_message({"jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": {"name": "echo", "arguments": {"text": "x"}}}, reg, INFO, executor=executor)
    assert seen == [{"text": "x"}]


def test_timeout_error_from_executor():
    def executor(handler, arguments):
        raise protocol.ToolTimeout("main thread busy")

    resp = protocol.handle_message({"jsonrpc": "2.0", "id": 12, "method": "tools/call", "params": {"name": "echo", "arguments": {"text": "x"}}}, registry(), INFO, executor=executor)
    assert resp["error"]["code"] == -32000 and "busy" in resp["error"]["message"]
```

- [ ] **Step 2: Implement** `scenario/mcp/protocol.py`

```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""JSON-RPC 2.0 + MCP method handling. No bpy, no sockets: pure functions over dicts."""
import json
import traceback
from dataclasses import dataclass, field

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR, TOOL_TIMEOUT = -32700, -32600, -32601, -32602, -32603, -32000


class ToolTimeout(Exception):
    pass


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    handler: object
    annotations: dict = field(default_factory=dict)


class Registry:
    def __init__(self):
        self._tools = {}

    def add(self, spec):
        self._tools[spec.name] = spec
        return spec

    def get(self, name):
        return self._tools.get(name)

    def names(self):
        return list(self._tools)

    def list_payload(self):
        out = []
        for spec in self._tools.values():
            item = {"name": spec.name, "description": spec.description, "inputSchema": spec.input_schema}
            if spec.annotations:
                item["annotations"] = spec.annotations
            out.append(item)
        return out


def _error(msg_id, code, message, data=None):
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": msg_id, "error": err}


def _result(msg_id, result):
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def to_content(value):
    if isinstance(value, dict) and "_image" in value:
        return [{"type": "image", "data": value["_image"], "mimeType": value.get("mimeType", "image/png")}]
    if isinstance(value, list) and value and all(isinstance(v, dict) and "type" in v for v in value):
        return value
    if isinstance(value, str):
        return [{"type": "text", "text": value}]
    return [{"type": "text", "text": json.dumps(value, indent=1, default=str)}]


def handle_message(message, registry, server_info, executor=None):
    if not isinstance(message, dict) or "method" not in message:
        return _error(message.get("id") if isinstance(message, dict) else None, INVALID_REQUEST, "Invalid JSON-RPC request")
    method, msg_id, params = message["method"], message.get("id"), message.get("params") or {}
    if msg_id is None:  # notification
        return None
    if method == "initialize":
        wanted = params.get("protocolVersion")
        version = wanted if wanted in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        return _result(msg_id, {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}}, "serverInfo": dict(server_info),
                               "instructions": "Blender is open on the user's machine. Use scene_summary first, prefer the specific tools over execute_python, and quote costs (CU) before generating."})
    if method == "ping":
        return _result(msg_id, {})
    if method == "tools/list":
        return _result(msg_id, {"tools": registry.list_payload()})
    if method == "tools/call":
        name = params.get("name")
        spec = registry.get(name) if name else None
        if spec is None:
            return _error(msg_id, INVALID_PARAMS, f"Unknown tool: {name}")
        arguments = params.get("arguments") or {}
        try:
            value = executor(spec.handler, arguments) if executor else spec.handler(arguments)
        except ToolTimeout as err:
            return _error(msg_id, TOOL_TIMEOUT, f"Tool timeout: {err}")
        except Exception as err:  # tool failures are results, not protocol errors
            text = f"{type(err).__name__}: {err}\n{traceback.format_exc(limit=3)}"
            return _result(msg_id, {"content": [{"type": "text", "text": text}], "isError": True})
        return _result(msg_id, {"content": to_content(value)})
    return _error(msg_id, METHOD_NOT_FOUND, f"Method not found: {method}")


def parse_body(raw):
    try:
        return json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw), None
    except (ValueError, UnicodeDecodeError) as err:
        return None, _error(None, PARSE_ERROR, f"Parse error: {err}")
```

Run tests (6 passed), commit `feat(mcp): JSON-RPC and MCP protocol handling with a tool registry`.

---

### Task 25: HTTP server thread with main-thread executor, bearer auth, headless CLI loop

**Files:**
- Create: `scenario/mcp/server.py`
- Modify: `scenario/blender/pump.py` (call `mcp_server.process_pending()` each tick), `scenario/blender/registry.py` (start/stop with the add-on, register the CLI command), `scenario/blender/runtime.py` (`state.mcp` holder)
- Test: `tests/blender/test_mcp_server.py`

**Interfaces:**
- `McpServer(host, port, token, registry, server_info, timeout=120.0)` with `.start() -> (host, port)` (tries `port`, then the next 3), `.stop()`, `.running`, `.url` (`http://127.0.0.1:<port>/mcp`), `.process_pending(max_items=8)` (main thread: executes queued handler calls), `.serve_blocking(stop_event)` (headless: runs `process_pending` in a loop with a small sleep).
- HTTP: `POST /mcp` with bearer -> JSON response (200) or 202 for notifications; `GET /mcp` -> 405; `DELETE /mcp` -> 200; wrong or missing token -> 401 with `WWW-Authenticate: Bearer`; body over 10 MiB -> 413; `GET /health` (no auth) -> `{"ok": true, "blender": version}`.
- The executor puts `(handler, arguments, Event, box)` on `self._queue` and waits `timeout` seconds; `process_pending` pops items, runs `box["result"] = handler(arguments)` (or stores the exception) and sets the event.

- [ ] **Step 1: Failing headless test** (server thread + manual `process_pending` because timers do not run headless)

`tests/blender/test_mcp_server.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import threading
import time
import unittest
import urllib.error
import urllib.request

from helpers import submodule


def post(url, token, payload, method="POST"):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream", **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as err:
        return err.code, None


class McpServerTests(unittest.TestCase):
    def setUp(self):
        protocol = submodule("mcp.protocol")
        server_mod = submodule("mcp.server")
        reg = protocol.Registry()
        reg.add(protocol.ToolSpec("echo", "Echo", {"type": "object", "properties": {"text": {"type": "string"}}}, lambda a: {"echo": a.get("text")}))
        self.server = server_mod.McpServer("127.0.0.1", 39876, "tok", reg, {"name": "test", "version": "0"}, timeout=5.0)
        host, port = self.server.start()
        self.url = f"http://{host}:{port}/mcp"
        self.pump = threading.Thread(target=self._pump, daemon=True)
        self.stop = threading.Event()
        self.pump.start()

    def _pump(self):
        while not self.stop.is_set():
            self.server.process_pending()
            time.sleep(0.02)

    def tearDown(self):
        self.stop.set()
        self.server.stop()

    def test_initialize_list_and_call_over_http(self):
        status, body = post(self.url, "tok", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
        self.assertEqual(status, 200)
        self.assertEqual(body["result"]["serverInfo"]["name"], "test")
        status, body = post(self.url, "tok", {"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual(status, 202)
        status, body = post(self.url, "tok", {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "echo", "arguments": {"text": "hi"}}})
        self.assertEqual(json.loads(body["result"]["content"][0]["text"]), {"echo": "hi"})

    def test_auth_and_methods(self):
        self.assertEqual(post(self.url, None, {"jsonrpc": "2.0", "id": 1, "method": "ping"})[0], 401)
        self.assertEqual(post(self.url, "wrong", {"jsonrpc": "2.0", "id": 1, "method": "ping"})[0], 401)
        self.assertEqual(post(self.url, "tok", None, method="GET")[0], 405)
        status, body = post(self.url.replace("/mcp", "/health"), None, None, method="GET")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])

    def test_timeout_when_main_thread_never_processes(self):
        self.stop.set()
        self.pump.join(timeout=1)
        self.server.timeout = 0.3
        status, body = post(self.url, "tok", {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "echo", "arguments": {}}})
        self.assertEqual(status, 200)
        self.assertEqual(body["error"]["code"], -32000)
```

- [ ] **Step 2: Implement** `scenario/mcp/server.py`

```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Local MCP server over Streamable HTTP. The HTTP thread never touches bpy: tool handlers run on the
main thread through process_pending(), called by the pump (GUI) or serve_blocking() (headless)."""
import http.server
import json
import logging
import queue
import socket
import threading
import time

from . import protocol

log = logging.getLogger("scenario.mcp")
MAX_BODY = 10 * 1024 * 1024


class _Pending:
    __slots__ = ("handler", "arguments", "event", "result", "error")

    def __init__(self, handler, arguments):
        self.handler, self.arguments = handler, arguments
        self.event = threading.Event()
        self.result, self.error = None, None


class McpServer:
    def __init__(self, host, port, token, registry, server_info, timeout=120.0, blender_version=""):
        self.host, self.port, self.token = host, int(port), token
        self.registry, self.server_info, self.timeout = registry, server_info, timeout
        self.blender_version = blender_version
        self._queue = queue.Queue()
        self._httpd = None
        self._thread = None

    # -- lifecycle --------------------------------------------------------
    @property
    def running(self):
        return self._httpd is not None

    @property
    def url(self):
        return f"http://{self.host}:{self.port}/mcp"

    def start(self):
        server = self
        last_error = None
        for candidate in range(self.port, self.port + 4):
            try:
                httpd = http.server.ThreadingHTTPServer((self.host, candidate), _make_handler(server))
                httpd.daemon_threads = True
                self.port = candidate
                self._httpd = httpd
                break
            except OSError as err:
                last_error = err
        if self._httpd is None:
            raise OSError(f"no free port from {self.port}: {last_error}")
        self._thread = threading.Thread(target=self._httpd.serve_forever, kwargs={"poll_interval": 0.25}, daemon=True, name="scenario-mcp-http")
        self._thread.start()
        log.info("MCP server listening on %s", self.url)
        return self.host, self.port

    def stop(self):
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    # -- main-thread executor ---------------------------------------------
    def executor(self, handler, arguments):
        pending = _Pending(handler, arguments)
        self._queue.put(pending)
        if not pending.event.wait(self.timeout):
            raise protocol.ToolTimeout(f"no response from Blender's main thread within {self.timeout:g} s")
        if pending.error is not None:
            raise pending.error
        return pending.result

    def process_pending(self, max_items=8):
        done = 0
        while done < max_items:
            try:
                pending = self._queue.get_nowait()
            except queue.Empty:
                return done
            try:
                pending.result = pending.handler(pending.arguments)
            except Exception as err:  # delivered to the HTTP thread as a tool error
                pending.error = err
            finally:
                pending.event.set()
            done += 1
        return done

    def serve_blocking(self, stop_event, interval=0.05):
        while not stop_event.is_set():
            if not self.process_pending():
                time.sleep(interval)

    def handle(self, message):
        return protocol.handle_message(message, self.registry, self.server_info, executor=self.executor)


def _make_handler(server):
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            log.debug("http %s", fmt % args)

        def _send(self, status, body=None, headers=None):
            raw = json.dumps(body).encode("utf-8") if body is not None else b""
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if raw:
                self.wfile.write(raw)

        def _authorized(self):
            header = self.headers.get("Authorization", "")
            return header.startswith("Bearer ") and header[7:].strip() == server.token

        def do_GET(self):
            if self.path.rstrip("/") == "/health":
                return self._send(200, {"ok": True, "blender": server.blender_version, "server": server.server_info})
            if not self._authorized():
                return self._send(401, {"error": "unauthorized"}, {"WWW-Authenticate": "Bearer"})
            self._send(405, {"error": "SSE streams are not offered; use POST"}, {"Allow": "POST, DELETE"})

        def do_DELETE(self):
            self._send(200 if self._authorized() else 401, {})

        def do_POST(self):
            if self.path.rstrip("/") != "/mcp":
                return self._send(404, {"error": "not found"})
            if not self._authorized():
                return self._send(401, {"error": "unauthorized"}, {"WWW-Authenticate": "Bearer"})
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                return self._send(413, {"error": "request too large"})
            raw = self.rfile.read(length) if length else b""
            message, parse_error = protocol.parse_body(raw)
            if parse_error:
                return self._send(400, parse_error)
            if isinstance(message, list):
                responses = [r for r in (server.handle(m) for m in message) if r is not None]
                return self._send(200, responses) if responses else self._send(202)
            response = server.handle(message)
            if response is None:
                return self._send(202)
            self._send(200, response)

    return Handler
```

Wire-up: `runtime.state.mcp = None`; new module `scenario/blender/mcp_service.py` with `start()` (builds the registry from `tools_blender`/`tools_scenario`, token `secrets.token_urlsafe(24)` kept in `runtime.state.mcp_token`, `McpServer("127.0.0.1", prefs.mcp_port, ...)`, skipped when `not runtime.online()`), `stop()`, `status() -> dict(running, url, token, error)`, `client_configs() -> dict` (see Task 27). `pump._process` calls `runtime.state.mcp.process_pending()` when present. `registry.register()` calls `mcp_service.start()` after `pump.start()` (GUI only) and `unregister()` calls `mcp_service.stop()`. CLI: `bpy.utils.register_cli_command("scenario-mcp", _cli)` where `_cli(argv)` parses `--port`/`--token`, starts the server and runs `serve_blocking` until Ctrl-C (headless `blender --background file.blend --command scenario-mcp --port 9876 --token X`).

Run `./tools/install_dev.sh && make test-blender` (41 OK), commit `feat(mcp): local Streamable HTTP server with main-thread executor, auth and headless loop`.

---

### Task 26: Blender and Scenario tools

**Files:**
- Create: `scenario/mcp/tools_blender.py`, `scenario/mcp/tools_scenario.py`, `scenario/mcp/sandbox.py`
- Test: `tests/blender/test_mcp_tools.py`

**Interfaces (tool names and arguments):**
- Blender: `scene_summary()` -> objects (name, type, location, dimensions, parent, collections, material names), cameras, frame range, fps, units, active object, selected names, file path; `object_detail(name)`; `execute_python(code)` -> `{result, stdout, stderr}` (gated by `mcp_allow_python`; `result` is a dict the code fills); `screenshot_viewport()` -> image content (PNG via `screen.screenshot` in GUI, error headless); `render_still(width=1280, height=720, source='CAMERA'|'VIEWPORT')` -> image content using `capture.capture_still`; `set_frame(frame)`; `select_objects(names)`.
- Scenario: `list_models(lane, query="")` -> curated list with id, name, description, capabilities from the loaded catalog (lane in image/video/3d/material); `model_schema(model_id)` -> parameters summary; `estimate_cost(model_id, parameters)` -> CU (synchronous dry run, 20 s timeout, runs the HTTP call in the executor thread, not the main thread: mark the ToolSpec `annotations={"scenario:offthread": true}` and let `mcp_service` build the executor so off-thread tools bypass the queue); `generate(lane, model_id, parameters, apply=True)` -> `{job_id, local_id, cu_cost?}` (submits through `runtime.ensure_manager()`, the pump applies the result like a panel generation: image datablock, material on the selection, 3D at the cursor, video file); `job_status(local_id|job_id)` -> status, progress, files; `wait_for_job(local_id, timeout=170)` (off-thread: polls the registry record with sleep; never blocks the main thread); `import_result(local_id)` (re-applies a finished job); `capture_reference(source='VIEWPORT'|'CAMERA')` -> uploads a still and returns `asset_id` to use as a reference parameter; `list_generations(limit=20)` -> from `runtime.state.history` (refreshing if empty).
- `sandbox.run_python(code, allow=True) -> dict(result, stdout, stderr)`: exec in a fresh namespace with `bpy` and `result = {}` preloaded, stdout/stderr captured, blocked operators wrapped: `sys.exit` replaced, and `bpy.ops.wm.quit_blender/read_factory_settings/read_factory_userpref/read_userpref` refused via a guard that checks the operator id in a wrapper around `bpy.ops` calls (implement by temporarily replacing `bpy.ops.wm.quit_blender` and the three others with functions that raise `RuntimeError("blocked by Scenario MCP")`, restored in `finally`).

- [ ] **Step 1: Failing headless test**

`tests/blender/test_mcp_tools.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import unittest

import bpy

from helpers import FIXTURES, reset_scene, submodule


class McpToolsTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.tb = submodule("mcp.tools_blender")
        self.ts = submodule("mcp.tools_scenario")
        self.sandbox = submodule("mcp.sandbox")
        bpy.ops.mesh.primitive_cube_add(location=(1, 2, 3))
        bpy.context.active_object.name = "Crate"

    def test_scene_summary_and_object_detail(self):
        summary = self.tb.scene_summary({})
        names = [o["name"] for o in summary["objects"]]
        self.assertIn("Crate", names)
        self.assertEqual(summary["frame_range"], [bpy.context.scene.frame_start, bpy.context.scene.frame_end])
        detail = self.tb.object_detail({"name": "Crate"})
        self.assertEqual(detail["type"], 'MESH')
        self.assertAlmostEqual(detail["location"][2], 3.0)
        self.assertIn("vertices", detail)

    def test_execute_python_captures_output_and_result_and_blocks_quit(self):
        out = self.sandbox.run_python("import bpy\nprint('hello')\nresult['count'] = len(bpy.data.objects)")
        self.assertEqual(out["result"]["count"], len(bpy.data.objects))
        self.assertIn("hello", out["stdout"])
        blocked = self.sandbox.run_python("import bpy\nbpy.ops.wm.quit_blender()")
        self.assertIn("blocked", blocked["stderr"].lower() + blocked.get("error", "").lower())
        self.assertTrue(len(bpy.data.objects) >= 1)

    def test_execute_python_respects_preference(self):
        prefs = submodule("prefs").get_prefs()
        prefs.mcp_allow_python = False
        try:
            with self.assertRaises(PermissionError):
                self.tb.execute_python({"code": "result['x'] = 1"})
        finally:
            prefs.mcp_allow_python = True

    def test_list_models_uses_loaded_catalog(self):
        runtime = submodule("blender.runtime")
        catalog = submodule("core.api.catalog")
        handlers = submodule("blender.handlers")
        runtime.state.reset()
        rec = catalog.ModelRecord.from_api(json.loads((FIXTURES / "models" / "model_patina-material.json").read_text())["model"])
        handlers.dispatch(("catalog", {"privacy": "public", "records": [rec], "detailed": [rec]}))
        listed = self.ts.list_models({"lane": "material"})
        self.assertEqual(listed["models"][0]["id"], "model_patina-material")
        schema = self.ts.model_schema({"model_id": "model_patina-material"})
        self.assertIn("maps", [p["name"] for p in schema["parameters"]])
```

- [ ] **Step 2: Implement** the three modules per the interfaces above; `tools_blender.execute_python` raises `PermissionError("Python execution is disabled in Scenario preferences")` when the preference is off. `tools_scenario.generate` validates through `generation.schema_for`/`build_body` (`params = build_body(schema.specs, parameters, files_from_asset_ids)`; file params accept asset ids directly), then `runtime.ensure_manager().submit(lane, kind, model_id, body, meta={"prompt": ..., "model_name": ..., "source": "mcp", "target_objects": selected meshes})`. Register every tool in `mcp_service.build_registry()`.

Run tests (45 OK), commit `feat(mcp): Blender scene tools and Scenario generation tools`.

---

### Task 27: MCP panel, client configs, stdio shim, docs, merge

**Files:**
- Create: `scenario/mcp/stdio_shim.py` (standalone; stdlib only; reads newline-delimited JSON-RPC from stdin, POSTs each message to `--url` with `--token`, writes the JSON response line to stdout, prints nothing else; `python3 stdio_shim.py --url http://127.0.0.1:9876/mcp --token X`)
- Modify: `scenario/blender/panels.py` (`draw_mcp_lane`: status line Running on url / Stopped (reason), token (masked with a Copy button), Start/Stop, "Copy config for" buttons: Claude Code (`claude mcp add --transport http scenario-blender <url> --header "Authorization: Bearer <token>"`), Cursor (`mcp.json` snippet), Claude Desktop (stdio snippet using Blender's Python at `os.path.join(sys.prefix, "bin", "python3.X")` when it exists, else `python3`), Codex (`codex mcp add scenario-blender --url <url> --header ...` or the TOML snippet); a "Python execution" toggle mirroring the preference; a live counter of tool calls served)
- Modify: `scenario/blender/operators.py` (`scenario.mcp_start`, `scenario.mcp_stop`, `scenario.mcp_copy(kind)` writing to `context.window_manager.clipboard`)
- Test: `tests/unit/test_stdio_shim.py` (runs the shim as a subprocess against a tiny local HTTP stub started in the test, checks a request/response round trip), `tests/blender/test_mcp_panel.py` (configs contain the url and token; masked token in the panel text)
- Docs: CHANGELOG `0.4.0 (P3)`, README (MCP section with the three client setups and the headless command), CLAUDE.md state.

- [ ] Verification: GUI run with `tools/gui_screenshot.py` lane `mcp` (screenshot reviewed); then from this machine: `claude mcp add --transport http scenario-blender <url> --header "Authorization: Bearer <token>"` is NOT run automatically (it changes the user's Claude Code config); instead run a curl `initialize` + `tools/list` + `tools/call scene_summary` against the live GUI server and paste the summary in the README as the proof. Finally `make test && make test-blender`, merge `--no-ff` into main.
