"""Immutable, ordered carousel hosting. Planning never uploads anything."""
from dataclasses import asdict, dataclass
import hashlib
import ipaddress
import io
import os
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from PIL import Image


class MediaError(RuntimeError):
    pass


def probe_public(url, mime):
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    try:
        with build_opener(NoRedirect).open(Request(url, method="HEAD"), timeout=15) as response:
            if response.status != 200 or response.headers.get_content_type() != mime:
                raise MediaError("unexpected public media response")
    except Exception:
        raise MediaError("public media URL is unavailable, redirects, or has the wrong MIME type") from None


def public_https(value):
    try:
        parsed = urlsplit(str(value))
        port = parsed.port
    except ValueError:
        raise MediaError("invalid public HTTPS URL") from None
    host = parsed.hostname or ""
    if (parsed.scheme != "https" or not host or parsed.username or parsed.password
            or parsed.query or parsed.fragment or port not in (None, 443)
            or host == "localhost" or host.endswith((".localhost", ".local"))
            or "." not in host or "%" in parsed.path or "\\" in value
            or any(part in {".", ".."} for part in parsed.path.split("/"))):
        raise MediaError("a public HTTPS URL without credentials/query/fragment is required")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return value
    raise MediaError("use a verified public DNS domain, not an IP address")


def validate_prefix(base, verified):
    public_https(base)
    public_https(verified)
    if not base.endswith("/") or not verified.endswith("/"):
        raise MediaError("public base and verified prefix must end with /")
    if not base.startswith(verified):
        raise MediaError("public media base is outside the verified prefix")
    return base


@dataclass(frozen=True)
class HostedPhoto:
    index: int
    path: str
    sha256: str
    mime: str
    key: str
    url: str

    def public(self):
        return {key: value for key, value in asdict(self).items() if key != "path"}


class R2MediaHost:
    def __init__(self, base, verified, client=None, bucket=None, cache=None, probe=probe_public):
        self.base = validate_prefix(base, verified)
        self.verified = verified
        self.client = client
        self.bucket = bucket or os.environ.get("TIKTOK_R2_BUCKET")
        self.cache = Path(cache or Path(__file__).parent / "workspace_data/tiktok/media")
        self.probe = probe

    def plan(self, paths):
        if not 1 <= len(paths) <= 35 or len(set(paths)) != len(paths):
            raise MediaError("a carousel requires 1-35 distinct ordered files")
        result = []
        for index, value in enumerate(paths):
            path = Path(value)
            if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
                raise MediaError("photo is missing or exceeds the 20 MB limit")
            data = path.read_bytes()
            try:
                with Image.open(path) as img:
                    fmt, size = img.format, img.size
                    img.verify()
            except Exception:
                raise MediaError("invalid photo content") from None
            # TikTok supports JPEG/WebP. Convert packaged PNG before operator preview.
            formats = {"PNG": ("image/png", ".png"), "JPEG": ("image/jpeg", ".jpg")}
            if fmt not in formats or size != (1080, 1350):
                raise MediaError("photo must be a 1080x1350 PNG or JPEG")
            mime, suffix = formats[fmt]
            if path.suffix.lower() not in ({".jpg", ".jpeg"} if fmt == "JPEG" else {".png"}):
                raise MediaError("photo extension and MIME type disagree")
            if fmt == "PNG":
                with Image.open(path) as img:
                    buffer = io.BytesIO()
                    img.convert("RGB").save(buffer, format="JPEG", quality=95, subsampling=0)
                data = buffer.getvalue()
                self.cache.mkdir(parents=True, exist_ok=True)
                path = self.cache / (hashlib.sha256(data).hexdigest() + ".jpg")
                if not path.exists():
                    path.write_bytes(data)
                mime, suffix = "image/jpeg", ".jpg"
            digest = hashlib.sha256(data).hexdigest()
            suffix_key = f"{digest}/{index:02d}{suffix}"
            key = urlsplit(self.base).path.lstrip("/") + suffix_key
            result.append(HostedPhoto(index, str(path), digest, mime, key, self.base + suffix_key))
        return result

    def upload(self, photos):
        if self.client is None:
            try:
                import boto3
                from botocore.config import Config
                endpoint = os.environ["TIKTOK_R2_ENDPOINT"]
                parsed = urlsplit(public_https(endpoint))
                if not parsed.hostname.endswith(".r2.cloudflarestorage.com"):
                    raise MediaError("R2 endpoint must be a Cloudflare R2 API domain")
                self.client = boto3.client(
                    "s3", endpoint_url=endpoint, region_name="auto",
                    aws_access_key_id=os.environ["TIKTOK_R2_ACCESS_KEY_ID"],
                    aws_secret_access_key=os.environ["TIKTOK_R2_SECRET_ACCESS_KEY"],
                    config=Config(connect_timeout=10, read_timeout=30,
                                  retries={"max_attempts": 2, "mode": "standard"}))
            except Exception:
                raise MediaError("R2 configuration is incomplete or invalid") from None
        if not self.bucket:
            raise MediaError("TIKTOK_R2_BUCKET is required")
        for photo in photos:
            data = Path(photo.path).read_bytes()
            if hashlib.sha256(data).hexdigest() != photo.sha256:
                raise MediaError("media changed after preview; review it again")
            try:
                self.client.put_object(Bucket=self.bucket, Key=photo.key, Body=data,
                                       ContentType=photo.mime,
                                       CacheControl="public, max-age=2592000, immutable")
            except Exception:
                raise MediaError("R2 upload failed; credentials and response redacted") from None
            self.probe(photo.url, photo.mime)


class FakeMediaHost(R2MediaHost):
    """Test-only host; never used by production configuration."""
    def __init__(self, base="https://media.example.test/photos/", cache=None):
        super().__init__(base, base, cache=cache)
        self.uploaded = []

    def upload(self, photos):
        self.uploaded.extend(photo.public() for photo in photos)
