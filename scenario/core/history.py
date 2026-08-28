# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Merge the cloud job list with local job records for the Generations panel. No bpy."""
from dataclasses import dataclass, field


@dataclass
class HistoryEntry:
    job_id: str
    kind: str
    model_id: str
    prompt: str
    status: str
    created_at: str
    cu_cost: float = None
    asset_ids: list = field(default_factory=list)
    local_files: list = field(default_factory=list)

    @property
    def is_success(self):
        return self.status in ("success", "succeeded", "completed")


def entries_from_jobs(jobs, local_records, kinds=None):
    kinds = kinds or {}
    local_by_job = {r.job_id: r for r in local_records if r.job_id}
    entries = []
    for job in jobs:
        if job.get("jobType") != "custom":
            continue
        meta = job.get("metadata") or {}
        inp = meta.get("input") or {}
        job_id = job.get("jobId") or job.get("id")
        local = local_by_job.get(job_id)
        model_id = inp.get("modelId") or (local.model_id if local else "")
        billing = job.get("billing") or {}
        entries.append(HistoryEntry(
            job_id=job_id,
            kind=(local.kind if local else kinds.get(model_id, "image")),
            model_id=model_id,
            prompt=str(inp.get("prompt") or (local.meta.get("prompt") if local else "") or ""),
            status=(job.get("status") or "").lower(),
            created_at=job.get("createdAt") or "",
            cu_cost=float(billing["cuCost"]) if billing.get("cuCost") is not None else None,
            asset_ids=list(meta.get("assetIds") or []),
            local_files=list(local.files) if local else [],
        ))
    entries.sort(key=lambda e: e.created_at, reverse=True)
    return entries
