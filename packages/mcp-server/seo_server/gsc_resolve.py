"""Auto-resolve GSC site_url to the correct property format (sc-domain: preferred)."""

import logging
from urllib.parse import urlparse

from seo_server import service_context as svc

logger = logging.getLogger(__name__)

# Module-level cache to avoid repeated list_sites calls within a session
_resolved_cache: dict[str, str] = {}


def _extract_domain(site_url: str) -> str:
    """Extract bare domain from any input format."""
    # Already sc-domain: format
    if site_url.startswith("sc-domain:"):
        return site_url.split(":", 1)[1].strip().lower()

    # URL format
    parsed = urlparse(site_url if "://" in site_url else f"https://{site_url}")
    domain = (parsed.hostname or parsed.path).lower()
    # Strip www.
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


async def resolve_site_url(site_url: str) -> str:
    """Resolve a user-provided site_url to the best matching GSC property.

    Priority: sc-domain: > https:// > http://
    Falls back to the original value if no match is found.
    """
    if not site_url:
        return site_url

    # Check cache first
    cache_key = site_url.lower().strip()
    if cache_key in _resolved_cache:
        resolved = _resolved_cache[cache_key]
        if resolved != site_url:
            logger.info("GSC resolve (cached): '%s' → '%s'", site_url, resolved)
        return resolved

    # If already sc-domain: format, trust it
    if site_url.startswith("sc-domain:"):
        _resolved_cache[cache_key] = site_url
        return site_url

    target_domain = _extract_domain(site_url)

    try:
        sites = await svc.ctx.gsc.list_sites()
    except Exception as e:
        logger.warning("GSC resolve: could not list sites: %s", e)
        _resolved_cache[cache_key] = site_url
        return site_url

    # Score candidates: sc-domain: wins, then exact https match, then partial
    best_match = None
    best_score = -1

    for entry in sites:
        prop_url = entry.get("site_url", "")

        if prop_url.startswith("sc-domain:"):
            prop_domain = prop_url.split(":", 1)[1].strip().lower()
            if prop_domain == target_domain:
                best_match = prop_url
                best_score = 100  # sc-domain exact match — highest priority
            elif target_domain.endswith(f".{prop_domain}"):
                # Subdomain matches parent domain property
                if best_score < 50:
                    best_match = prop_url
                    best_score = 50
        else:
            prop_domain = _extract_domain(prop_url)
            if prop_domain == target_domain:
                if best_score < 80:
                    best_match = prop_url
                    best_score = 80  # Exact URL property match

    resolved = best_match or site_url
    _resolved_cache[cache_key] = resolved

    if resolved != site_url:
        logger.info("GSC resolve: '%s' → '%s'", site_url, resolved)

    return resolved
