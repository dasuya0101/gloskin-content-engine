#!/usr/bin/env python3
"""Load human-authored, per-compound claim packs for generation and linting."""
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent
CLAIMS_DIR = ROOT / "claims"
CLAIM_FIELDS = (
    "evidence_claims",
    "mechanism_claims",
    "regulatory_claims",
    "disallowed_claims",
)


class ClaimPackError(RuntimeError):
    pass


def _items(value):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ClaimPackError("claim-pack claim fields must be lists")
    return value


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
