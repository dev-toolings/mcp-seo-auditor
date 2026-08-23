"""GEO (Generative Engine Optimization) models."""

from typing import Any

from pydantic import BaseModel, Field


class GEODimension(BaseModel):
    name: str
    score: int = 0
    weight: float = 0.0
    details: dict[str, Any] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)


class GEOPageResult(BaseModel):
    url: str
    geo_score: int = 0
    ai_readability: int = 0
    schema_coverage: int = 0
    faq_completeness: int = 0
    eeat_score: int = 0
    citation_readiness: int = 0
    issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class GEOReport(BaseModel):
    geo_score: int = 0
    grade: str = "F"
    dimensions: list[GEODimension] = Field(default_factory=list)
    page_results: list[GEOPageResult] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
