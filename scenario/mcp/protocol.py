# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""JSON-RPC 2.0 + MCP method handling. No bpy, no sockets: pure functions over dicts."""
import json
import traceback
from dataclasses import dataclass, field

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR, TOOL_TIMEOUT = -32700, -32600, -32601, -32602, -32603, -32000
INSTRUCTIONS = ("Blender is open on the user's machine. Start with scene_summary, prefer the specific tools over execute_python, "
                "quote the CU cost (estimate_cost) before generating, and place results where the user is working.")


class ToolTimeout(Exception):
    pass


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict
    handler: object
    annotations: dict = field(default_factory=dict)
    offthread: bool = False  # True: safe to run on the HTTP thread (network only, no bpy)


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
        return _result(msg_id, {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}}, "serverInfo": dict(server_info), "instructions": INSTRUCTIONS})
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
            if executor is not None and not spec.offthread:
                value = executor(spec.handler, arguments)
            else:
                value = spec.handler(arguments)
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
