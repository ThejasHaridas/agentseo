from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class AuditCreate(BaseModel):
    url: HttpUrl
    project_id: str | None = None  # defaults to the account's first project
    business_type: str | None = None
    tasks: list[str] = Field(default_factory=list, max_length=5, description='e.g. "book a table"')


class PageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    url: str
    status_code: int | None
    metrics: dict


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    site_id: str
    status: str
    rubric_version: str
    business_type: str | None
    tasks: list[str]
    classification: dict
    visibility: dict
    verdict: dict
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    page_count: int = 0
    site_url: str = ""
    site_type: str | None = None
    score_summary: dict[str, float | None] = {}
    priority: str | None = None
    screenshot_url: str | None = None
    project_id: str | None = None
    project_name: str | None = None


class SiteFileOut(BaseModel):
    url: str
    found: bool
    status: int | None = None
    content_type: str | None = None


class ScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: str
    value: float | None
    details: dict


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    category: str
    severity: str
    title: str
    evidence: dict
    impact_estimate: float | None


class AgentTestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task: str
    run_no: int
    success: bool
    answer: str | None
    failure_reason: str | None
    steps: list[dict]
    screenshots: list[str]  # URLs under /storage
    tokens: dict
    seconds: float | None
    blocked_submits: int


class VisibilityCheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    prompt: str
    intent: str | None
    provider: str
    sample: int
    mentioned: bool
    cited_url: str | None
    in_sources: bool
    competitors: list[str]
    answer: str | None
    source_urls: list[str]
    searched: bool
    error: str | None


class FixOut(BaseModel):
    id: str
    finding_ids: list[str]
    finding_titles: list[str]
    check_ids: list[str]
    severity: str  # most severe of the findings it resolves
    impact_estimate: float | None  # combined score gain
    type: str
    title: str
    content: str
    meta: dict


_EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(pattern=_EMAIL, max_length=320)
    password: str = Field(min_length=10, max_length=200)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Enter your name.")
        return v


class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
    created_at: datetime


ProjectColor = Literal["blue", "green", "yellow", "red", "teal", "rose", "gray"]


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=280)
    color: ProjectColor = "blue"

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Give the project a name.")
        return v.strip()


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=280)
    color: ProjectColor | None = None


class ProjectSite(BaseModel):
    site_id: str
    url: str
    latest_audit_id: str
    status: str
    agent_ready: float | None
    seo: float | None
    started_at: datetime | None
    screenshot_url: str | None = None


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str
    color: str
    created_at: datetime
    audit_count: int = 0
    running: int = 0
    last_audit_at: datetime | None = None
    avg_agent_ready: float | None = None
    sites: list[ProjectSite] = []
