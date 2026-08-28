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
