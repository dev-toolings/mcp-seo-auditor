"""Token budget management for LLM prompts."""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Importance weights for fields: higher = keep longer during compression
FIELD_IMPORTANCE_WEIGHTS = {
    "score": 10,
    "overall_score": 10,
    "geo_score": 10,
    "grade": 10,
    "issues_critical": 9,
    "issues_warning": 8,
    "total_urls": 7,
    "audit_type": 7,
    "recommendations": 6,
    "issues": 6,
    "pages": 5,
    "urls": 4,
    "links": 3,
    "page_results": 3,
}

# Severity ordering for issue prioritization (lower index = higher priority)
_SEVERITY_ORDER = {"critical": 0, "error": 1, "warning": 2, "info": 3}


def estimate_tokens(text: str, provider: str = "anthropic") -> int:
    """Estimate token count. Uses tiktoken for OpenAI, heuristic for others."""
    if provider == "openai":
        try:
            import tiktoken

            enc = tiktoken.encoding_for_model("gpt-4")
            return len(enc.encode(text))
        except Exception:
            pass
    # Check if text contains significant non-ASCII content
    non_ascii = sum(1 for c in text if ord(c) > 127)
    if non_ascii > len(text) * 0.1:
        # Non-ASCII heavy text (French, etc.): ~1 token per 3 chars
        return len(text) // 3
    # ASCII-dominant text: ~1 token per 4 chars
    return len(text) // 4


def _get_severity(item: Any) -> int:
    """Extract severity rank from an item (dict with 'severity' or 'level' key)."""
    if not isinstance(item, dict):
        return 99
    severity = item.get("severity", item.get("level", "info"))
    if isinstance(severity, str):
        return _SEVERITY_ORDER.get(severity.lower(), 99)
    return 99


def _get_issue_count(item: Any) -> int:
    """Extract total issue count from a page-like dict for sorting."""
    if not isinstance(item, dict):
        return 0
    count = 0
    for key in ("issues_critical", "issues_warning", "issues_count", "errors", "warnings"):
        val = item.get(key, 0)
        if isinstance(val, int):
            count += val
        elif isinstance(val, list):
            count += len(val)
    return count


