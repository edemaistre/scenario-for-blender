# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Job records and the persisted registry (survives Blender restarts)."""
import json
import pathlib
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field

from ..api import jobs as jobs_api


@dataclass
class JobRecord:
    local_id: str
    lane: str
    kind: str
    model_id: str
    body: dict
    job_id: str = None
    status: str = "submitting"
    progress: float = 0.0
    cu_cost: float = None
    asset_ids: list = field(default_factory=list)
    asset_types: dict = field(default_factory=dict)
    files: list = field(default_factory=list)
    error: str = None
    created_at: float = 0.0
    updated_at: float = 0.0
    meta: dict = field(default_factory=dict)

    @classmethod
    def new(cls, lane, kind, model_id, body, meta=None, now=None):
        now = now if now is not None else time.time()
        return cls(local_id=uuid.uuid4().hex, lane=lane, kind=kind, model_id=model_id, body=dict(body), created_at=now, updated_at=now, meta=dict(meta or {}))

    @property
    def is_terminal(self):
        return self.status in ("failed",) or jobs_api.is_terminal(self.status)

    @property
    def is_success(self):
        return jobs_api.is_success(self.status)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)


class JobRegistry:
    def __init__(self, path):
        self.path = pathlib.Path(path)
        self._records = {}
        self._lock = threading.RLock()

    def load(self):
        with self._lock:
            self._records = {}
            if self.path.exists():
                try:
                    for item in json.loads(self.path.read_text(encoding="utf-8")):
                        rec = JobRecord.from_dict(item)
                        self._records[rec.local_id] = rec
                except (ValueError, TypeError, KeyError):
                    self._records = {}
        return self

    def save(self):
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = [r.to_dict() for r in sorted(self._records.values(), key=lambda r: r.created_at)]
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload), encoding="utf-8")
            tmp.replace(self.path)

    def add(self, rec):
        with self._lock:
            self._records[rec.local_id] = rec
        return rec

    def by_local_id(self, local_id):
        with self._lock:
            return self._records.get(local_id)

    def active(self):
        with self._lock:
            return [r for r in self._records.values() if not r.is_terminal]

    def recent(self, limit=50):
        with self._lock:
            return sorted(self._records.values(), key=lambda r: r.created_at, reverse=True)[:limit]

    def all(self):
        with self._lock:
            return list(self._records.values())
