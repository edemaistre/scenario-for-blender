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
