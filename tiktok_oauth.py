"""Owned-account OAuth boundary. No tokens or provider error bodies leave here."""
import hashlib
from contextlib import contextmanager
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError

from tiktok_media import public_https

API = "https://open.tiktokapis.com"


class TikTokError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def http_transport(path, body, token=None, *, form=False, timeout=30):
    """Injected by tests. Fixed API origin, TLS verification, no redirect/token leaks."""
    if path not in {"/v2/oauth/token/", "/v2/post/publish/creator_info/query/",
                    "/v2/post/publish/content/init/", "/v2/post/publish/status/fetch/"}:
        raise TikTokError("unsupported TikTok endpoint")
    headers = {"Content-Type": "application/x-www-form-urlencoded" if form else "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = (urlencode(body) if form else json.dumps(body)).encode()
    req = Request(API + path, data=data, headers=headers, method="POST")
    try:
        with build_opener(NoRedirect).open(req, timeout=timeout) as response:
            return response.status, json.loads(response.read(1024 * 1024))
    except HTTPError as exc:
        # Never return raw error bodies, URLs, headers, or exception reprs.
        return exc.code, {}
    except Exception:
        raise TikTokError("TikTok transport failed; details redacted") from None


def call(transport, path, body, token=None, *, form=False, read_only=False, sleep=time.sleep):
    attempts = 3 if read_only else 1  # NEVER retry content init or rotating OAuth exchanges.
    for index in range(attempts):
        try:
            status, response = transport(path, body, token, form=form, timeout=30)
        except Exception:
            if index + 1 < attempts:
                sleep(2 ** index)
                continue
            raise TikTokError("TikTok transport failed; response redacted") from None
        if (status == 429 or status >= 500) and index + 1 < attempts:
            sleep(2 ** index)
            continue
        error = response.get("error")
        ok = error in (None, "") if form else isinstance(error, dict) and error.get("code") == "ok"
        if status != 200 or not ok:
            raise TikTokError(f"TikTok request rejected (HTTP {int(status)}); response redacted")
        return response if form else response.get("data", {})


class TokenStore:
    def __init__(self, root=None):
        from cryptography.fernet import Fernet
        try:
            self.cipher = Fernet(os.environ["TIKTOK_TOKEN_ENCRYPTION_KEY"].encode())
        except Exception:
            raise TikTokError("valid TIKTOK_TOKEN_ENCRYPTION_KEY required") from None
        self.root = Path(root or Path(__file__).parent / "workspace_data/tiktok")
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "tokens.sqlite3"
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS secrets (id TEXT PRIMARY KEY, value BLOB NOT NULL)")
        if os.name != "nt":
            self.root.chmod(0o700)
            self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def put(self, key, value):
        encrypted = self.cipher.encrypt(json.dumps(value).encode())
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO secrets VALUES (?, ?)", (key, encrypted))

    def get(self, key, consume=False):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM secrets WHERE id=?", (key,)).fetchone()
            if consume:
                db.execute("DELETE FROM secrets WHERE id=?", (key,))
        if row is None:
            raise TikTokError("token or OAuth state not found")
        try:
            return json.loads(self.cipher.decrypt(row[0]))
        except Exception:
            raise TikTokError("encrypted token store cannot be read") from None


class OAuth:
    def __init__(self, store, transport=http_transport):
        self.store, self.transport = store, transport

    def callback_url(self):
        value = os.environ.get("TIKTOK_REDIRECT_URI", "")
        public_https(value)
        if len(value) >= 512 or not value.endswith("/api/tiktok/oauth/callback"):
            raise TikTokError("register the exact HTTPS /api/tiktok/oauth/callback URI")
        return value

    def start(self, account_id, pinned_id, browser_nonce):
        callback = self.callback_url()
        if not os.environ.get("TIKTOK_CLIENT_KEY") or not os.environ.get("TIKTOK_CLIENT_SECRET"):
            raise TikTokError("TikTok client credentials required")
        state = secrets.token_urlsafe(32)
        self.store.put("state:" + hashlib.sha256(state.encode()).hexdigest(), {
            "account_id": account_id, "open_id": pinned_id,
            "browser": hashlib.sha256(browser_nonce.encode()).hexdigest(),
            "expires": time.time() + 600, "callback": callback})
        return "https://www.tiktok.com/v2/auth/authorize/?" + urlencode({
            "client_key": os.environ["TIKTOK_CLIENT_KEY"], "response_type": "code",
            "scope": "video.publish,video.upload", "redirect_uri": callback,
            "state": state, "disable_auto_auth": 1})

    def finish(self, state, code, browser_nonce):
        pending = self.store.get("state:" + hashlib.sha256(state.encode()).hexdigest(), consume=True)
        if (pending["expires"] < time.time() or not browser_nonce or
                not hmac.compare_digest(pending["browser"], hashlib.sha256(browser_nonce.encode()).hexdigest())
                or pending["callback"] != self.callback_url() or not code):
            raise TikTokError("invalid or expired OAuth state")
        data = self.exchange({"grant_type": "authorization_code", "code": code,
                              "redirect_uri": pending["callback"]})
        self.save(pending["account_id"], pending["open_id"], data)
        return pending["account_id"]

    def exchange(self, body):
        try:
            body = {**body, "client_key": os.environ["TIKTOK_CLIENT_KEY"],
                    "client_secret": os.environ["TIKTOK_CLIENT_SECRET"]}
        except KeyError:
            raise TikTokError("TikTok client credentials required") from None
        return call(self.transport, "/v2/oauth/token/", body, form=True)

    def save(self, account_id, pinned_id, data):
        if not pinned_id or not hmac.compare_digest(str(data.get("open_id", "")), pinned_id):
            raise TikTokError("OAuth account does not match pinned open_id")
        if not all(data.get(key) for key in ("access_token", "refresh_token", "expires_in", "refresh_expires_in")):
            raise TikTokError("incomplete OAuth token response")
        data = {**data, "expires_at": time.time() + int(data["expires_in"]),
                "refresh_expires_at": time.time() + int(data["refresh_expires_in"])}
        self.store.put("account:" + account_id, data)

    def token(self, account_id, pinned_id, scopes):
        # Transaction serializes token rotation across dashboard and worker processes.
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM secrets WHERE id=?", ("account:" + account_id,)).fetchone()
            try:
                data = json.loads(self.store.cipher.decrypt(row[0]))
            except Exception:
                raise TikTokError("account token unavailable") from None
            if data.get("open_id") != pinned_id:
                raise TikTokError("token identity is not the pinned account")
            if data["expires_at"] <= time.time() + 60:
                if data["refresh_expires_at"] <= time.time():
                    raise TikTokError("OAuth reconnect required")
                data = self.exchange({"grant_type": "refresh_token", "refresh_token": data["refresh_token"]})
                if data.get("open_id") != pinned_id or not all(data.get(k) for k in
                        ("access_token", "refresh_token", "expires_in", "refresh_expires_in")):
                    raise TikTokError("invalid refreshed identity or credentials")
                data.update(expires_at=time.time() + int(data["expires_in"]),
                            refresh_expires_at=time.time() + int(data["refresh_expires_in"]))
                db.execute("UPDATE secrets SET value=? WHERE id=?", (
                    self.store.cipher.encrypt(json.dumps(data).encode()), "account:" + account_id))
            if not set(scopes).issubset(set(data.get("scope", "").split(","))):
                raise TikTokError("required OAuth scopes were not granted")
            return data["access_token"]
