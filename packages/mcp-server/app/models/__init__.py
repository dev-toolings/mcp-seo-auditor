"""Pydantic data models for the SEO auditor."""

from app.models.cannibalization import CannibalizationGroup
from app.models.eeat_models import EEATDimension, EEATPageResult, EEATReport
from app.models.geo_models import GEODimension, GEOPageResult, GEOReport
from app.models.issue import Issue
from app.models.report import AuditReport, AuditType

__all__ = [
    "AuditReport",
    "AuditType",
    "CannibalizationGroup",
    "EEATDimension",
    "EEATPageResult",
    "EEATReport",
    "GEODimension",
    "GEOPageResult",
    "GEOReport",
    "Issue",
]
