from __future__ import annotations

from functools import wraps
from typing import Callable, Optional

from django.conf import settings
from django.core.cache import cache
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import HttpResponse, JsonResponse

_TOKEN_SALT = "bingo.web.token"
_TOKEN_MAX_AGE_SECONDS = int(getattr(settings, "WEB_ACCESS_TOKEN_MAX_AGE", 3600 * 12))


def create_user_access_token(telegram_id: int) -> str:
    signer = TimestampSigner(salt=_TOKEN_SALT)
    return signer.sign(str(int(telegram_id)))


def verify_user_access_token(token: str, max_age: Optional[int] = None) -> Optional[int]:
    signer = TimestampSigner(salt=_TOKEN_SALT)
    effective_max_age = _TOKEN_MAX_AGE_SECONDS if max_age is None else max_age
    try:
        value = signer.unsign(token, max_age=effective_max_age)
    except (BadSignature, SignatureExpired, ValueError):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_request_access_token(request) -> str:
    auth_header = (request.headers.get("Authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    header_token = (request.headers.get("X-User-Token") or "").strip()
    if header_token:
        return header_token

    query_token = (request.GET.get("token") or "").strip()
    return query_token


def get_authenticated_telegram_id(request) -> Optional[int]:
    token = get_request_access_token(request)
    if not token:
        return None
    return verify_user_access_token(token)


def request_origin_allowed(request) -> bool:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return True

    allowed = {origin.rstrip("/") for origin in getattr(settings, "WEB_ALLOWED_ORIGINS", []) if origin}
    if not allowed:
        return True

    origin = (request.headers.get("Origin") or "").rstrip("/")
    if origin and origin in allowed:
        return True

    referer = (request.headers.get("Referer") or "")
    if referer:
        for allowed_origin in allowed:
            if referer.startswith(allowed_origin + "/") or referer == allowed_origin:
                return True

    return False


def _client_ip(request) -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def rate_limit(key_prefix: str, max_requests: int, window_seconds: int):
    def decorator(view_func: Callable):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            auth_tid = get_authenticated_telegram_id(request)
            identity = auth_tid if auth_tid is not None else _client_ip(request)
            cache_key = f"rl:{key_prefix}:{identity}"

            if cache.add(cache_key, 1, timeout=window_seconds):
                count = 1
            else:
                try:
                    count = cache.incr(cache_key)
                except ValueError:
                    cache.set(cache_key, 1, timeout=window_seconds)
                    count = 1

            if count > max_requests:
                return JsonResponse({"error": "Too many requests. Please slow down."}, status=429)

            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


def require_valid_web_token(view_func: Callable):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if request.method == "OPTIONS":
            return HttpResponse(status=204)

        auth_tid = get_authenticated_telegram_id(request)
        if auth_tid is None:
            return JsonResponse({"error": "Authentication required."}, status=401)

        if not request_origin_allowed(request):
            return JsonResponse({"error": "Request origin not allowed."}, status=403)

        request.auth_telegram_id = auth_tid
        return view_func(request, *args, **kwargs)

    return wrapped


def require_path_telegram_auth(view_func: Callable):
    @wraps(view_func)
    def wrapped(request, telegram_id, *args, **kwargs):
        if request.method == "OPTIONS":
            return HttpResponse(status=204)

        auth_tid = get_authenticated_telegram_id(request)
        if auth_tid is None:
            return JsonResponse({"error": "Authentication required."}, status=401)

        if int(auth_tid) != int(telegram_id):
            return JsonResponse({"error": "Forbidden."}, status=403)

        if not request_origin_allowed(request):
            return JsonResponse({"error": "Request origin not allowed."}, status=403)

        request.auth_telegram_id = auth_tid
        return view_func(request, telegram_id, *args, **kwargs)

    return wrapped