class TokenBudget:
    """Compress and manage audit data to fit within LLM token limits."""

    # Fields to always keep (high signal-to-noise ratio)
    PRIORITY_FIELDS = {
        "score",
        "overall_score",
        "total_urls",
        "issues_critical",
        "issues_warning",
        "audit_type",
        "geo_score",
        "grade",
    }

    # Fields that can be truncated
    TRUNCATABLE_FIELDS = {
        "urls",
        "pages",
        "page_results",
        "issues",
        "recommendations",
        "links",
        "top_pages",
        "top_queries",
        "low_ctr_opportunities",
    }

    # Fields to drop when space is tight
    LOW_PRIORITY_FIELDS = {
        "raw_response",
        "raw_html",
        "html_content",
        "response_headers",
    }

    @classmethod
    def prepare_audit_data(
        cls, raw_data: dict, max_tokens: int = 6000, provider: str = "anthropic"
    ) -> dict:
        """Compress audit data to fit within the token budget."""
        # Remove low-priority fields first
        cleaned = cls._remove_low_priority(raw_data)

        # Check if it fits
        serialized = json.dumps(cleaned, default=str)
        current_tokens = estimate_tokens(serialized, provider)

        if current_tokens <= max_tokens:
            return cleaned

        # Truncate list fields with severity awareness
        cleaned = cls._truncate_lists(cleaned, max_tokens, provider)

        # Final check - if still too large, aggressive compress
        serialized = json.dumps(cleaned, default=str)
        if estimate_tokens(serialized, provider) > max_tokens:
            cleaned = cls._aggressive_compress(cleaned, max_tokens, provider)

        return cleaned

    @classmethod
    def compress_for_display(cls, data: dict, max_tokens: int = 10000) -> dict:
        """Lighter compression for displaying results to users (vs LLM input).

        Keeps more detail than prepare_audit_data, only removes truly
        low-value fields and lightly truncates very long lists.
        """
        cleaned = cls._remove_low_priority(data)

        serialized = json.dumps(cleaned, default=str)
        if estimate_tokens(serialized) <= max_tokens:
            return cleaned

        # Light truncation: keep up to 20 items per list
        result: dict[str, Any] = {}
        for key, value in cleaned.items():
            if key in cls.TRUNCATABLE_FIELDS and isinstance(value, list):
                max_items = min(20, len(value))
                if key == "issues":
                    result[key] = _sort_issues_by_severity(value)[:max_items]
                elif key == "pages":
                    result[key] = _sort_pages_by_issues(value)[:max_items]
                else:
                    result[key] = value[:max_items]
                if len(value) > max_items:
                    result[f"_{key}_total"] = len(value)
                    result[f"_{key}_truncated"] = True
            elif isinstance(value, dict):
                result[key] = cls._remove_low_priority(value)
            else:
                result[key] = value

        return result

    @classmethod
    def _remove_low_priority(cls, data: dict) -> dict:
        """Remove fields that are not useful for LLM analysis."""
        if not isinstance(data, dict):
            return data
        result: dict[str, Any] = {}
        for key, value in data.items():
            if key in cls.LOW_PRIORITY_FIELDS:
                continue
            if isinstance(value, dict):
                result[key] = cls._remove_low_priority(value)
            elif isinstance(value, list):
                result[key] = [
                    cls._remove_low_priority(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    @classmethod
    def _truncate_lists(cls, data: dict, max_tokens: int, provider: str = "anthropic") -> dict:
        """Truncate long lists to fit the budget, with severity-aware sorting."""
        if not isinstance(data, dict):
            return data
        result: dict[str, Any] = {}
        for key, value in data.items():
            if key in cls.TRUNCATABLE_FIELDS and isinstance(value, list):
                max_items = max(5, len(value) // 3)

                if key == "issues":
                    # Severity-aware: keep at least 1 of each severity, critical first
                    result[key] = _select_issues_by_severity(value, max_items)
                elif key in ("pages", "page_results"):
                    # Keep pages with most issues first
                    result[key] = _sort_pages_by_issues(value)[:max_items]
                else:
                    result[key] = value[:max_items]

                if len(value) > max_items:
                    result[f"_{key}_total"] = len(value)
                    result[f"_{key}_truncated"] = True
            elif isinstance(value, dict):
                result[key] = cls._truncate_lists(value, max_tokens, provider)
            else:
                result[key] = value
        return result

    @classmethod
    def _aggressive_compress(cls, data: dict, max_tokens: int, provider: str = "anthropic") -> dict:
        """Aggressively compress data when other methods aren't enough."""
        result = {}

        # Sort fields by importance (highest first), unweighted fields last
        sorted_keys = sorted(
            data.keys(),
            key=lambda k: FIELD_IMPORTANCE_WEIGHTS.get(k, 0),
            reverse=True,
        )

        for key in sorted_keys:
            value = data[key]

            if key in cls.PRIORITY_FIELDS:
                # Always keep scores and grades as-is
                result[key] = value
            elif key == "issues" and isinstance(value, list):
                # Keep up to 5 representative issues: all critical first, then warnings
                result[key] = _select_issues_by_severity(value, 5)
                if len(value) > 5:
                    result[f"_{key}_total"] = len(value)
            elif key == "recommendations" and isinstance(value, list):
                # Keep first 5 recommendations
                result[key] = value[:5]
                if len(value) > 5:
                    result[f"_{key}_total"] = len(value)
            elif isinstance(value, dict):
                # Keep scalar values + summarize lists as counts
                compressed: dict[str, Any] = {}
                for k, v in value.items():
                    if isinstance(v, list):
                        compressed[f"{k}_count"] = len(v)
                    elif isinstance(v, dict):
                        # Keep scalar sub-values only
                        compressed[k] = {
                            sk: sv for sk, sv in v.items() if not isinstance(sv, (dict, list))
                        }
                    else:
                        compressed[k] = v
                result[key] = compressed
            elif isinstance(value, list):
                result[key] = value[:3]
                if len(value) > 3:
                    result[f"_{key}_total"] = len(value)
            elif isinstance(value, str) and len(value) > 200:
                result[key] = value[:200] + "..."
            else:
                result[key] = value

            # Check if we're within budget
            serialized = json.dumps(result, default=str)
            if estimate_tokens(serialized, provider) > max_tokens * 0.9:
                break

        return result


def _sort_issues_by_severity(issues: list) -> list:
    """Sort issues by severity (critical first, then warning, then info)."""
    return sorted(issues, key=_get_severity)


def _sort_pages_by_issues(pages: list) -> list:
    """Sort pages by total issue count (most issues first)."""
    return sorted(pages, key=_get_issue_count, reverse=True)


def _select_issues_by_severity(issues: list, max_items: int) -> list:
    """Select issues ensuring at least 1 per severity level, critical first.

    Strategy:
    1. Group issues by severity
    2. Pick at least 1 from each severity level (critical > error > warning > info)
    3. Fill remaining slots starting from the highest severity
    """
    if len(issues) <= max_items:
        return issues

    # Group by severity
    by_severity: dict[int, list] = {}
    for item in issues:
        sev = _get_severity(item)
        by_severity.setdefault(sev, []).append(item)

    selected = []
    remaining_budget = max_items

    # Phase 1: pick 1 from each severity level present
    for sev_rank in sorted(by_severity.keys()):
        if remaining_budget <= 0:
            break
        group = by_severity[sev_rank]
        selected.append(group[0])
        remaining_budget -= 1

    # Phase 2: fill remaining slots from highest severity groups
    for sev_rank in sorted(by_severity.keys()):
        if remaining_budget <= 0:
            break
        group = by_severity[sev_rank]
        # Skip the first item (already selected in phase 1)
        for item in group[1:]:
            if remaining_budget <= 0:
                break
            selected.append(item)
            remaining_budget -= 1

    return selected
