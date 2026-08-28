#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Record REST fixtures used by unit tests. Reads .env.local, never prints secrets.

Usage: python3 tools/record_fixtures.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scenario.core import config  # noqa: E402
from scenario.core.api.client import ScenarioClient  # noqa: E402
from scenario.core.api.errors import ScenarioError  # noqa: E402

MODEL_IDS = [
    "model_patina-material", "model_patina", "model_patina-material-extract",
    "model_openai-gpt-image-2", "model_google-gemini-3-1-flash", "model_bytedance-seedance-2-0",
    "model_meshy-7-img23d", "model_meshy-7-txt23d", "model_tripo-v3-1-image-to-3d",
]


def main():
    env = config.load_dotenv(ROOT / ".env.local")
    creds = config.resolve_credentials(env.get("SCENARIO_API_KEY"), env.get("SCENARIO_API_SECRET"), environ={})
    if not creds.valid:
        sys.exit("no credentials in .env.local")
    client = ScenarioClient(creds.key, creds.secret)
    out = ROOT / "tests" / "fixtures" / "models"
    out.mkdir(parents=True, exist_ok=True)
    for model_id in MODEL_IDS:
        try:
            data = client.get(f"/models/{model_id}")
        except ScenarioError as err:
            print("MISSING", model_id, err.status, err.reason)
            continue
        (out / f"{model_id}.json").write_text(json.dumps(data, indent=1))
        print("saved", model_id)
    page1 = client.get("/models", query={"privacy": "public", "pageSize": 5})
    (ROOT / "tests" / "fixtures" / "models_list_page1.json").write_text(json.dumps(page1, indent=1))
    token = page1.get("nextPaginationToken")
    page2 = client.get("/models", query={"privacy": "public", "pageSize": 5, "paginationToken": token})
    first1 = page1["models"][0]["id"]
    first2 = page2["models"][0]["id"] if page2.get("models") else None
    print("pagination param 'paginationToken' works:", first1 != first2)
    if first1 == first2:
        page2b = client.get("/models", query={"privacy": "public", "pageSize": 5, "pageToken": token})
        print("fallback 'pageToken' works:", page2b["models"][0]["id"] != first1)


if __name__ == "__main__":
    main()
