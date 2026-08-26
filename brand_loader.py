#!/usr/bin/env python3
"""
Brand configuration loader.

Brand-specific identity lives in brands/<brand_id>.yaml. Runtime modules should
load a Brand object instead of hardcoding voice, CTA, palette, accounts, prompts,
or screenshot templates.
"""
from dataclasses import dataclass
from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parent
BRANDS_DIR = ROOT / "brands"
DEFAULT_BRAND = "gloskin"


class BrandConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Brand:
    brand_id: str
    display_name: str
    voice: dict
    pillars: list
    cta: dict
    palette: dict
    fonts: dict
    assets: dict
    accounts: dict
    formats: list
    templates: dict
    prompts: dict
    compliance: dict
    slideshow: dict
    testimonial: dict
    caption: dict
    tracking: dict
    operational_status: str
    claim_lanes: list
    source_path: Path

    @property
    def default_account(self):
        return (
            self.accounts.get("default")
            or self.accounts.get("tiktok")
            or self.accounts.get("instagram")
            or "TODO"
        )

    def prompt_path(self, key):
        value = (self.prompts or {}).get(key)
        return _root_path(value) if value else None

    def format_prompt_path(self, format_name):
        return ROOT / "prompts" / self.brand_id / "formats" / f"{format_name}.md"

    def template_path(self, key):
        item = (self.templates or {}).get(key)
        if isinstance(item, dict):
            value = item.get("path")
        else:
            value = item
        return _root_path(value) if value else None

    def template_items(self):
        rows = []
        for key, raw in (self.templates or {}).items():
            if isinstance(raw, dict):
                item = dict(raw)
            else:
                item = {"path": raw}
            item.setdefault("key", key)
            rows.append(item)
        return rows


def _root_path(value):
    if not value:
        return None
    p = Path(value)
    if p.is_absolute():
        return p
    return ROOT / p


def _require_mapping(data, path):
    if not isinstance(data, dict):
        raise BrandConfigError(f"{path}: expected a YAML mapping")


def _validate_required(data, brand_id, keys):
    for key in keys:
        if key not in data:
            raise BrandConfigError(f"brands/{brand_id}.yaml missing required key: {key}")


def _validate_hex_colors(brand_id, palette):
    for key, value in (palette or {}).items():
        if isinstance(value, str) and value.startswith("#"):
            if not re.fullmatch(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", value):
                raise BrandConfigError(
                    f"brands/{brand_id}.yaml palette.{key} is not a valid hex color: {value}"
                )


def _validate_path_exists(brand_id, section, key, value, *, allow_missing=False):
    if not value:
        return
    p = _root_path(value)
    if not p.exists() and not allow_missing:
        raise BrandConfigError(
            f"brands/{brand_id}.yaml {section}.{key} points to a missing path: {value}"
        )


def _brand_from_dict(data, source_path):
    brand_id = data.get("brand_id") or source_path.stem
    required = [
        "display_name", "voice", "pillars", "cta", "palette", "fonts",
        "assets", "accounts", "formats", "templates", "prompts",
        "compliance", "slideshow", "testimonial", "caption", "tracking",
        "claim_lanes",
    ]
    _validate_required(data, brand_id, required)
    _validate_hex_colors(brand_id, data.get("palette") or {})
    operational_status = data.get("operational_status", "pre_launch")
    if operational_status not in {"pre_launch", "live"}:
        raise BrandConfigError(
            f"brands/{brand_id}.yaml operational_status must be pre_launch or live"
        )
    claim_lanes = [
        str(item).strip() for item in (data.get("claim_lanes") or [])
        if str(item).strip()
    ]
    if not claim_lanes:
        raise BrandConfigError(
            f"brands/{brand_id}.yaml claim_lanes must contain at least one lane"
        )
    if len(claim_lanes) != len(set(claim_lanes)):
        raise BrandConfigError(
            f"brands/{brand_id}.yaml claim_lanes contains duplicate lanes"
        )

    for key, value in (data.get("prompts") or {}).items():
        _validate_path_exists(brand_id, "prompts", key, value)
    for format_name in data.get("formats") or []:
        if format_name != "slideshow":
            _validate_path_exists(
                brand_id,
                "format_prompts",
                format_name,
                f"prompts/{brand_id}/formats/{format_name}.md",
            )
    for key, value in (data.get("assets") or {}).items():
        _validate_path_exists(brand_id, "assets", key, value, allow_missing=(value is None))
    for item in (data.get("templates") or {}).values():
        if isinstance(item, dict):
            required = item.get("required") or item.get("priority") == "required"
            _validate_path_exists(
                brand_id,
                "templates",
                item.get("key") or "template",
                item.get("path"),
                allow_missing=not required,
            )
        else:
            _validate_path_exists(brand_id, "templates", "template", item)

    return Brand(
        brand_id=brand_id,
        display_name=data["display_name"],
        voice=data["voice"] or {},
        pillars=data["pillars"] or [],
        cta=data["cta"] or {},
        palette=data["palette"] or {},
        fonts=data["fonts"] or {},
        assets=data["assets"] or {},
        accounts=data["accounts"] or {},
        formats=data["formats"] or [],
        templates=data["templates"] or {},
        prompts=data["prompts"] or {},
        compliance=data["compliance"] or {},
        slideshow=data["slideshow"] or {},
        testimonial=data["testimonial"] or {},
        caption=data["caption"] or {},
        tracking=data["tracking"] or {},
        operational_status=operational_status,
        claim_lanes=claim_lanes,
        source_path=source_path,
    )


def load_brand(brand_id=DEFAULT_BRAND):
    path = BRANDS_DIR / f"{brand_id}.yaml"
    if not path.exists():
        raise BrandConfigError(f"unknown brand: {brand_id} ({path} not found)")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    _require_mapping(data, path)
    return _brand_from_dict(data, path)


def available_brands():
    if not BRANDS_DIR.exists():
        return []
    return [load_brand(path.stem) for path in sorted(BRANDS_DIR.glob("*.yaml"))]


def brand_summary(brand):
    return {
        "brand_id": brand.brand_id,
        "display_name": brand.display_name,
        "default_account": brand.default_account,
        "cta": brand.cta,
        "formats": brand.formats,
        "templates": list((brand.templates or {}).keys()),
        "has_image_prompts": bool(brand.prompts.get("image_character")),
        "operational_status": brand.operational_status,
        "claim_lanes": brand.claim_lanes,
        "slideshow_copy": {
            "scan_text": brand.testimonial.get("synthetic_scan_text"),
            "result_text": brand.testimonial.get("synthetic_result_text"),
            "progress_text": brand.testimonial.get("synthetic_progress_text"),
            "progress_subtext": brand.testimonial.get("synthetic_progress_subtext"),
        },
    }


def mechanism_claims_for(brand, source_text):
    """Return only mechanism claims for compounds named in the source brief."""
    haystack = str(source_text or "").lower()
    claims = []
    for compound, approved in (brand.compliance.get("mechanism_claims") or {}).items():
        if str(compound).lower() in haystack:
            claims.extend(str(item) for item in (approved or []) if str(item).strip())
    return claims


def main():
    import json

    print(json.dumps([brand_summary(b) for b in available_brands()], indent=2))


if __name__ == "__main__":
    main()
