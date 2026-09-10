"""Authenticated native publishing routes, isolated from existing brand workflows."""
import hmac
import logging
import os
import secrets
from urllib.parse import urlsplit

from flask import Blueprint, jsonify, request, send_file, make_response

import distribution
import publish
from publisher_tiktok import NativeTikTok, TikTokError
from tiktok_media import MediaError, public_https


class CallbackLogFilter(logging.Filter):
    def filter(self, record):
        # Werkzeug access logs must never capture authorization codes or OAuth state.
        if "/api/tiktok/oauth/callback" in record.getMessage():
            record.msg, record.args = "TikTok OAuth callback (query redacted)", ()
        return True


def register(app, posts_path):
    bp = Blueprint("native_tiktok", __name__, url_prefix="/api/tiktok")
    logging.getLogger("werkzeug").addFilter(CallbackLogFilter())

    def service():
        factory = app.config.get("TIKTOK_SERVICE_FACTORY")
        return factory() if factory else NativeTikTok(posts_path=posts_path())

    def authenticate():
        expected = os.environ.get("TIKTOK_OPERATOR_TOKEN", "")
        operator = os.environ.get("TIKTOK_OPERATOR_ID", "")
        origin = os.environ.get("TIKTOK_DASHBOARD_ORIGIN", "")
        provided = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if len(expected) < 32 or not operator or not hmac.compare_digest(expected, provided):
            raise TikTokError("native dashboard operator authentication required")
        if not origin or request.host_url.rstrip("/") != origin.rstrip("/"):
            raise TikTokError("request host does not match TIKTOK_DASHBOARD_ORIGIN")
        parsed = urlsplit(origin)
        if parsed.hostname not in {"127.0.0.1", "localhost"}:
            public_https(origin)
            if not request.is_secure:
                raise TikTokError("remote native dashboard requires HTTPS")
        if request.method != "GET" and request.headers.get("Origin") != origin.rstrip("/"):
            raise TikTokError("same-origin operator action required")
        if request.method != "GET" and not request.is_json:
            raise TikTokError("JSON operator action required")
        return operator

    @bp.before_request
    def protect():
        if request.endpoint != "native_tiktok.oauth_callback":
            authenticate()

    @bp.after_request
    def private_response(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    for error in (TikTokError, MediaError, distribution.DistributionError, publish.PublishError, ValueError):
        bp.register_error_handler(error, lambda exc: (jsonify({"error": str(exc)}), 400))
    for error in (KeyError, TypeError):
        bp.register_error_handler(error, lambda exc: (jsonify({"error": "invalid native TikTok request"}), 400))

    @bp.get("/config")
    def config():
        return jsonify(service().config_status())

    @bp.get("/attempts")
    def attempts():
        return jsonify([{"post_id": a["snapshot"]["post_id"], "stage": a["stage"], **a["record"]}
                        for a in service().journal.attempts()])

    @bp.post("/cancel-schedule")
    def cancel_schedule():
        return jsonify(service().cancel_schedule(request.get_json()["attempt_id"], authenticate()))

    @bp.post("/inspect")
    def inspect():
        data = request.get_json()
        return jsonify(service().inspect(data["post_id"], data["account_id"]))

    @bp.post("/preview")
    def preview():
        data = request.get_json()
        return jsonify(service().preview(data["post_id"], data["account_id"], data["settings"],
                                         data["requested_at"], authenticate()))

    @bp.get("/preview/<ticket>/<int:index>")
    def photo(ticket, index):
        return send_file(service().preview_image(ticket, index, authenticate()), mimetype="image/jpeg")

    @bp.post("/approve")
    def approve():
        data = request.get_json()
        return jsonify(service().approve(data["ticket"], authenticate(),
            content_preview_confirmed=data.get("content_preview_confirmed", False),
            express_consent=data.get("express_consent", False)))

    @bp.post("/refresh")
    def refresh():
        return jsonify(service().refresh_status(request.get_json()["attempt_id"]))

    @bp.post("/oauth/start")
    def oauth_start():
        native = service()
        account, pinned = native.account(request.get_json()["account_id"])
        nonce = secrets.token_urlsafe(32)
        # OAuth always runs on the registered HTTPS deployment, never HTTP localhost.
        callback = native.tokens().callback_url()
        if not request.is_secure or urlsplit(callback).netloc != request.host:
            raise TikTokError("start OAuth on the registered HTTPS callback host")
        url = native.tokens().start(account["account_id"], pinned, nonce)
        response = jsonify({"authorization_url": url})
        response.set_cookie("tiktok_oauth_browser", nonce, max_age=600, secure=True,
                            httponly=True, samesite="Lax", path="/api/tiktok/oauth")
        return response

    @bp.get("/oauth/callback")
    def oauth_callback():
        native = service()
        callback = native.tokens().callback_url()
        if not request.is_secure or urlsplit(callback).netloc != request.host:
            raise TikTokError("OAuth requires the registered HTTPS callback host")
        account_id = native.tokens().finish(request.args.get("state", ""), request.args.get("code", ""),
                                            request.cookies.get("tiktok_oauth_browser", ""))
        # Recheck the registry pin after the state-bound exchange, before any posting use.
        native.account(account_id)
        response = make_response("TikTok authorization stored. Return to the dashboard for post review.")
        response.delete_cookie("tiktok_oauth_browser", path="/api/tiktok/oauth")
        return response

    app.register_blueprint(bp)
