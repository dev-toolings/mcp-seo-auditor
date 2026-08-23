"""Shared validators and bounded types for MCP tool inputs."""

import json
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, model_validator

from app.core.security import validate_url


class MCPInput(BaseModel):
    """Base class for all MCP tool inputs.

    Handles JSON string coercion: some MCP clients serialize the input
    dict as a JSON string instead of passing a dict directly.
    """

    @model_validator(mode="before")
    @classmethod
    def _coerce_json_string(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (ValueError, TypeError):
                return v
        return v


def _validate_url_safe(url: str) -> str:
    """Validate a single URL for SSRF safety."""
    return validate_url(url)


def _validate_url_list(urls: list[str]) -> list[str]:
    """Validate each URL in a list."""
    return [validate_url(u) for u in urls]


SafeUrl = Annotated[str, AfterValidator(_validate_url_safe)]
SafeUrlList = Annotated[list[str], AfterValidator(_validate_url_list)]

# Bounded integer types matching _BOUNDS_DEFAULTS in app/core/security.py
BoundedMaxUrls = Annotated[int, Field(ge=1, le=1000)]
BoundedMaxPages = Annotated[int, Field(ge=1, le=500)]
BoundedLimit = Annotated[int, Field(ge=1, le=100)]
BoundedDays = Annotated[int, Field(ge=1, le=365)]
BoundedMaxActions = Annotated[int, Field(ge=1, le=50)]
BoundedMaxResults = Annotated[int, Field(ge=1, le=50)]
BoundedSampleSize = Annotated[int, Field(ge=1, le=500)]
BoundedPeriods = Annotated[int, Field(ge=1, le=52)]
BoundedPeriodDays = Annotated[int, Field(ge=1, le=90)]
