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


def is_prompt_asset(value):
    """The jobs list replaces the prompt text by the id of a text asset once the job is archived."""
    return isinstance(value, str) and value.startswith("asset_")


def prompt_asset_ids(jobs):
    ids = []
    for job in jobs:
        value = ((job.get("metadata") or {}).get("input") or {}).get("prompt")
        if is_prompt_asset(value) and value not in ids:
            ids.append(value)
    return ids


def resolve_prompts(jobs, texts):
    """Replace prompt asset ids by their text where `texts` (asset_id -> text) knows them."""
    for job in jobs:
        inp = (job.get("metadata") or {}).get("input") or {}
        value = inp.get("prompt")
        if is_prompt_asset(value) and value in texts:
            inp["prompt"] = texts[value]
    return jobs


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
        prompt = inp.get("prompt")
        if is_prompt_asset(prompt):
            prompt = local.meta.get("prompt") if local else ""
        entries.append(HistoryEntry(
            job_id=job_id,
            kind=(local.kind if local else kinds.get(model_id, "image")),
            model_id=model_id,
            prompt=str(prompt or (local.meta.get("prompt") if local else "") or ""),
            status=(job.get("status") or "").lower(),
            created_at=job.get("createdAt") or "",
            cu_cost=float(billing["cuCost"]) if billing.get("cuCost") is not None else None,
            asset_ids=list(meta.get("assetIds") or []),
            local_files=list(local.files) if local else [],
        ))
    entries.sort(key=lambda e: e.created_at, reverse=True)
    return entries
