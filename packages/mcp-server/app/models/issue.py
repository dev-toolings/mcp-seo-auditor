"""SEO issue model."""

from pydantic import BaseModel, Field


class Issue(BaseModel):
    issue_type: str
    severity: str = "warning"
    urls: list[str] = Field(default_factory=list)
    description: str = ""
    recommendation: str = ""
