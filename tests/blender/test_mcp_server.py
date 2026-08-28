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
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
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
        self.stop = threading.Event()
        self.pump = threading.Thread(target=self._pump, daemon=True)
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
