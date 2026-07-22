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
    "regulatory_facts",
)
LIST_FIELDS = ("disallowed_claims", "caveats")


class ClaimPackError(RuntimeError):
    pass


def _items(value):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ClaimPackError("claim-pack claim fields must be lists")
    return value


def _iso_date(value, field, path, *, allow_null=False):
    if value is None and allow_null:
        return None
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError) as exc:
        raise ClaimPackError(f"{path}: {field} must be an ISO date") from exc


def _lanes(value, field, path, *, required=False):
    rows = [str(item).strip() for item in _items(value) if str(item).strip()]
    if required and not rows:
        raise ClaimPackError(f"{path}: {field} must contain at least one lane")
    if len(rows) != len(set(rows)):
        raise ClaimPackError(f"{path}: {field} contains duplicate lanes")
    return rows


def claim_text(item):
    if isinstance(item, dict):
        return str(item.get("claim") or item.get("text") or "").strip()
    return str(item or "").strip()


def claim_lanes(item):
    if not isinstance(item, dict):
        return []
    return [str(value).strip() for value in (item.get("lanes") or []) if str(value).strip()]


def _claim_entries(value, field, path, pack_lanes):
    entries = []
    for index, raw in enumerate(_items(value)):
        if isinstance(raw, str):
            text = raw.strip()
            lanes = []
        elif isinstance(raw, dict):
            text = claim_text(raw)
            lanes = _lanes(
                raw.get("lanes"), f"{field}[{index}].lanes", path,
                required=bool(pack_lanes),
            )
        else:
            raise ClaimPackError(f"{path}: {field}[{index}] must be a string or mapping")
        if not text:
            raise ClaimPackError(f"{path}: {field}[{index}].claim is required")
        unknown = sorted(set(lanes) - set(pack_lanes)) if pack_lanes else []
        if unknown:
            raise ClaimPackError(
                f"{path}: {field}[{index}] uses lanes not declared by the pack: "
                f"{', '.join(unknown)}"
            )
        entries.append({"claim": text, "lanes": lanes} if isinstance(raw, dict) else text)
    return entries


def _regulatory_holds(value, path):
    holds = []
    for index, raw in enumerate(_items(value)):
        if not isinstance(raw, dict):
            raise ClaimPackError(f"{path}: regulatory_hold[{index}] must be a mapping")
        claim_ref = str(raw.get("claim_ref") or "").strip()
        status = str(raw.get("status") or "held").strip()
        if not claim_ref:
            raise ClaimPackError(f"{path}: regulatory_hold[{index}].claim_ref is required")
        if "review_after" not in raw:
            raise ClaimPackError(
                f"{path}: regulatory_hold[{index}].review_after is required; "
                "use null for a permanent hold"
            )
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
                allow_null=True,
            ),
            "status": status,
            "note": str(raw.get("note") or "").strip(),
        }
        hold_lanes = _lanes(
            raw.get("lanes"), f"regulatory_hold[{index}].lanes", path)
        if hold_lanes:
            hold["lanes"] = hold_lanes
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
    pack["lanes"] = _lanes(data.get("lanes"), "lanes", path)
    for field in CLAIM_FIELDS:
        pack[field] = _claim_entries(
            data.get(field), field, path, pack["lanes"])
    for field in LIST_FIELDS:
        pack[field] = _items(data.get(field))
    pack["regulatory_hold"] = _regulatory_holds(
        data.get("regulatory_hold"), path)
    for index, hold in enumerate(pack["regulatory_hold"]):
        unknown = sorted(set(hold.get("lanes") or []) - set(pack["lanes"]))
        if unknown:
            raise ClaimPackError(
                f"{path}: regulatory_hold[{index}] uses lanes not declared by "
                f"the pack: {', '.join(unknown)}"
            )
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


def _lane_allowed(item, allowed_lanes):
    lanes = claim_lanes(item)
    return not lanes or not allowed_lanes or bool(set(lanes) & set(allowed_lanes))


def approved_claims(brief):
    claims = [claim_text(item) for item in (brief.get("mechanism_claims") or [])]
    allowed_lanes = brief.get("claim_lanes") or []
    for pack in brief.get("claim_packs") or []:
        for field in CLAIM_FIELDS:
            claims.extend(
                claim_text(item)
                for item in (pack.get(field) or [])
                if _lane_allowed(item, allowed_lanes)
            )
    return [item.strip() for item in claims if item.strip()]


def mechanism_claims(brief):
    allowed_lanes = brief.get("claim_lanes") or []
    claims = [claim_text(item) for item in (brief.get("mechanism_claims") or [])]
    for pack in brief.get("claim_packs") or []:
        claims.extend(
            claim_text(item)
            for item in (pack.get("mechanism_claims") or [])
            if _lane_allowed(item, allowed_lanes)
        )
    return [item for item in claims if item]


def lane_claims(brief):
    """Yield every lane-tagged claim, including claims outside the active brand lane."""
    for pack in brief.get("claim_packs") or []:
        for field in CLAIM_FIELDS:
            for item in pack.get(field) or []:
                lanes = claim_lanes(item)
                if lanes:
                    yield pack, field, claim_text(item), lanes


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
    """A hold clears only after valid human clearance; null review dates never age out."""
    if str(hold.get("status") or "held") != "cleared":
        return True
    cleared_at = hold.get("cleared_at")
    if not cleared_at:
        return True
    try:
        clearance_date = date.fromisoformat(str(cleared_at))
        review_after = hold.get("review_after")
        review_date = date.fromisoformat(str(review_after)) if review_after else None
    except (TypeError, ValueError):
        return True
    current_date = today or date.today()
    if current_date < clearance_date:
        return True
    return bool(review_date and clearance_date <= review_date)
