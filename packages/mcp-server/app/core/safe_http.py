"""SSRF-safe HTTP helpers with validation on every redirect hop."""

from urllib.parse import urljoin

import httpx

from app.core.security import validate_url

_REDIRECT_CODES = {301, 302, 303, 307, 308}


async def safe_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    max_redirects: int = 10,
) -> httpx.Response:
    """GET a URL while validating the initial target and every redirect."""
    current = validate_url(url)
    for _ in range(max_redirects + 1):
        response = await client.get(current, headers=headers, follow_redirects=False)
        if response.status_code not in _REDIRECT_CODES:
            return response
        location = response.headers.get("location")
        if not location:
            return response
        current = validate_url(urljoin(current, location))
    raise httpx.TooManyRedirects(f"More than {max_redirects} redirects", request=response.request)
