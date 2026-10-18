"""Local operator authentication, session-bound previews and request limits."""
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

from fastapi import HTTPException
from starlette.responses import JSONResponse

COOKIE = "baton_operator"
BODY_LIMIT = 65536
SESSION_TTL = 8 * 3600
PREVIEW_TTL = 15 * 60


def credential(data):
    configured = os.environ.get("BATON_OPERATOR_TOKEN")
    if configured:
        if len(configured) < 32:
            raise RuntimeError("BATON_OPERATOR_TOKEN must contain at least 32 characters")
        return configured
    data = Path(data)
    data.mkdir(parents=True, exist_ok=True)
    path = data / ".operator-token"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError:
        if path.is_symlink():
            raise RuntimeError("Operator credential cannot be a symbolic link")
        return path.read_text(encoding="utf-8").strip()
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        value = secrets.token_urlsafe(32)
        stream.write(value)
    return value


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def login(request, supplied, db, data):
    # A rate limit also applies to failed local guesses; credentials never enter logs.
    key = "baton:login:" + digest(request.client.host if request.client else "unknown")
    attempts = db.incr(key)
    if attempts == 1:
        db.expire(key, 60)
    if attempts > 10:
        raise HTTPException(429, "Too many login attempts; retry in one minute")
    if not hmac.compare_digest(supplied.encode(), credential(data).encode()):
        raise HTTPException(401, "Invalid operator token")
    token = secrets.token_urlsafe(32)
    db.set("baton:session:" + digest(token), digest(credential(data)), ex=SESSION_TTL)
    return token


def session(request, db, data, required=True):
    token = request.cookies.get(COOKIE, "")
    saved = db.get("baton:session:" + digest(token)) if token else None
    if isinstance(saved, str):
        saved = saved.encode()
    expected = digest(credential(data)).encode() if saved else b""
    if not saved or not hmac.compare_digest(saved, expected):
        if required:
            raise HTTPException(401, "Sign in as the local operator before saving ownership")
        return None
    return digest(token)


def issue_preview(db, identity, seed, assignments, fingerprint):
    token = secrets.token_urlsafe(32)
    db.set("baton:preview:" + digest(token),
           json.dumps({"operator": identity, "seed": seed, "assign": assignments, "fingerprint": fingerprint}), ex=PREVIEW_TTL)
    return token


def check_preview(db, token, identity, seed, assignments):
    saved = db.get("baton:preview:" + digest(token))
    expected = json.loads(saved) if saved else {}
    if expected.get("operator") != identity or expected.get("seed") != seed or expected.get("assign") != assignments:
        raise HTTPException(409, "Preview this exact plan again before saving it")
    return expected


class RequestGuard:
    """RT-01/03: reject cross-site state changes and bound even chunked bodies."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH", "DELETE"):
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        host = headers.get(b"host", b"").decode("latin1")
        origin = headers.get(b"origin", b"").decode("latin1")
        if (origin and origin != f"{scope['scheme']}://{host}") or headers.get(b"sec-fetch-site") == b"cross-site":
            return await JSONResponse({"detail": "Cross-site state changes are forbidden"}, 403)(scope, receive, send)
        length = headers.get(b"content-length")
        if length and (not length.isdigit() or int(length) > BODY_LIMIT):
            return await JSONResponse({"detail": "Request body exceeds 64 KiB"}, 413)(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > BODY_LIMIT:
                return await JSONResponse({"detail": "Request body exceeds 64 KiB"}, 413)(scope, receive, send)
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)


POLICY = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
          "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
          "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")


class BrowserHeaders:
    """Defense in depth for static pages, API responses, and rejected requests."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def secured(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if not any(k.lower() == b"content-security-policy" for k, _ in headers):
                    headers.append((b"content-security-policy", POLICY.encode()))
                headers.extend([(b"x-content-type-options", b"nosniff"), (b"x-frame-options", b"DENY"),
                                (b"referrer-policy", b"same-origin")])
                if scope.get("path", "").startswith("/api/"):
                    headers.append((b"cache-control", b"no-store"))
                message["headers"] = headers
            await send(message)
        await self.app(scope, receive, secured)
