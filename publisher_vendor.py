#!/usr/bin/env python3
"""Vendor-neutral posting adapter boundary.

Only dry-run request assembly is implemented. Network submission remains
deliberately unavailable until a vendor is selected and Checkpoints B/C clear.
"""
from __future__ import annotations

from dataclasses import dataclass

import distribution


class VendorAdapterError(RuntimeError):
    pass


@dataclass
class VendorAdapter:
    registry: dict

    @property
    def status(self):
        return distribution.vendor_status(self.registry)

    def dry_run(self, payload, account, scheduled_for=None):
        is_aigc = bool((payload.get("metadata") or {}).get("is_aigc"))
        return {
            "mode": "dry_run",
            "vendor": self.status["name"],
            "submission_attempted": False,
            "account": {
                "account_id": account.get("account_id"),
                "platform": account.get("platform"),
                "handle": account.get("handle"),
                "vendor_account_ref_env": account.get("vendor_account_ref_env"),
            },
            "scheduled_for": scheduled_for,
            "request": {
                "post_type": "carousel",
                "platform": payload.get("platform"),
                "caption": payload.get("caption"),
                "media": payload.get("slides") or [],
                "tracking_code": payload.get("tracking_code"),
                "aigc": {
                    "is_aigc": is_aigc,
                    "send_platform_label": is_aigc,
                    "caption_fallback_present": bool(
                        (payload.get("metadata") or {}).get("illustrative_results_text")
                    ),
                },
            },
        }

    def submit(self, payload, account, scheduled_for=None):
        raise VendorAdapterError(
            "vendor submission is disabled; select and implement the audited vendor, "
            "then clear Checkpoints B and C"
        )

