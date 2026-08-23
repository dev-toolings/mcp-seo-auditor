"""Security utilities for input validation and SSRF protection."""

import ipaddress
import socket
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import urlparse

from app.core.config import settings
from app.core.exceptions import InvalidURLError, ParameterBoundsError

_MAX_URL_LENGTH = 2048
_ALLOWED_SCHEMES = {"http", "https"}
_TRUST_LOCAL_URLS: ContextVar[bool] = ContextVar("trust_local_urls", default=False)


@contextmanager
def trusted_local_urls():
    """Allow local URLs only inside an explicitly trusted internal run context."""
    token = _TRUST_LOCAL_URLS.set(True)
    try:
        yield
    finally:
        _TRUST_LOCAL_URLS.reset(token)


def _is_private_ip(host: str) -> bool:
    """Check if a hostname resolves to a private/reserved IP address."""
    try:
        addr = ipaddress.ip_address(host)
        return (
            addr.is_private
            or addr.is_loopback
            or addr.is_reserved
            or addr.is_link_local
            or addr.is_multicast
        )
    except ValueError:
        pass

    try:
        addrinfos = socket.getaddrinfo(host, None)
        for family, _type, _proto, _canonname, sockaddr in addrinfos:
            ip_str = sockaddr[0]
            addr = ipaddress.ip_address(ip_str)
            if (
                addr.is_private
                or addr.is_loopback
                or addr.is_reserved
                or addr.is_link_local
                or addr.is_multicast
            ):
                return True
    except (socket.gaierror, OSError):
        pass

    return False


_BLOCKED_HOSTS = {"localhost", "0.0.0.0", "[::1]"}


def validate_url(url: str) -> str:
    """Validate and sanitize a URL for safe server-side requests.

    Ensures only http/https schemes, blocks private/reserved IPs to prevent SSRF.
    Returns the cleaned URL or raises InvalidURLError.
    """
    if not url or not isinstance(url, str):
        raise InvalidURLError("URL is empty or not a string")

    url = url.strip()

    if len(url) > _MAX_URL_LENGTH:
        raise InvalidURLError(f"URL exceeds maximum length of {_MAX_URL_LENGTH} characters")

    try:
        parsed = urlparse(url)
    except Exception:
        raise InvalidURLError(f"Malformed URL: {url}")

    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise InvalidURLError(
            f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are allowed"
        )

    if not parsed.hostname:
        raise InvalidURLError(f"URL has no hostname: {url}")

    hostname = parsed.hostname.lower()

    if not settings.ALLOW_LOCAL_URLS and not _TRUST_LOCAL_URLS.get():
        if hostname in _BLOCKED_HOSTS:
            raise InvalidURLError(f"Blocked hostname: {hostname}")

        if _is_private_ip(hostname):
            raise InvalidURLError(f"URL resolves to a private/reserved IP address: {hostname}")

    return url


_BOUNDS_DEFAULTS: dict[str, int] = {
    "max_urls": 1000,
    "max_pages": 500,
    "limit": 100,
    "days": 365,
    "days_back": 365,
    "max_actions": 50,
    "max_results": 50,
}


def validate_bounds(value: int, param_name: str, max_val: int | None = None) -> int:
    """Validate that an integer parameter is within acceptable bounds.

    Uses default max values per parameter name if max_val is not provided.
    Returns the validated value or raises ParameterBoundsError.
    """
    if max_val is None:
        max_val = _BOUNDS_DEFAULTS.get(param_name)
        if max_val is None:
            raise ParameterBoundsError(
                param_name, value, f"No default bounds defined for '{param_name}'"
            )

    if not isinstance(value, int) or isinstance(value, bool):
        raise ParameterBoundsError(
            param_name, value, f"'{param_name}' must be an integer, got {type(value).__name__}"
        )

    if value <= 0 or value > max_val:
        raise ParameterBoundsError(
            param_name, value, f"'{param_name}' must be between 1 and {max_val}, got {value}"
        )

    return value
