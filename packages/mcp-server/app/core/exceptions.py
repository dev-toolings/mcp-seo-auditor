"""Custom exceptions for SEO Auditor."""

from typing import Any


class SEOAuditorError(Exception):
    """Base exception for SEO Auditor."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class SitemapFetchError(SEOAuditorError):
    """Raised when sitemap cannot be fetched."""

    def __init__(self, url: str, reason: str):
        super().__init__(f"Failed to fetch sitemap from {url}: {reason}")


class SitemapParseError(SEOAuditorError):
    """Raised when sitemap XML is invalid."""

    def __init__(self, reason: str):
        super().__init__(f"Failed to parse sitemap XML: {reason}")


class CrawlError(SEOAuditorError):
    """Raised when a page cannot be crawled."""

    def __init__(self, url: str, reason: str):
        super().__init__(f"Failed to crawl {url}: {reason}")


class ReportNotFoundError(SEOAuditorError):
    """Raised when a report is not found."""

    def __init__(self, audit_id: str):
        super().__init__(f"Report not found: {audit_id}")


class LLMError(SEOAuditorError):
    """Base exception for LLM-related errors."""

    def __init__(self, message: str):
        super().__init__(f"LLM error: {message}")


class LLMProviderNotAvailableError(LLMError):
    """Raised when a requested LLM provider is not available."""

    def __init__(self, provider: str):
        super().__init__(f"Provider not available: {provider}")


class LLMTokenBudgetExceededError(LLMError):
    """Raised when input data exceeds the token budget."""

    def __init__(self, estimated: int, max_tokens: int):
        super().__init__(f"Token budget exceeded: {estimated} > {max_tokens}")


class InvalidURLError(SEOAuditorError):
    """Raised when a URL fails validation (scheme, SSRF, length)."""

    def __init__(self, reason: str):
        super().__init__(f"Invalid URL: {reason}")


class ParameterBoundsError(SEOAuditorError):
    """Raised when a parameter value is outside acceptable bounds."""

    def __init__(self, param_name: str, value: Any, reason: str):
        self.param_name = param_name
        self.value = value
        super().__init__(f"Parameter bounds error: {reason}")
