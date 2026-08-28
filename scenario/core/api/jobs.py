# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Job polling helpers."""

SUCCESS = {"success", "succeeded", "completed"}
FAILED = {"failure", "failed", "canceled", "cancelled", "error"}


def is_success(status):
    return (status or "").lower() in SUCCESS


def is_terminal(status):
    s = (status or "").lower()
    return s in SUCCESS or s in FAILED


def get_job(client, job_id):
    data = client.get(f"/jobs/{job_id}")
    return data.get("job") or data


def list_jobs(client, page_size=50, token=None, status=None):
    query = {"pageSize": page_size}
    if token:
        query["paginationToken"] = token
    if status:
        query["status"] = status
    data = client.get("/jobs", query=query)
    return list(data.get("jobs") or []), data.get("nextPaginationToken")


def asset_ids(job):
    return list(((job or {}).get("metadata") or {}).get("assetIds") or [])


def upload_entity_id(job):
    output = ((job or {}).get("metadata") or {}).get("output") or {}
    return output.get("entityId")


def progress(job):
    try:
        return float((job or {}).get("progress") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def cu_cost(job):
    billing = (job or {}).get("billing") or {}
    try:
        return float(billing.get("cuCost")) if billing.get("cuCost") is not None else None
    except (TypeError, ValueError):
        return None


def error_text(job):
    """Failure reason: top-level keys first, then metadata.error and metadata.hint (where the API puts them)."""
    job = job or {}
    for key in ("error", "errorMessage", "failureReason", "reason"):
        value = job.get(key)
        if value:
            return str(value)
    meta = job.get("metadata") or {}
    parts = [str(meta[k]) for k in ("error", "hint") if meta.get(k)]
    return " ".join(parts) if parts else None
