"""Native GloSkin photo publishing with operator consent and durable at-most-once init.

The journal is authoritative for native attempts; distribution is its UI projection.
No HTTP Content Posting API call is made by config_status(), inspect(), or preview()
except the documented read-only creator query in the latter two.
"""
from dataclasses import asdict, dataclass
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time

import distribution
import manifest
import publish
from tiktok_media import R2MediaHost, MediaError
from tiktok_oauth import OAuth, TokenStore, TikTokError, call, http_transport

ROOT = Path(__file__).resolve().parent
MODES = {"manual", "draft", "private", "direct"}
PRIVACY_LEVELS = {"SELF_ONLY", "PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def utc(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise TikTokError("invalid ISO schedule time") from None
    if result.tzinfo is None:
        raise TikTokError("schedule requires an explicit timezone offset")
    return result.astimezone(timezone.utc)


@dataclass(frozen=True)
class PhotoSettings:
    title: str = ""
    privacy_level: str = ""
    allow_comments: bool = False
    auto_add_music: bool = False
    cover_index: int = 0
    draft_disclosure_acknowledged: bool = False

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) - set(cls.__dataclass_fields__):
            raise TikTokError("unknown photo settings")
        settings = cls(**value)
        if not isinstance(settings.title, str) or not isinstance(settings.privacy_level, str):
            raise TikTokError("title and privacy must be strings")
        for field in ("allow_comments", "auto_add_music", "draft_disclosure_acknowledged"):
            if type(getattr(settings, field)) is not bool:
                raise TikTokError("photo switches must be booleans")
        if type(settings.cover_index) is not int:
            raise TikTokError("cover index must be an integer")
        return settings


def assemble_request(payload, photos, settings, creator, mode):
    """Photo is_aigc is TOP LEVEL (official Photo reference, Aug 24, 2026)."""
    if mode not in {"draft", "private", "direct"}:
        raise TikTokError("manual mode cannot assemble a submission")
    if not 1 <= len(photos) <= 35 or not 0 <= settings.cover_index < len(photos):
        raise TikTokError("invalid photo count or cover index")
    description = payload["caption"]
    for value, limit, label in ((settings.title, 90, "title"), (description, 4000, "description")):
        if len(value.encode("utf-16-le")) // 2 > limit:
            raise TikTokError(f"photo {label} exceeds {limit} UTF-16 units")
    if settings.privacy_level not in PRIVACY_LEVELS or settings.privacy_level not in creator.get("privacy_level_options", []):
        raise TikTokError("select a privacy choice returned by creator_info")
    if settings.allow_comments and creator.get("comment_disabled", True):
        raise TikTokError("creator has disabled comments")
    if mode == "private" and settings.privacy_level != "SELF_ONLY":
        raise TikTokError("private validation requires SELF_ONLY")
    if mode == "draft" and (settings.allow_comments or settings.auto_add_music):
        raise TikTokError("draft interaction/music controls must be set in TikTok")
    info = {"title": settings.title, "description": description}
    if mode != "draft":
        info.update(privacy_level=settings.privacy_level, disable_comment=not settings.allow_comments,
                    auto_add_music=settings.auto_add_music, brand_organic_toggle=True,
                    brand_content_toggle=False)
    return {"media_type": "PHOTO", "post_mode": "MEDIA_UPLOAD" if mode == "draft" else "DIRECT_POST",
            "is_aigc": payload.get("metadata", {}).get("is_aigc") is True,
            "post_info": info,
            "source_info": {"source": "PULL_FROM_URL", "photo_cover_index": settings.cover_index,
                            "photo_images": [photo.url for photo in photos]}}


