#!/usr/bin/env python3
"""Folder-backed queue for talking-head video generation jobs."""
import argparse
import hashlib
import json
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent
QUEUE_ROOT = ROOT / "video_jobs"
STATES = ("queued", "processing", "submitted", "completed", "failed")
ACTIVE_STATES = ("queued", "processing", "submitted")


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def ensure_queue(queue_root=QUEUE_ROOT):
    root = Path(queue_root)
    for state in STATES:
        (root / state).mkdir(parents=True, exist_ok=True)
    return root


def read_job(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_job(path, job):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_text(json.dumps(job, indent=2), encoding="utf-8")
    temp.replace(target)


def list_jobs(queue_root=QUEUE_ROOT, states=STATES):
    root = ensure_queue(queue_root)
    jobs = []
    for state in states:
        for path in (root / state).glob("*.json"):
            job = read_job(path)
            job["queue_file"] = str(path)
            jobs.append(job)
    return sorted(jobs, key=lambda job: job.get("created_at", ""), reverse=True)


def find_job(job_id, queue_root=QUEUE_ROOT, states=STATES):
    root = ensure_queue(queue_root)
    for state in states:
        path = root / state / f"{job_id}.json"
        if path.exists():
            return path, read_job(path)
    raise FileNotFoundError(f"video job not found: {job_id}")


def script_digest(script):
    return hashlib.sha256(script.encode("utf-8")).hexdigest()[:16]


def active_duplicate(job, queue_root=QUEUE_ROOT):
    digest = job.get("script_digest") or script_digest(job.get("script", ""))
    for existing in list_jobs(queue_root, states=ACTIVE_STATES):
        if existing.get("slug") != job.get("slug"):
            continue
        if existing.get("source_asset") != job.get("source_asset"):
            continue
        if existing.get("script_digest") == digest:
            return existing
    return None


def enqueue_job(job, queue_root=QUEUE_ROOT):
    root = ensure_queue(queue_root)
    queued = {
        **job,
        "schema_version": 1,
        "job_id": job.get("job_id") or f"vid_{time.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}",
        "script_digest": job.get("script_digest") or script_digest(job.get("script", "")),
        "status": "queued",
        "created_at": job.get("created_at") or now_iso(),
    }
    duplicate = active_duplicate(queued, root)
    if duplicate:
        return duplicate, False
    write_job(root / "queued" / f"{queued['job_id']}.json", queued)
    return queued, True


def move_job(job_id, state, queue_root=QUEUE_ROOT, updates=None):
    if state not in STATES:
        raise ValueError(f"invalid video job state: {state}")
    root = ensure_queue(queue_root)
    source, job = find_job(job_id, root)
    job.update(updates or {})
    job["status"] = state
    job[f"{state}_at"] = now_iso()
    destination = root / state / source.name
    write_job(destination, job)
    if source.resolve() != destination.resolve():
        source.unlink()
    return job


def update_job(job_id, updates, queue_root=QUEUE_ROOT):
    path, job = find_job(job_id, queue_root)
    job.update(updates)
    job["updated_at"] = now_iso()
    write_job(path, job)
    return job


def claim_job(job_id=None, queue_root=QUEUE_ROOT):
    root = ensure_queue(queue_root)
    if job_id is None:
        queued = list_jobs(root, states=("queued",))
        if not queued:
            raise FileNotFoundError("no queued video jobs")
        job_id = queued[-1]["job_id"]
    return move_job(job_id, "processing", root)


def fail_job(job_id, reason, queue_root=QUEUE_ROOT):
    return move_job(job_id, "failed", queue_root, {"error": str(reason)[:2000]})


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    list_parser = sub.add_parser("list")
    list_parser.add_argument("--status", choices=STATES)
    show_parser = sub.add_parser("show")
    show_parser.add_argument("--job", required=True)
    claim_parser = sub.add_parser("claim")
    claim_parser.add_argument("--job")
    fail_parser = sub.add_parser("fail")
    fail_parser.add_argument("--job", required=True)
    fail_parser.add_argument("--reason", required=True)
    args = parser.parse_args()

    if args.command == "list":
        states = (args.status,) if args.status else STATES
        result = list_jobs(states=states)
    elif args.command == "show":
        result = find_job(args.job)[1]
    elif args.command == "claim":
        result = claim_job(args.job)
    else:
        result = fail_job(args.job, args.reason)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
