# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lifecycle of the local MCP server inside Blender, plus client setup snippets."""
import json
import logging
import os
import secrets
import sys

import bpy

from . import runtime
from .. import __version__
from ..mcp import protocol
from ..mcp.server import McpServer

log = logging.getLogger("scenario.mcp")
SERVER_INFO = {"name": "scenario-blender", "version": __version__}


def build_registry():
    from ..mcp import tools_blender, tools_scenario

    registry = protocol.Registry()
    for spec in tools_blender.SPECS + tools_scenario.SPECS:
        registry.add(spec)
    return registry


def status():
    server = runtime.state.mcp
    return {"running": bool(server and server.running), "url": server.url if server else "", "token": runtime.state.mcp_token,
            "error": runtime.state.mcp_error, "calls": server.calls_served if server else 0}


def start():
    if runtime.state.mcp is not None and runtime.state.mcp.running:
        return runtime.state.mcp
    if not runtime.online():
        runtime.state.mcp_error = "Allow Online Access is off"
        return None
    prefs = runtime.prefs()
    port = prefs.mcp_port if prefs else 9876
    if not runtime.state.mcp_token:
        runtime.state.mcp_token = secrets.token_urlsafe(24)
    try:
        server = McpServer("127.0.0.1", port, runtime.state.mcp_token, build_registry(), SERVER_INFO, blender_version=bpy.app.version_string)
        server.start()
    except OSError as err:
        runtime.state.mcp_error = str(err)
        runtime.state.mcp = None
        return None
    runtime.state.mcp = server
    runtime.state.mcp_error = ""
    return server


def stop():
    server = runtime.state.mcp
    if server is not None:
        server.stop()
    runtime.state.mcp = None


def process_pending():
    server = runtime.state.mcp
    if server is not None:
        server.process_pending()


def _blender_python():
    candidates = [os.path.join(sys.prefix, "bin", f"python{sys.version_info.major}.{sys.version_info.minor}"), os.path.join(sys.prefix, "bin", "python3")]
    for path in candidates:
        if os.path.exists(path):
            return path
    return "python3"


def shim_path():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mcp", "stdio_shim.py")


def client_configs():
    st = status()
    url, token = st["url"] or "http://127.0.0.1:9876/mcp", st["token"] or "<token>"
    stdio = {"mcpServers": {"scenario-blender": {"command": _blender_python(), "args": [shim_path(), "--url", url, "--token", token]}}}
    return {
        "claude_code": f'claude mcp add --transport http scenario-blender {url} --header "Authorization: Bearer {token}"',
        "cursor": json.dumps({"mcpServers": {"scenario-blender": {"url": url, "headers": {"Authorization": f"Bearer {token}"}}}}, indent=2),
        "claude_desktop": json.dumps(stdio, indent=2),
        "codex": f'codex mcp add scenario-blender --url {url} --bearer-token-env-var SCENARIO_BLENDER_TOKEN\n# then: export SCENARIO_BLENDER_TOKEN={token}',
        "curl": f'curl -s -X POST {url} -H "Authorization: Bearer {token}" -H "Content-Type: application/json" -d \'{{"jsonrpc":"2.0","id":1,"method":"tools/list"}}\'',
    }


def cli(argv):
    """blender --background file.blend --command scenario-mcp [--port N] [--token T]"""
    import argparse
    import threading

    parser = argparse.ArgumentParser(prog="scenario-mcp")
    parser.add_argument("--port", type=int, default=9876)
    parser.add_argument("--token", default="")
    args = parser.parse_args(argv)
    runtime.state.mcp_token = args.token or secrets.token_urlsafe(24)
    server = McpServer("127.0.0.1", args.port, runtime.state.mcp_token, build_registry(), SERVER_INFO, blender_version=bpy.app.version_string)
    server.start()
    print(f"Scenario MCP serving on {server.url} (token {runtime.state.mcp_token})", flush=True)
    stop_event = threading.Event()
    try:
        server.serve_blocking(stop_event)
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        server.stop()
    return 0
