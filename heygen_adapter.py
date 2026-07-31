#!/usr/bin/env python3
"""HeyGen transport for local talking-head jobs.

The direct API path is optional and billed from HeyGen's API wallet. OAuth/MCP
jobs use the same queue schema but are processed externally by a connected Codex
worker so this module never substitutes one billing route for the other.
"""
import argparse
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import video_queue


ROOT = Path(__file__).resolve().parent
API_BASE = "https://api.heygen.com"
MAX_RETRIES = 3


class HeyGenError(RuntimeError):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def load_dotenv(path=ROOT / ".env"):
    path = Path(path)
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def env_value(name):
    load_dotenv()
    value = (os.environ.get(name) or "").strip()
    if not value or value in {"...", "changeme"} or value.lower().startswith("your_"):
        return None
    return value


def connection_status():
    api_key = env_value("HEYGEN_API_KEY")
    voice_id = env_value("HEYGEN_VOICE_ID")
    return {
        "api_key_configured": bool(api_key),
        "default_voice_configured": bool(voice_id),
        "api_mode": "ready" if api_key else "missing_key",
        "oauth_mode": "external_connection_required",
        "oauth_note": "Connect HeyGen Remote MCP to the Codex task that processes queued OAuth jobs.",
    }


def resolve_workspace_path(path, workspace_root=ROOT, must_exist=True):
    root = Path(workspace_root).resolve()
    candidate = (root / path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"video job path escapes workspace: {path}")
    if must_exist and not candidate.exists():
        raise FileNotFoundError(f"video job file not found: {path}")
    return candidate


def response_message(payload, fallback):
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return error.get("message") or error.get("code") or fallback
        if isinstance(error, str):
            return error
        return payload.get("message") or fallback
    return fallback


