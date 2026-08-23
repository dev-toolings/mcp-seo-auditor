"""E-E-A-T (Experience, Expertise, Authoritativeness, Trustworthiness) models."""

from typing import Any

from pydantic import BaseModel, Field


class EEATDimension(BaseModel):
    name: str
    score: int = 0
    signals: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class EEATPageResult(BaseModel):
    url: str
    eeat_score: int = 0
    experience: EEATDimension
    expertise: EEATDimension
    authoritativeness: EEATDimension
    trustworthiness: EEATDimension
    has_author_info: bool = False
    has_author_page: bool = False
    has_organization_schema: bool = False
    has_person_schema: bool = False
    issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class EEATReport(BaseModel):
    eeat_score: int = 0
    grade: str = "F"
    experience_score: int = 0
    expertise_score: int = 0
    authoritativeness_score: int = 0
    trustworthiness_score: int = 0
    page_results: list[EEATPageResult] = Field(default_factory=list)
    cross_page_consistency: dict[str, Any] = Field(default_factory=dict)
    author_coverage: dict[str, Any] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    ai_enhanced: bool = False
