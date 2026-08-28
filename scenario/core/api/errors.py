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
