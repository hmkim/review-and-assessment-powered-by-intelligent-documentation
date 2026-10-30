#!/usr/bin/env python3
"""M4-d driver: checklist extraction (Q8) and ambiguity detection (Q9) through the deployed
RAPID API.

Flow per input PDF (mirrors the web UI):
  Cognito USER_PASSWORD_AUTH -> ID token
  PUT  /user/preference/language {"language": "ko"}
  POST /documents/checklist/presigned-url {filename, contentType} -> {url, key, documentId}
  PUT  <presigned url> (bytes, Content-Type: application/pdf)
  POST /checklist-sets {name, description, documents:[{documentId, filename, s3Key, fileType}]}
  GET  /checklist-sets/{id}            (poll until completed/failed)
  GET  /checklist-sets/{id}/items?includeAllChildren=true
  POST /checklist-sets/{id}/detect-ambiguity, then poll + items again

Secrets: Cognito user/password are read from ~/.cache/rapid-m4/cognito_user.env (0600) and
never printed. Results: <out>/raw/<slug>.json (one per input) + <out>/run_manifest.json.

Usage:
  uv run --no-project python evals/ko/m4d/run_extraction.py --inputs inputs.json --out <dir>
  inputs.json: [{"slug": "...", "path": "...pdf", "name": "...", "description": "...",
                 "expected_items": 24, "kind": "designed|law|official|form"}]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import boto3
import requests

API = "https://9n8lnz87t2.execute-api.us-west-2.amazonaws.com/api"
REGION = "us-west-2"
ENV_FILE = Path.home() / ".cache" / "rapid-m4" / "cognito_user.env"
POLL_SECS = 15
TIMEOUT_SECS = 40 * 60


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def id_token(env: dict[str, str]) -> str:
    client = boto3.client("cognito-idp", region_name=REGION)
    resp = client.initiate_auth(
        ClientId=env["RAPID_CLIENT"],
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": env["RAPID_USER"], "PASSWORD": env["RAPID_PASS"]},
    )
    return resp["AuthenticationResult"]["IdToken"]


class Rapid:
    def __init__(self, token: str):
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})

    def _check(self, r: requests.Response) -> dict:
        if r.status_code >= 400:
            raise RuntimeError(f"{r.request.method} {r.url} -> {r.status_code}: {r.text[:500]}")
        body = r.json()
        if isinstance(body, dict) and body.get("success") is False:
            raise RuntimeError(f"{r.request.method} {r.url} -> success=false: {json.dumps(body)[:500]}")
        return body

    def get(self, path: str, **params) -> dict:
        return self._check(self.s.get(f"{API}{path}", params=params or None, timeout=60))

    def post(self, path: str, body: dict | None = None) -> dict:
        return self._check(self.s.post(f"{API}{path}", data=json.dumps(body or {}), timeout=60))

    def put(self, path: str, body: dict) -> dict:
        return self._check(self.s.put(f"{API}{path}", data=json.dumps(body), timeout=60))


def upload_pdf(api: Rapid, pdf: Path) -> dict:
    pre = api.post("/documents/checklist/presigned-url", {"filename": pdf.name, "contentType": "application/pdf"})
    data = pre["data"]
    r = requests.put(data["url"], data=pdf.read_bytes(), headers={"Content-Type": "application/pdf"}, timeout=300)
    if r.status_code >= 300:
        raise RuntimeError(f"S3 PUT failed {r.status_code}: {r.text[:300]}")
    return {"documentId": data["documentId"], "filename": pdf.name, "s3Key": data["key"], "fileType": "application/pdf"}


def wait_status(api: Rapid, set_id: str, done: set[str], label: str) -> tuple[dict, float]:
    t0 = time.time()
    last = None
    while True:
        info = api.get(f"/checklist-sets/{set_id}")["data"]
        status = info.get("processingStatus") or info.get("status")
        if status != last:
            print(f"    [{label}] {status} (+{time.time() - t0:.0f}s)", flush=True)
            last = status
        if status in done:
            return info, time.time() - t0
        if time.time() - t0 > TIMEOUT_SECS:
            raise TimeoutError(f"{label}: still {status} after {TIMEOUT_SECS}s")
        time.sleep(POLL_SECS)


def fetch_items(api: Rapid, set_id: str) -> list[dict]:
    body = api.get(f"/checklist-sets/{set_id}/items", includeAllChildren="true")
    data = body["data"]
    if isinstance(data, dict):
        data = data.get("items") or data.get("data") or list(data.values())[0]
    return data


def git_head(repo: Path) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--filter", action="append", default=[], help="slug substring; repeatable")
    ap.add_argument("--skip-ambiguity", action="store_true")
    args = ap.parse_args()

    inputs = json.loads(Path(args.inputs).read_text())
    if args.filter:
        inputs = [i for i in inputs if any(f in i["slug"] for f in args.filter)]
    out = Path(args.out)
    (out / "raw").mkdir(parents=True, exist_ok=True)

    env = load_env(ENV_FILE)
    api = Rapid(id_token(env))
    me = api.get("/auth/me")
    print(f"auth ok: {json.dumps({k: v for k, v in me.get('data', me).items() if k in ('userId', 'isAdmin')})}")
    api.put("/user/preference/language", {"language": "ko"})
    print(f"language preference: {api.get('/user/preference')['data']}")

    repo = Path(__file__).resolve().parents[4]
    manifest_path = out / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        "api": API, "repo_head": git_head(repo), "runs": {}}

    for inp in inputs:
        slug = inp["slug"]
        dest = out / "raw" / f"{slug}.json"
        if dest.exists():
            print(f"== {slug}: exists, skipping")
            continue
        pdf = Path(inp["path"])
        print(f"== {slug}: {pdf.name} ({pdf.stat().st_size // 1024} KB)", flush=True)
        rec: dict = {"slug": slug, "input": inp, "started_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
        try:
            api = Rapid(id_token(env))  # fresh token per document (1h id token)
            doc = upload_pdf(api, pdf)
            set_name = f"{inp.get('name') or slug} {dt.datetime.now(dt.timezone.utc).strftime('%H%M%S')}"
            api.post("/checklist-sets", {
                "name": set_name,
                "description": inp.get("description") or f"M4-d Q8 extraction test: {slug}",
                "documents": [doc],
            })
            # The create endpoint returns an empty body; find the new set by its unique name.
            listing = api.get("/checklist-sets", page=1, limit=20, sortBy="id", sortOrder="desc")["data"]
            match = [s for s in listing.get("checkListSets", []) if s.get("name") == set_name]
            if not match:
                raise RuntimeError(f"created set not found in listing: {set_name}")
            set_id = match[0].get("checkListSetId") or match[0].get("id")
            rec["set_id"] = set_id
            rec["set_name"] = set_name
            info, secs = wait_status(api, set_id, {"completed", "failed"}, "extract")
            rec["extraction"] = {"status": info.get("processingStatus"), "seconds": round(secs, 1),
                                 "set": info}
            items = fetch_items(api, set_id)
            rec["items"] = items
            print(f"    items: {len(items)} (top-level {sum(1 for i in items if not i.get('parentId'))})")

            if not args.skip_ambiguity and info.get("processingStatus") == "completed":
                api.post(f"/checklist-sets/{set_id}/detect-ambiguity")
                info2, secs2 = wait_status(api, set_id, {"completed", "failed"}, "ambiguity")
                items2 = fetch_items(api, set_id)
                flagged = [i for i in items2 if i.get("ambiguityReview")]
                rec["ambiguity"] = {"status": info2.get("processingStatus"), "seconds": round(secs2, 1),
                                    "flagged_count": len(flagged), "items": items2}
                print(f"    ambiguity: {len(flagged)}/{len(items2)} flagged")
        except Exception as e:  # keep going; record the error
            rec["error"] = f"{type(e).__name__}: {e}"
            print(f"    ERROR {rec['error']}", flush=True)
        rec["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        dest.write_text(json.dumps(rec, ensure_ascii=False, indent=2))
        manifest["runs"][slug] = {"set_id": rec.get("set_id"), "error": rec.get("error"),
                                  "items": len(rec.get("items", [])), "finished_utc": rec["finished_utc"]}
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
