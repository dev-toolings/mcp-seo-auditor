"""Audit report models."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class AuditType(str, Enum):
    SITEMAP = "sitemap"
    FULL = "full"
    CONTENT = "content"
    TECHNICAL = "technical"
    GEO = "geo"
    EEAT = "eeat"


class AuditReport(BaseModel):
    audit_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    audit_type: AuditType
    score: int = 0
    total_urls: int = 0
    issues_critical: int = 0
    issues_warning: int = 0
    issues: list[Any] = Field(default_factory=list)
    recommendations: list[Any] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
