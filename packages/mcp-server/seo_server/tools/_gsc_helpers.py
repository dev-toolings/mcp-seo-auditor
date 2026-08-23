"""Shared helpers for GSC tools."""


def gsc_credentials_error() -> dict:
    return {
        "error": "Google Search Console credentials not configured. Set GOOGLE_CREDENTIALS_PATH.",
        "error_type": "ConfigurationError",
        "recoverable": False,
    }