class HeyGenClient:
    def __init__(self, api_key=None, api_base=API_BASE, timeout=60, sleep=time.sleep):
        load_dotenv()
        self.api_key = api_key or env_value("HEYGEN_API_KEY")
        if not self.api_key:
            raise HeyGenError("HEYGEN_API_KEY is not configured")
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout
        self.sleep = sleep

    def _request(self, method, path, body=None, headers=None, raw=False, authenticated=True):
        request_headers = {**(headers or {})}
        if authenticated:
            request_headers["x-api-key"] = self.api_key
        url = path if path.startswith("http") else f"{self.api_base}{path}"
        for attempt in range(1, MAX_RETRIES + 1):
            request = urllib.request.Request(
                url, data=body, headers=request_headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    data = response.read()
                    if raw:
                        return data
                    return json.loads(data.decode("utf-8")) if data else {}
            except urllib.error.HTTPError as exc:
                response_body = exc.read().decode("utf-8", errors="replace")
                try:
                    payload = json.loads(response_body)
                except json.JSONDecodeError:
                    payload = {}
                retryable = exc.code == 429 or exc.code >= 500
                if retryable and attempt < MAX_RETRIES:
                    delay = int(exc.headers.get("Retry-After") or min(2 ** attempt, 10))
                    self.sleep(delay)
                    continue
                raise HeyGenError(
                    response_message(payload, f"HeyGen request failed ({exc.code})"),
                    status_code=exc.code,
                ) from exc
            except urllib.error.URLError as exc:
                if attempt < MAX_RETRIES:
                    self.sleep(min(2 ** attempt, 10))
                    continue
                raise HeyGenError(f"HeyGen connection failed: {exc.reason}") from exc

    def json_request(self, method, path, payload=None, idempotency_key=None):
        headers = {"Content-Type": "application/json"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        return self._request(method, path, body=body, headers=headers)

    def current_user(self):
        return self.json_request("GET", "/v3/users/me").get("data", {})

    def upload_asset(self, path, idempotency_key=None):
        source = Path(path)
        boundary = f"----gloskin-{uuid.uuid4().hex}"
        mime = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{source.name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode("utf-8") + source.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        response = self._request("POST", "/v3/assets", body=body, headers=headers)
        data = response.get("data") or {}
        asset_id = data.get("id") or data.get("asset_id")
        if not asset_id:
            raise HeyGenError("HeyGen asset upload returned no asset ID")
        return asset_id

    def create_video(self, payload, idempotency_key):
        response = self.json_request(
            "POST", "/v3/videos", payload, idempotency_key=idempotency_key)
        data = response.get("data") or {}
        video_id = data.get("video_id") or data.get("id")
        if not video_id:
            raise HeyGenError("HeyGen video creation returned no video ID")
        return data

    def get_video(self, video_id):
        return (self.json_request("GET", f"/v3/videos/{video_id}").get("data") or {})

    def download(self, url, destination):
        data = self._request("GET", url, raw=True, headers={}, authenticated=False)
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".tmp")
        temp.write_bytes(data)
        temp.replace(target)
        return target


def video_payload(job):
    common = {
        "title": job.get("title") or f"{job.get('slug', 'character')} talking head",
        "script": job["script"],
        "voice_id": job["voice_id"],
        "resolution": job.get("resolution") or "1080p",
        "aspect_ratio": job.get("aspect_ratio") or "9:16",
    }
    if job.get("motion_prompt"):
        common["motion_prompt"] = job["motion_prompt"]
    if job.get("avatar_id"):
        return {"type": "avatar", "avatar_id": job["avatar_id"], **common}
    if not job.get("heygen_asset_id"):
        raise HeyGenError("job has neither avatar_id nor uploaded HeyGen asset")
    return {
        "type": "image",
        "image": {"type": "asset_id", "asset_id": job["heygen_asset_id"]},
        **common,
    }


def finish_completed_job(job, detail, client, queue_root, workspace_root):
    video_url = detail.get("video_url") or detail.get("url")
    if not video_url:
        raise HeyGenError("completed HeyGen video has no download URL")
    output_path = resolve_workspace_path(
        job["output_path"], workspace_root=workspace_root, must_exist=False)
    client.download(video_url, output_path)
    return video_queue.move_job(job["job_id"], "completed", queue_root, {
        "remote_status": "completed",
        "video_url": video_url,
        "video_page_url": detail.get("video_page_url"),
        "duration": detail.get("duration"),
        "output_path": str(output_path.relative_to(Path(workspace_root).resolve())).replace("\\", "/"),
    })


def refresh_job(job_id, queue_root=video_queue.QUEUE_ROOT, workspace_root=ROOT, client=None):
    _, job = video_queue.find_job(job_id, queue_root, states=("submitted",))
    client = client or HeyGenClient()
    detail = client.get_video(job["heygen_video_id"])
    status = detail.get("status") or "unknown"
    if status == "completed":
        return finish_completed_job(job, detail, client, queue_root, workspace_root)
    if status == "failed":
        reason = detail.get("failure_message") or detail.get("failure_code") or "HeyGen render failed"
        return video_queue.fail_job(job_id, reason, queue_root)
    return video_queue.update_job(job_id, {"remote_status": status}, queue_root)


def process_job(job_id, queue_root=video_queue.QUEUE_ROOT, workspace_root=ROOT,
                client=None, wait=True, max_wait_seconds=300, sleep=time.sleep):
    _, initial = video_queue.find_job(job_id, queue_root)
    if initial.get("auth_mode") != "api_key":
        raise HeyGenError("OAuth/MCP jobs must be processed by a Codex task with HeyGen MCP connected")
    job = video_queue.claim_job(job_id, queue_root)
    try:
        client = client or HeyGenClient()
        portrait = resolve_workspace_path(job["portrait_path"], workspace_root)
        if not job.get("avatar_id") and not job.get("heygen_asset_id"):
            asset_id = client.upload_asset(portrait, idempotency_key=f"{job_id}:asset")
            job = video_queue.update_job(job_id, {"heygen_asset_id": asset_id}, queue_root)
        remote = client.create_video(video_payload(job), idempotency_key=f"{job_id}:video")
        job = video_queue.move_job(job_id, "submitted", queue_root, {
            "heygen_video_id": remote.get("video_id") or remote.get("id"),
            "remote_status": remote.get("status") or "pending",
        })
        if not wait:
            return job
        deadline = time.monotonic() + max_wait_seconds
        delay = 5
        while time.monotonic() < deadline:
            refreshed = refresh_job(job_id, queue_root, workspace_root, client)
            if refreshed["status"] in {"completed", "failed"}:
                return refreshed
            sleep(delay)
            delay = min(delay * 2, 20)
        return video_queue.update_job(job_id, {
            "remote_status": "processing",
            "note": "Polling window ended; refresh this job later. The HeyGen render was not cancelled.",
        }, queue_root)
    except Exception as exc:
        try:
            video_queue.fail_job(job_id, exc, queue_root)
        except FileNotFoundError:
            pass
        raise


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    process_parser = sub.add_parser("process")
    process_parser.add_argument("--job", required=True)
    process_parser.add_argument("--no-wait", action="store_true")
    refresh_parser = sub.add_parser("refresh")
    refresh_parser.add_argument("--job", required=True)
    args = parser.parse_args()
    if args.command == "status":
        result = connection_status()
    elif args.command == "process":
        result = process_job(args.job, wait=not args.no_wait)
    else:
        result = refresh_job(args.job)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
