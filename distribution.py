#!/usr/bin/env python3
"""Account registry and deterministic scheduling rules for distribution."""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import os
from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parent
DEFAULT_REGISTRY_PATH = ROOT / "distribution_accounts.yaml"
PLATFORMS = {"tiktok", "instagram"}
ROLES = {"flagship", "volume"}
VERIFICATION_STATUSES = {"unverified", "pending", "verified", "rejected"}
ACCOUNT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")
TODO_VALUES = {"", "todo", "tbd", "unknown"}


class DistributionError(RuntimeError):
    pass


def _todo(value):
    return str(value or "").strip().casefold() in TODO_VALUES


def load_registry(path=DEFAULT_REGISTRY_PATH):
    target = Path(path)
    if not target.exists():
        raise DistributionError(f"distribution account registry not found: {target}")
    raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise DistributionError("distribution account registry must be a YAML mapping")
    registry = {
        "schema_version": raw.get("schema_version", 1),
        "vendor": dict(raw.get("vendor") or {}),
        "scheduling": dict(raw.get("scheduling") or {}),
        "accounts": list(raw.get("accounts") or []),
    }
    seen = set()
    for account in registry["accounts"]:
        validate_account(account)
        account_id = account["account_id"]
        if account_id in seen:
            raise DistributionError(f"duplicate distribution account_id: {account_id}")
        seen.add(account_id)
    return registry


def validate_account(account):
    if not isinstance(account, dict):
        raise DistributionError("each distribution account must be a mapping")
    account_id = str(account.get("account_id") or "")
    if not ACCOUNT_ID_PATTERN.fullmatch(account_id):
        raise DistributionError(f"invalid distribution account_id: {account_id or '(empty)'}")
    if account.get("platform") not in PLATFORMS:
        raise DistributionError(f"{account_id}: unsupported platform {account.get('platform')}")
    if account.get("role") not in ROLES:
        raise DistributionError(f"{account_id}: invalid role {account.get('role')}")
    if account.get("verification_status") not in VERIFICATION_STATUSES:
        raise DistributionError(
            f"{account_id}: invalid verification_status {account.get('verification_status')}")
    if not str(account.get("brand") or "").strip():
        raise DistributionError(f"{account_id}: brand is required")
    return account


def get_account(registry, account_id):
    account = next(
        (row for row in registry.get("accounts", []) if row.get("account_id") == account_id),
        None,
    )
    if not account:
        raise DistributionError(f"distribution account not found: {account_id}")
    return account


def account_blockers(account, *, require_vendor_ref=True):
    blockers = []
    if account.get("enabled") is not True:
        blockers.append("account is disabled")
    if _todo(account.get("handle")):
        blockers.append("handle is not configured")
    if _todo(account.get("owning_entity")):
        blockers.append("owning entity is not configured")
    if account.get("platform") == "tiktok" and account.get("verification_status") != "verified":
        blockers.append("TikTok account is not verified")
    if account.get("platform") == "instagram" and account.get("verification_status") != "verified":
        blockers.append("Instagram professional account is not verified")
    ref_env = str(account.get("vendor_account_ref_env") or "").strip()
    if require_vendor_ref and (not ref_env or not os.environ.get(ref_env)):
        blockers.append(f"vendor account reference is missing ({ref_env or 'env not set'})")
    return blockers


def public_registry(registry):
    rows = []
    for raw in registry.get("accounts", []):
        account = dict(raw)
        account["blockers"] = account_blockers(account)
        account["ready"] = not account["blockers"]
        ref_env = account.get("vendor_account_ref_env")
        account["vendor_account_ref_configured"] = bool(ref_env and os.environ.get(ref_env))
        rows.append(account)
    return {
        "schema_version": registry.get("schema_version", 1),
        "vendor": vendor_status(registry),
        "scheduling": registry.get("scheduling") or {},
        "accounts": rows,
    }


def vendor_status(registry):
    vendor = dict(registry.get("vendor") or {})
    api_url_env = str(vendor.get("api_url_env") or "POSTING_VENDOR_API_URL")
    api_key_env = str(vendor.get("api_key_env") or "POSTING_VENDOR_API_KEY")
    selected = not _todo(vendor.get("name")) and vendor.get("name") != "unselected"
    return {
        "name": vendor.get("name") or "unselected",
        "selected": selected,
        "configured": bool(selected and os.environ.get(api_url_env) and os.environ.get(api_key_env)),
        "submission_enabled": vendor.get("submission_enabled") is True,
        "scheduler_enabled": vendor.get("scheduler_enabled") is True,
        "checkpoint_b_approved": vendor.get("checkpoint_b_approved") is True,
        "checkpoint_c_approved": vendor.get("checkpoint_c_approved") is True,
        "requires": [api_url_env, api_key_env],
    }


def daily_cap(registry, platform, account=None):
    if account and account.get("daily_cap") is not None:
        return int(account["daily_cap"])
    caps = (registry.get("scheduling") or {}).get("daily_caps") or {}
    return int(caps.get(platform, 0))


def scheduled_time(registry, account, post, requested_at, existing_records=()):
    requested = (
        requested_at if isinstance(requested_at, datetime)
        else datetime.fromisoformat(str(requested_at))
    )
    jitter = (registry.get("scheduling") or {}).get("jitter_minutes") or {}
    low = int(jitter.get("min", 0))
    high = int(jitter.get("max", low))
    if high < low:
        raise DistributionError("scheduling.jitter_minutes.max must be >= min")
    seed = "|".join([
        str(account.get("account_id")),
        str(post.get("tracking_code") or post.get("post_id")),
        requested.date().isoformat(),
    ])
    span = high - low + 1
    offset = low + (int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) % span)
    scheduled = requested + timedelta(minutes=offset)

    active = [
        row for row in existing_records
        if row.get("account_id") == account.get("account_id")
        and row.get("platform") == account.get("platform")
        and row.get("status") in {"queued", "posted", "metrics_matched"}
        and str(row.get("scheduled_for") or row.get("posted_at") or "")[:10]
        == scheduled.date().isoformat()
    ]
    cap = daily_cap(registry, account.get("platform"), account)
    if cap <= 0:
        raise DistributionError(f"no daily cap configured for {account.get('platform')}")
    if len(active) >= cap:
        raise DistributionError(
            f"daily cap reached for {account.get('account_id')}: {len(active)}/{cap}")
    return scheduled.replace(microsecond=0).isoformat()


def creative_fingerprint(payload):
    digest = hashlib.sha256()
    slides = payload.get("slides") or []
    if slides:
        for value in slides:
            path = Path(value)
            if path.exists() and path.is_file():
                digest.update(path.read_bytes())
            else:
                digest.update(str(value).encode("utf-8"))
    else:
        digest.update(str(payload.get("video") or "").encode("utf-8"))
    return digest.hexdigest()


def require_distinct_creative(platform, account_id, fingerprint, records):
    for record in records:
        if (
            record.get("platform") == platform
            and record.get("creative_fingerprint") == fingerprint
            and record.get("account_id") != account_id
            and record.get("status") in {"packaged", "queued", "posted", "metrics_matched"}
        ):
            raise DistributionError(
                "identical creative is already assigned to "
                f"{record.get('account_id')} on {platform}"
            )
