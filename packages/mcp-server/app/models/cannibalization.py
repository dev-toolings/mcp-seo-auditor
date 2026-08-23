"""Keyword cannibalization model."""

from pydantic import BaseModel, Field


class CannibalizationGroup(BaseModel):
    urls: list[str] = Field(default_factory=list)
    shared_keywords: list[str] = Field(default_factory=list)
    similarity_score: float = 0.0
    recommendation: str = ""
