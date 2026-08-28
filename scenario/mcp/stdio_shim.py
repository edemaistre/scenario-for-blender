#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""stdio <-> local HTTP bridge for MCP clients that only launch commands (Claude Desktop).

Reads newline-delimited JSON-RPC on stdin, forwards each message to the Scenario for Blender server,
writes the JSON response on stdout. Standard library only; no bpy.

Usage: python3 stdio_shim.py --url http://127.0.0.1:9876/mcp --token TOKEN
"""
import argparse
import json
import sys
import urllib.error
import urllib.request


def forward(url, token, message, timeout=300):
    data = json.dumps(message).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as err:
        body = err.read()
        try:
            return json.loads(body)
        except ValueError:
            return {"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": -32000, "message": f"HTTP {err.code}: {body[:200]!r}"}}
    except (urllib.error.URLError, OSError) as err:
        return {"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": -32001, "message": f"Blender is not reachable at {url}: {err}"}}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="scenario-blender-stdio")
    parser.add_argument("--url", default="http://127.0.0.1:9876/mcp")
    parser.add_argument("--token", required=True)
    args = parser.parse_args(argv)
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError as err:
            out.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {err}"}}) + "\n")
            out.flush()
            continue
        response = forward(args.url, args.token, message)
        if response is not None and message.get("id") is not None:
            out.write(json.dumps(response) + "\n")
            out.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
