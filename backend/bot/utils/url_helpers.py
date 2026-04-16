from __future__ import annotations

import ipaddress
from urllib.parse import urlencode, urlsplit

from django.conf import settings


def build_react_url(path: str = "/", **query_params) -> str:
    base_url = str(getattr(settings, "REACT_APP_URL", "") or "").rstrip("/")
    path = path if path.startswith("/") else f"/{path}"
    query = urlencode({k: str(v) for k, v in query_params.items() if v is not None})
    return f"{base_url}{path}?{query}" if query else f"{base_url}{path}"


def can_use_telegram_button_url(url: str) -> bool:
    parsed = urlsplit((url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        return False

    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False

    # Telegram commonly rejects localhost URLs in inline button links.
    if host == "localhost":
        return bool(getattr(settings, "ALLOW_LOCALHOST_TELEGRAM_BUTTON_URL", False))

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # Normal domain name.
        return True

    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved:
        default_private_ip = bool(getattr(settings, "DEBUG", False))
        return bool(getattr(settings, "ALLOW_PRIVATE_IP_TELEGRAM_BUTTON_URL", default_private_ip))

    return True
