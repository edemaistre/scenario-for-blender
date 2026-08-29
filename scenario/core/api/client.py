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
                 user_agent="ScenarioBlender/0.8.3", sleep=time.sleep, max_retries=3):
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
