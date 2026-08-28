# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generation submit and dry-run cost estimate."""
from dataclasses import dataclass, field


@dataclass
class Estimate:
    cu_cost: float
    discount: float = 0.0
    details: dict = field(default_factory=dict)


def submit(client, model_id, body):
    data = client.post(f"/generate/custom/{model_id}", json_body=body)
    job = data.get("job") or {}
    if not job.get("jobId") and job.get("id"):
        job["jobId"] = job["id"]
    return job


def estimate(client, model_id, body):
    # dryRun MUST be a query parameter; in the body it is ignored and runs a paid job.
    data = client.post(f"/generate/custom/{model_id}", query={"dryRun": "true"}, json_body=body)
    return Estimate(
        cu_cost=float(data.get("creativeUnitsCost") or 0.0),
        discount=float(data.get("creativeUnitsDiscount") or 0.0),
        details=dict(data.get("costDetails") or {}),
    )
