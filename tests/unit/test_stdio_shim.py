# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import http.server
import json
import pathlib
import subprocess
import sys
import threading

SHIM = pathlib.Path(__file__).resolve().parents[2] / "scenario" / "mcp" / "stdio_shim.py"


class _Stub(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.headers.get("Authorization") != "Bearer secret":
            self.send_response(401)
            self.end_headers()
            return
        payload = json.dumps({"jsonrpc": "2.0", "id": body.get("id"), "result": {"echo": body.get("method")}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def test_shim_round_trips_requests_and_skips_notifications():
    server = http.server.HTTPServer(("127.0.0.1", 0), _Stub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/mcp"
    try:
        proc = subprocess.run([sys.executable, str(SHIM), "--url", url, "--token", "secret"],
                              input='{"jsonrpc":"2.0","id":1,"method":"ping"}\n{"jsonrpc":"2.0","method":"notifications/initialized"}\n{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n',
                              capture_output=True, text=True, timeout=20)
        lines = [json.loads(l) for l in proc.stdout.strip().splitlines()]
        assert [l["id"] for l in lines] == [1, 2]
        assert lines[1]["result"] == {"echo": "tools/list"}
        assert proc.returncode == 0
    finally:
        server.shutdown()
