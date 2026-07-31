#!/usr/bin/env python3
"""Folder-backed queue used by Codex built-in image generation tasks."""
import argparse
import json
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent
QUEUE_ROOT = ROOT / "image_jobs"
STATES = ("queued", "processing", "completed", "failed")


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
    raise FileNotFoundError(f"image job not found: {job_id}")


def active_duplicate(job, queue_root=QUEUE_ROOT):
    target_names = sorted(target["name"] for target in job.get("targets", []))
    for existing in list_jobs(queue_root, states=("queued", "processing")):
        if existing.get("slug") != job.get("slug"):
            continue
        existing_names = sorted(target["name"] for target in existing.get("targets", []))
        if existing_names == target_names:
            return existing
    return None


def enqueue_job(job, queue_root=QUEUE_ROOT):
    root = ensure_queue(queue_root)
    duplicate = active_duplicate(job, root)
    if duplicate:
        return duplicate, False
    queued = {
        **job,
        "schema_version": 1,
        "job_id": job.get("job_id") or f"img_{time.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}",
        "status": "queued",
        "created_at": job.get("created_at") or now_iso(),
    }
    write_job(root / "queued" / f"{queued['job_id']}.json", queued)
    return queued, True


def move_job(job_id, state, queue_root=QUEUE_ROOT, updates=None):
    if state not in STATES:
        raise ValueError(f"invalid image job state: {state}")
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


def claim_job(job_id=None, queue_root=QUEUE_ROOT):
    root = ensure_queue(queue_root)
    if job_id is None:
        queued = list_jobs(root, states=("queued",))
        if not queued:
            raise FileNotFoundError("no queued image jobs")
        job_id = queued[-1]["job_id"]
    return move_job(job_id, "processing", root)


def resolve_workspace_path(path, workspace_root=ROOT):
    root = Path(workspace_root).resolve()
    candidate = (root / path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"image job path escapes workspace: {path}")
    return candidate


def complete_job(job_id, queue_root=QUEUE_ROOT, workspace_root=ROOT):
    _, job = find_job(job_id, queue_root, states=("processing", "queued"))
    missing = [
        target["target_path"] for target in job.get("targets", [])
        if not resolve_workspace_path(target["target_path"], workspace_root).exists()
    ]
    if missing:
        raise FileNotFoundError("missing generated targets: " + ", ".join(missing))
    return move_job(job_id, "completed", queue_root)


def fail_job(job_id, reason, queue_root=QUEUE_ROOT):
    return move_job(job_id, "failed", queue_root, {"error": reason})


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    list_parser = sub.add_parser("list")
    list_parser.add_argument("--status", choices=STATES)
    show_parser = sub.add_parser("show")
    show_parser.add_argument("--job", required=True)
    claim_parser = sub.add_parser("claim")
    claim_parser.add_argument("--job")
    complete_parser = sub.add_parser("complete")
    complete_parser.add_argument("--job", required=True)
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
    elif args.command == "complete":
        result = complete_job(args.job)
    else:
        result = fail_job(args.job, args.reason)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