class Journal:
    def __init__(self, root):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "publishing.sqlite3"
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS previews (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS consents (id TEXT PRIMARY KEY, data TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, data TEXT NOT NULL)")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, table, key, db=None):
        if table not in {"previews", "consents", "attempts"}:
            raise TikTokError("invalid journal table")
        if db is None:
            with self.connect() as conn:
                return self.get(table, key, conn)
        row = db.execute(f"SELECT data FROM {table} WHERE id=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, table, key, value, db):
        if table not in {"previews", "attempts"}:
            raise TikTokError("consent records are append-only")
        db.execute(f"INSERT OR REPLACE INTO {table} VALUES (?, ?)", (key, json.dumps(value)))

    def attempts(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT data FROM attempts")]


class NativeTikTok:
    def __init__(self, posts_path=ROOT / "posts.json", registry_path=distribution.DEFAULT_REGISTRY_PATH,
                 root=ROOT / "workspace_data/tiktok", *, transport=http_transport, oauth=None,
                 host=None, now=lambda: datetime.now(timezone.utc)):
        self.posts_path, self.registry_path = posts_path, registry_path
        self.root, self.transport, self.oauth, self.host, self.now = Path(root), transport, oauth, host, now
        self.journal = Journal(root)

    def registry(self):
        return distribution.load_registry(self.registry_path)

    def account(self, account_id):
        account = distribution.get_account(self.registry(), account_id)
        if account.get("brand") != "gloskin" or account.get("platform") != "tiktok":
            raise TikTokError("native publishing is limited to GloSkin TikTok")
        config = account.get("native_tiktok", {})
        pinned = os.environ.get(config.get("open_id_env", ""), "")
        if distribution._todo(pinned) or not config.get("open_id_env"):
            raise TikTokError("a known target account must have an environment-pinned open_id")
        if config.get("mode", "manual") not in MODES:
            raise TikTokError("unknown native rollout mode")
        return account, pinned

    def tokens(self):
        if self.oauth is None:
            self.oauth = OAuth(TokenStore(self.root), self.transport)
        return self.oauth

    def media(self):
        if self.host is None:
            self.host = R2MediaHost(os.environ.get("TIKTOK_MEDIA_PUBLIC_BASE", ""),
                self.registry().get("native_tiktok", {}).get("verified_media_prefix", ""),
                cache=self.root / "media")
        return self.host

    def config_status(self):
        registry = self.registry()
        config = registry.get("native_tiktok", {})
        rows = []
        for account in registry["accounts"]:
            if account.get("brand") != "gloskin" or account.get("platform") != "tiktok":
                continue
            blockers = distribution.account_blockers(account, require_vendor_ref=False)
            try:
                self.account(account["account_id"])
            except TikTokError as exc:
                blockers.append(str(exc))
            rows.append({"account_id": account["account_id"], "handle": account["handle"],
                         "mode": account.get("native_tiktok", {}).get("mode", "manual"),
                         "blockers": blockers})
        required = ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_TOKEN_ENCRYPTION_KEY",
                    "TIKTOK_REDIRECT_URI", "TIKTOK_MEDIA_PUBLIC_BASE", "TIKTOK_R2_ENDPOINT",
                    "TIKTOK_R2_BUCKET", "TIKTOK_R2_ACCESS_KEY_ID", "TIKTOK_R2_SECRET_ACCESS_KEY",
                    "TIKTOK_OPERATOR_TOKEN", "TIKTOK_OPERATOR_ID", "TIKTOK_DASHBOARD_ORIGIN"]
        checks = {key: bool(os.environ.get(key)) for key in required}
        errors = []
        try:
            self.media()
        except (MediaError, ValueError) as exc:
            errors.append(str(exc))
        if checks["TIKTOK_REDIRECT_URI"]:
            try:
                OAuth(None).callback_url()
            except (TikTokError, MediaError, ValueError) as exc:
                errors.append(str(exc))
        if checks["TIKTOK_TOKEN_ENCRYPTION_KEY"]:
            try:
                from cryptography.fernet import Fernet
                Fernet(os.environ["TIKTOK_TOKEN_ENCRYPTION_KEY"].encode())
            except Exception:
                errors.append("TIKTOK_TOKEN_ENCRYPTION_KEY is invalid")
        if checks["TIKTOK_OPERATOR_TOKEN"] and len(os.environ["TIKTOK_OPERATOR_TOKEN"]) < 32:
            errors.append("TIKTOK_OPERATOR_TOKEN must contain at least 32 characters")
        return {"accounts": rows, "rollout": config, "environment_configured": checks,
                "errors": errors, "configuration_valid": not errors and all(checks.values())
                and any(not row["blockers"] for row in rows), "submission_attempted": False}

    def creator_info(self, account_id):
        account, pinned = self.account(account_id)
        # The official creator endpoint requires video.publish even for our draft preview.
        token = self.tokens().token(account_id, pinned, {"video.publish"})
        data = call(self.transport, "/v2/post/publish/creator_info/query/", {}, token, read_only=True)
        if (not re.fullmatch(r"[A-Za-z0-9_.]+", str(data.get("creator_username", ""))) or
                not data.get("creator_nickname") or not data.get("privacy_level_options") or
                type(data.get("comment_disabled")) is not bool):
            raise TikTokError("creator_info is incomplete or cannot permit posting")
        if data.get("creator_username", "").lstrip("@").casefold() != account["handle"].lstrip("@").casefold():
            raise TikTokError("creator username differs from the configured account")
        return {key: data[key] for key in ("creator_username", "creator_nickname",
                                         "privacy_level_options", "comment_disabled")}

    def gate(self, post, account):
        if post.get("brand") != "gloskin":
            raise TikTokError("VendraRx and other brands are outside native TikTok scope")
        publish.require_automation_gates(post, account, require_vendor_ref=False)
        if not post.get("tracking_code"):
            raise TikTokError("a tracking code is required for idempotency")

    def rollout_gate(self, account):
        config = self.registry().get("native_tiktok", {})
        mode = account.get("native_tiktok", {}).get("mode", "manual")
        if mode == "manual":
            raise TikTokError("account remains in manual mode")
        for flag in ("submission_enabled", "developer_app_approved", "intended_use_approved",
                     "manual_launch_complete", "private_validation_approved"):
            if config.get(flag) is not True:
                raise TikTokError("native rollout checkpoint missing: " + flag)
        if distribution._todo(config.get("intended_use_approval_reference")):
            raise TikTokError("TikTok intended-use approval evidence is required")
        if mode == "direct" and config.get("direct_checkpoint_approved") is not True:
            raise TikTokError("explicit direct-post checkpoint is required")
        enabled = [a for a in self.registry()["accounts"] if a.get("brand") == "gloskin"
                   and a.get("platform") == "tiktok" and a.get("enabled") is True
                   and a.get("native_tiktok", {}).get("mode", "manual") != "manual"]
        if len(enabled) > 2 or sum(a["role"] == "flagship" for a in enabled) != 1:
            raise TikTokError("rollout permits one flagship and at most one owned UGC test account")
        if account["role"] != "flagship" and (config.get("ugc_test_approved") is not True
                or account.get("native_tiktok", {}).get("ownership_disclosed") is not True
                or account.get("test_account") is not True):
            raise TikTokError("owned UGC test account needs explicit approval and public ownership disclosure")

    def records(self):
        records = []
        for post in manifest.all_posts(self.posts_path):
            for value in post.get("distribution", []):
                row = dict(value)
                if post.get("brand") == "gloskin" and row.get("platform") == "tiktok":
                    if not row.get("creative_fingerprint"):
                        payload = publish.platform_payload_for(post, "tiktok")
                        row["creative_fingerprint"] = payload.get("creative_fingerprint")
                    for account in self.registry()["accounts"]:
                        if account.get("brand") == "gloskin" and account.get("platform") == "tiktok" and (
                                row.get("account_id") == account.get("handle")):
                            row["account_id"] = account["account_id"]
                records.append(row)
        # Include journal records even if a process died before projection write-back.
        indexed = {(r.get("platform"), r.get("account_id"), r.get("tracking_code"),
                    r.get("creative_fingerprint")): r for r in records}
        for attempt in self.journal.attempts():
            row = attempt["record"]
            indexed[("tiktok", row["account_id"], row.get("tracking_code"), row["creative_fingerprint"])] = row
        return list(indexed.values())

    def distinct(self, payload, account, exclude=None):
        records = self.records()
        distribution.require_distinct_creative("tiktok", account["account_id"],
                                               payload["creative_fingerprint"], records)
        # Native attempts, including ambiguous/failed ones, also reserve this creative.
        for attempt in self.journal.attempts():
            if attempt["id"] != exclude and attempt["snapshot"]["fingerprint"] == payload["creative_fingerprint"]:
                raise TikTokError("identical creative already has a native attempt")

    def scheduled(self, account, post, requested, exclude=None, apply_jitter=True):
        records = [r for r in self.records() if r.get("native_attempt_id") != exclude]
        requested = utc(requested)
        # Native cap tightens, never raises, the existing account/platform cap.
        cap = min(1, distribution.daily_cap(self.registry(), "tiktok", account))
        registry = self.registry()
        if not apply_jitter:
            registry = {**registry, "scheduling": {**registry["scheduling"], "jitter_minutes": {"min": 0, "max": 0}}}
        normalized = []
        for row in records:
            row = dict(row)
            value = row.get("attempted_at") or row.get("scheduled_for") or row.get("posted_at")
            if value:
                # Legacy manifest timestamps are local; conservatively also count their date.
                try:
                    row["scheduled_for"] = utc(value).isoformat()
                except TikTokError:
                    pass
            normalized.append(row)
        return distribution.scheduled_time(registry, {**account, "daily_cap": cap}, post,
                                           requested, normalized)

    def inspect(self, post_id, account_id):
        post = publish.load_post(post_id, self.posts_path)
        account, _ = self.account(account_id)
        self.gate(post, account)
        payload = publish.platform_payload_for(post, "tiktok", account_id)
        publish.validate_carousel(payload["slides"], "tiktok")
        photos = self.media().plan(payload["slides"])
        return {"account": {"account_id": account_id, "handle": account["handle"]},
                "creator": self.creator_info(account_id), "caption": payload["caption"],
                "is_aigc": payload["metadata"].get("is_aigc") is True,
                "brand_organic": True, "mode": account.get("native_tiktok", {}).get("mode", "manual"),
                "photo_count": len(photos)}

    def prepare(self, post_id, account_id, settings, scheduled_for, exclude=None, creator_fixture=None):
        post = publish.load_post(post_id, self.posts_path)
        account, pinned = self.account(account_id)
        self.gate(post, account)
        payload = publish.platform_payload_for(post, "tiktok", account_id)
        publish.validate_carousel(payload["slides"], "tiktok")
        if len(payload["slides"]) != len(post.get("slides", [])):
            raise TikTokError("rendered slide count must match the release manifest")
        self.distinct(payload, account, exclude)
        photos = self.media().plan(payload["slides"])
        creator = self.creator_info(account_id) if creator_fixture is None else creator_fixture
        mode = account.get("native_tiktok", {}).get("mode", "manual")
        request = assemble_request(payload, photos, settings, creator, mode)
        snapshot = {"post_id": post_id, "account_id": account_id, "open_id_digest": digest(pinned),
                    "handle": account["handle"], "owning_entity": account["owning_entity"],
                    "creator": creator, "tracking_code": post["tracking_code"], "mode": mode,
                    "photos": [photo.public() for photo in photos], "request": request,
                    "fingerprint": payload["creative_fingerprint"], "settings": asdict(settings),
                    "scheduled_for": scheduled_for}
        return snapshot, photos

    def preview(self, post_id, account_id, settings, requested_at, operator):
        settings = PhotoSettings.parse(settings)
        account, _ = self.account(account_id)
        post = publish.load_post(post_id, self.posts_path)
        planned = self.scheduled(account, post, requested_at)
        if utc(planned) < self.now():
            raise TikTokError("schedule must be in the future")
        key = digest({"platform": "tiktok", "tracking_code": post.get("tracking_code")})
        previous = self.journal.get("attempts", key)
        exclude = key if previous and previous["stage"] == "cancelled" else None
        snapshot, photos = self.prepare(post_id, account_id, settings, planned, exclude)
        ticket = secrets.token_urlsafe(32)
        data = {"snapshot": snapshot, "digest": digest(snapshot), "operator": operator,
                "expires_at": time.time() + 900, "paths": [p.path for p in photos], "viewed": []}
        with self.journal.connect() as db:
            self.journal.put("previews", ticket, data, db)
        return {"ticket": ticket, "digest": data["digest"], "snapshot": snapshot,
                "content_preview_confirmed": False, "express_consent": False,
                "submission_attempted": False}

    def preview_image(self, ticket, index, operator):
        with self.journal.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            data = self.journal.get("previews", ticket, db)
            if not data or data["operator"] != operator or data["expires_at"] < time.time():
                raise TikTokError("preview expired or belongs to another operator")
            if not 0 <= index < len(data["paths"]):
                raise TikTokError("invalid preview image index")
            path = Path(data["paths"][index])
            if hashlib.sha256(path.read_bytes()).hexdigest() != data["snapshot"]["photos"][index]["sha256"]:
                raise TikTokError("preview media changed")
            data["viewed"] = sorted(set(data["viewed"] + [index]))
            self.journal.put("previews", ticket, data, db)
            db.commit()
        return path

    def approve(self, ticket, operator, *, content_preview_confirmed=False, express_consent=False):
        """Only the authenticated dashboard action calls this; CLI cannot mint consent."""
        if content_preview_confirmed is not True or express_consent is not True or not operator:
            raise TikTokError("explicit preview confirmation and express consent are required")
        with self.journal.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            preview = self.journal.get("previews", ticket, db)
            if not preview or preview["operator"] != operator or preview["expires_at"] < time.time():
                raise TikTokError("preview expired or belongs to another operator")
            old = preview["snapshot"]
            if len(preview["viewed"]) != len(old["photos"]):
                raise TikTokError("every carousel image must load in the dashboard before approval")
            account, _ = self.account(old["account_id"])
            self.rollout_gate(account)
            if old["mode"] == "draft" and not old["settings"]["draft_disclosure_acknowledged"]:
                raise TikTokError("acknowledge the required own-brand disclosure in TikTok's draft editor")
            key = digest({"platform": "tiktok", "tracking_code": old["tracking_code"]})
            previous = self.journal.get("attempts", key, db)
            if previous and previous["stage"] != "cancelled":
                raise TikTokError("this tracking code already has an attempt; use status refresh")
            current, _ = self.prepare(old["post_id"], old["account_id"], PhotoSettings.parse(old["settings"]), old["scheduled_for"], key)
            if digest(current) != preview["digest"]:
                raise TikTokError("post/account/settings changed; render a new preview")
            post = publish.load_post(old["post_id"], self.posts_path)
            self.scheduled(account, post, old["scheduled_for"], apply_jitter=False)
            if utc(old["scheduled_for"]) < self.now():
                raise TikTokError("scheduled time has passed; render a new preview")
            consent = {"id": ticket, "digest": preview["digest"], "snapshot": current,
                       "operator": operator, "approved_at": self.now().isoformat(),
                       "source": "dashboard_explicit_approve_and_schedule",
                       "content_preview_confirmed": True, "express_consent": True,
                       "declaration_version": "tiktok-music-own-brand-v1"}
            db.execute("INSERT INTO consents VALUES (?, ?)", (ticket, json.dumps(consent)))
            record = {"platform": "tiktok", "account_id": old["account_id"], "mode": "native_tiktok",
                      "status": "queued", "scheduled_for": old["scheduled_for"],
                      "tracking_code": old["tracking_code"], "creative_fingerprint": old["fingerprint"],
                      "native_attempt_id": key, "consent_id": ticket, "consent_digest": preview["digest"]}
            attempt = {"id": key, "snapshot": current, "record": record, "stage": "scheduled"}
            self.journal.put("attempts", key, attempt, db)
            db.commit()
        self.project(attempt)
        return record

    def cancel_schedule(self, key, operator):
        with self.journal.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            attempt = self.journal.get("attempts", key, db)
            if not attempt or attempt["stage"] != "scheduled":
                raise TikTokError("only an unclaimed local schedule can be cancelled")
            attempt["stage"] = "cancelled"
            attempt["record"].update(status="failed", error="schedule cancelled before submission",
                                      cancelled_by=operator, cancelled_at=self.now().isoformat())
            self.journal.put("attempts", key, attempt, db)
            db.commit()
        self.project(attempt)
        return attempt["record"]

    def project(self, attempt):
        post_id = attempt["snapshot"]["post_id"]
        row = dict(attempt["record"])
        post = publish.load_post(post_id, self.posts_path)
        existing = next((r for r in post.get("distribution", []) if r.get("platform") == "tiktok"
                         and r.get("account_id") == row["account_id"]), None)
        if existing and existing.get("status") == "metrics_matched":
            return
        if existing is None:
            manifest.set_distribution(post_id, "tiktok", row["account_id"], "packaged", self.posts_path)
            existing = {"status": "packaged"}
        if existing["status"] == "packaged" and row["status"] in {"queued", "failed"}:
            manifest.set_distribution(post_id, "tiktok", row["account_id"], "queued", self.posts_path)
        status, account_id, platform = row.pop("status"), row.pop("account_id"), row.pop("platform")
        manifest.set_distribution(post_id, platform, account_id, status, self.posts_path, **row)

    def save_attempt(self, attempt):
        with self.journal.connect() as db:
            self.journal.put("attempts", attempt["id"], attempt, db)
        self.project(attempt)

    def submit(self, key, *, allow_network_writes=False):
        if allow_network_writes is not True or os.environ.get("TIKTOK_ALLOW_SUBMISSIONS") != "true":
            raise TikTokError("submission requires --allow-network-writes and TIKTOK_ALLOW_SUBMISSIONS=true")
        # Claim before any remote side effects. A crashed claimed/init attempt is NEVER replayed.
        with self.journal.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            attempt = self.journal.get("attempts", key, db)
            if not attempt:
                raise TikTokError("approved attempt not found")
            if attempt["stage"] != "scheduled":
                return attempt["record"]
            old = attempt["snapshot"]
            if utc(old["scheduled_for"]) > self.now():
                raise TikTokError("approved schedule is not due")
            if self.now() - utc(old["scheduled_for"]) > timedelta(hours=1):
                raise TikTokError("schedule expired; operator review required")
            account, pinned = self.account(old["account_id"])
            self.rollout_gate(account)
            consent = self.journal.get("consents", attempt["record"]["consent_id"], db)
            if not consent or consent["digest"] != digest(old) or not all(consent.get(k) is True for k in
                    ("content_preview_confirmed", "express_consent")):
                raise TikTokError("auditable consent missing or invalid")
            current, photos = self.prepare(old["post_id"], old["account_id"],
                                          PhotoSettings.parse(old["settings"]), old["scheduled_for"], key)
            if digest(current) != consent["digest"]:
                raise TikTokError("consent invalidated by post/account/settings edits")
            # Check actual execution day too; late jobs cannot evade cadence at midnight.
            self.scheduled(account, publish.load_post(old["post_id"], self.posts_path),
                           self.now().isoformat(), exclude=key, apply_jitter=False)
            scopes = {"video.publish", "video.upload"} if old["mode"] == "draft" else {"video.publish"}
            token = self.tokens().token(old["account_id"], pinned, scopes)
            attempt["stage"] = "claimed"
            attempt["record"]["attempted_at"] = self.now().isoformat()
            self.journal.put("attempts", key, attempt, db)
            db.commit()
        try:
            self.media().upload(photos)
        except Exception:
            attempt["stage"] = "media_failed"
            attempt["record"].update(status="failed", error="media hosting failed; no TikTok init attempted")
            self.save_attempt(attempt)
            raise TikTokError(attempt["record"]["error"]) from None
        attempt["stage"] = "init_started"
        self.save_attempt(attempt)
        try:
            result = call(self.transport, "/v2/post/publish/content/init/", old["request"], token)
            publish_id = result.get("publish_id")
            if not isinstance(publish_id, str) or not re.fullmatch(r"[\w.~:-]{1,64}", publish_id):
                raise TikTokError("invalid publish id")
        except Exception:
            attempt["stage"] = "uncertain"
            attempt["record"].update(error="init outcome unknown/rejected; automatic retry prohibited",
                                     reconciliation_required=True)
            self.save_attempt(attempt)
            raise TikTokError(attempt["record"]["error"]) from None
        attempt["stage"] = "polling"
        attempt["record"].update(publish_id=publish_id, error=None)
        self.save_attempt(attempt)
        return attempt["record"]

    def refresh_status(self, key):
        with self.journal.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            attempt = self.journal.get("attempts", key, db)
            if not attempt or not attempt["record"].get("publish_id"):
                raise TikTokError("no publish_id; reconcile uncertain init manually without resubmitting")
            old = attempt["snapshot"]
            _, pinned = self.account(old["account_id"])
            scopes = {"video.upload"} if old["mode"] == "draft" else {"video.publish"}
            token = self.tokens().token(old["account_id"], pinned, scopes)
            data = call(self.transport, "/v2/post/publish/status/fetch/",
                        {"publish_id": attempt["record"]["publish_id"]}, token, read_only=True)
            status = data.get("status")
            if status not in {"PROCESSING_UPLOAD", "PROCESSING_DOWNLOAD", "SEND_TO_USER_INBOX", "PUBLISH_COMPLETE", "FAILED"}:
                raise TikTokError("unknown TikTok publishing status")
            record = attempt["record"]
            record.update(tiktok_status=status, last_polled_at=self.now().isoformat())
            if status == "FAILED":
                attempt["stage"] = "terminal"
                reason = data.get("fail_reason")
                allowed = {"picture_size_check_failed", "file_format_check_failed", "photo_pull_failed",
                           "auth_removed", "publish_cancelled", "spam_risk_too_many_posts"}
                record.update(status="failed", error=reason if reason in allowed else "TikTok publishing failed (details redacted)")
            elif status == "PUBLISH_COMPLETE":
                attempt["stage"] = "terminal"
                ids = [str(x) for x in data.get("publicaly_available_post_id", []) if re.fullmatch(r"\d{1,30}", str(x))]
                urls = [f"https://www.tiktok.com/@{old['creator']['creator_username']}/photo/{x}" for x in ids]
                record.update(status="posted", posted_at=record.get("posted_at") or self.now().isoformat(),
                              platform_post_ids=ids, platform_post_id=ids[0] if ids else None,
                              urls=urls, url=urls[0] if urls else None,
                              url_source="constructed_from_public_id" if ids else None, error=None)
            self.journal.put("attempts", key, attempt, db)
            db.commit()
        self.project(attempt)
        return record

    def worker(self, *, limit=10, allow_network_writes=False):
        if not 1 <= limit <= 100:
            raise TikTokError("worker limit must be 1-100")
        results = []
        config = self.registry().get("native_tiktok", {})
        for attempt in sorted(self.journal.attempts(), key=lambda a: a["snapshot"]["scheduled_for"]):
            if len(results) >= limit:
                break
            key = attempt["id"]
            try:
                if attempt["stage"] == "polling":
                    last = attempt["record"].get("last_polled_at")
                    if last and self.now() - utc(last) < timedelta(seconds=60):
                        continue
                    results.append(self.refresh_status(key))
                elif attempt["stage"] == "scheduled" and utc(attempt["snapshot"]["scheduled_for"]) <= self.now():
                    if config.get("scheduler_enabled") is not True:
                        continue
                    results.append(self.submit(key, allow_network_writes=allow_network_writes))
            except (TikTokError, MediaError, publish.PublishError, distribution.DistributionError) as exc:
                results.append({"native_attempt_id": key, "error": str(exc)})
        return results
