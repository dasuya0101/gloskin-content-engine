#!/usr/bin/env python3
"""Load human-authored, per-compound claim packs for generation and linting."""
import re
from datetime import date
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent
CLAIMS_DIR = ROOT / "claims"
CLAIM_FIELDS = (
    "evidence_claims",
    "mechanism_claims",
    "regulatory_claims",
    "disallowed_claims",
    "caveats",
)


class ClaimPackError(RuntimeError):
    pass


def _items(value):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ClaimPackError("claim-pack claim fields must be lists")
    return value


def _iso_date(value, field, path):
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError) as exc:
        raise ClaimPackError(f"{path}: {field} must be an ISO date") from exc


def _regulatory_holds(value, path):
    holds = []
    for index, raw in enumerate(_items(value)):
        if not isinstance(raw, dict):
            raise ClaimPackError(f"{path}: regulatory_hold[{index}] must be a mapping")
        claim_ref = str(raw.get("claim_ref") or "").strip()
        status = str(raw.get("status") or "held").strip()
        if not claim_ref:
            raise ClaimPackError(f"{path}: regulatory_hold[{index}].claim_ref is required")
        if status not in {"held", "cleared"}:
            raise ClaimPackError(
                f"{path}: regulatory_hold[{index}].status must be held or cleared"
            )
        hold = {
            "claim_ref": claim_ref,
            "review_after": _iso_date(
                raw.get("review_after"),
                f"regulatory_hold[{index}].review_after",
                path,
            ),
            "status": status,
            "note": str(raw.get("note") or "").strip(),
        }
        if raw.get("cleared_at") is not None:
            hold["cleared_at"] = _iso_date(
                raw.get("cleared_at"),
                f"regulatory_hold[{index}].cleared_at",
                path,
            )
        holds.append(hold)
    return holds


def load_claim_pack(path):
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or not str(data.get("compound") or "").strip():
        raise ClaimPackError(f"{path}: compound is required")
    pack = {
        "compound": str(data["compound"]).strip(),
        "aliases": [
            str(item).strip()
            for item in _items(data.get("aliases"))
            if str(item).strip()
        ],
        "source": str(path.relative_to(ROOT)).replace("\\", "/"),
    }
    for field in CLAIM_FIELDS:
        pack[field] = _items(data.get(field))
    pack["regulatory_hold"] = _regulatory_holds(
        data.get("regulatory_hold"), path)
    return pack


def available_claim_packs(claims_dir=CLAIMS_DIR):
    directory = Path(claims_dir)
    if not directory.exists():
        return []
    return [load_claim_pack(path) for path in sorted(directory.glob("*.yaml"))]


def relevant_claim_packs(source_text, claims_dir=CLAIMS_DIR):
    haystack = str(source_text or "")
    matches = []
    for pack in available_claim_packs(claims_dir):
        names = [pack["compound"], *(pack.get("aliases") or [])]
        if any(re.search(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", haystack, re.I)
               for name in names):
            matches.append(pack)
    return matches


def approved_claims(brief):
    claims = [str(item) for item in (brief.get("mechanism_claims") or [])]
    for pack in brief.get("claim_packs") or []:
        for field in ("evidence_claims", "mechanism_claims", "regulatory_claims"):
            claims.extend(str(item) for item in (pack.get(field) or []))
    return [item.strip() for item in claims if item.strip()]


def disallowed_claims(brief):
    rows = []
    for pack in brief.get("claim_packs") or []:
        rows.extend(pack.get("disallowed_claims") or [])
    return rows


def caveats(brief):
    rows = []
    for pack in brief.get("claim_packs") or []:
        rows.extend(str(item).strip() for item in (pack.get("caveats") or []))
    return [item for item in rows if item]


def regulatory_holds(brief):
    rows = []
    for pack in brief.get("claim_packs") or []:
        for hold in pack.get("regulatory_hold") or []:
            rows.append((pack, hold))
    return rows


def regulatory_hold_is_active(hold, today=None):
    """A hold clears only after a valid human clearance past its review date."""
    if str(hold.get("status") or "held") != "cleared":
        return True
    cleared_at = hold.get("cleared_at")
    if not cleared_at:
        return True
    try:
        review_date = date.fromisoformat(str(hold.get("review_after")))
        clearance_date = date.fromisoformat(str(cleared_at))
    except ValueError:
        return True
    current_date = today or date.today()
    return clearance_date <= review_date or current_date < clearance_date
