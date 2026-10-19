"""Prototype data model (requirements doc, section 8)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.scoring import RUBRIC_VERSION


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UserSession(Base):
    """A login session. Only the SHA-256 of the cookie token is stored."""

    __tablename__ = "user_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()


PROJECT_COLORS = ("blue", "green", "yellow", "red", "teal", "rose", "gray")


class Project(Base):
    """A folder of audits, e.g. one client or one brand's sites."""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(280), default="")
    color: Mapped[str] = mapped_column(String(16), default="blue")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    audits: Mapped[list["Audit"]] = relationship(back_populates="project")


class Site(Base):
    __tablename__ = "sites"
    __table_args__ = (UniqueConstraint("user_id", "url"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    url: Mapped[str] = mapped_column(String(2048), index=True)
    type: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    audits: Mapped[list["Audit"]] = relationship(back_populates="site")


class Audit(Base):
    __tablename__ = "audits"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    site_id: Mapped[str] = mapped_column(ForeignKey("sites.id"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|done|failed
    rubric_version: Mapped[str] = mapped_column(String(16), default=RUBRIC_VERSION)
    business_type: Mapped[str | None] = mapped_column(String(64))
    tasks: Mapped[list[str]] = mapped_column(JSON, default=list)
    # robots.txt, sitemap, llms.txt, /.well-known/ etc. (FR-4)
    site_files: Mapped[dict] = mapped_column(JSON, default=dict)
    # site type, summary, likely agent tasks (FR-26)
    classification: Mapped[dict] = mapped_column(JSON, default=dict)
    # mention/citation rates, intervals, competitors (FR-25)
    visibility: Mapped[dict] = mapped_column(JSON, default=dict)
    # "do you need this?" priority, factors, explanation, projected scores (FR-27, FR-28)
    verdict: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    site: Mapped[Site] = relationship(back_populates="audits")
    project: Mapped[Project | None] = relationship(back_populates="audits")
    pages: Mapped[list["Page"]] = relationship(back_populates="audit", cascade="all, delete-orphan")
    findings: Mapped[list["Finding"]] = relationship(back_populates="audit", cascade="all, delete-orphan")
    scores: Mapped[list["Score"]] = relationship(back_populates="audit", cascade="all, delete-orphan")


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    audit_id: Mapped[str] = mapped_column(ForeignKey("audits.id"), index=True)
    url: Mapped[str] = mapped_column(String(2048))
    status_code: Mapped[int | None] = mapped_column(Integer)
    raw_html_ref: Mapped[str | None] = mapped_column(String(512))
    rendered_html_ref: Mapped[str | None] = mapped_column(String(512))
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)

    audit: Mapped[Audit] = relationship(back_populates="pages")


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    audit_id: Mapped[str] = mapped_column(ForeignKey("audits.id"), index=True)
    category: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))  # critical|warning|info
    title: Mapped[str] = mapped_column(String(512))
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    impact_estimate: Mapped[float | None] = mapped_column(Float)

    audit: Mapped[Audit] = relationship(back_populates="findings")
    fixes: Mapped[list["Fix"]] = relationship(back_populates="finding", cascade="all, delete-orphan")


class Fix(Base):
    __tablename__ = "fixes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    finding_id: Mapped[str] = mapped_column(ForeignKey("findings.id"), index=True)
    type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(256), default="")
    content: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)

    finding: Mapped[Finding] = relationship(back_populates="fixes")


class AgentTest(Base):
    __tablename__ = "agent_tests"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    audit_id: Mapped[str] = mapped_column(ForeignKey("audits.id"), index=True)
    task: Mapped[str] = mapped_column(String(512))
    run_no: Mapped[int] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    answer: Mapped[str | None] = mapped_column(Text)
    steps: Mapped[list] = mapped_column(JSON, default=list)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    screenshots: Mapped[list[str]] = mapped_column(JSON, default=list)
    tokens: Mapped[dict] = mapped_column(JSON, default=dict)
    seconds: Mapped[float | None] = mapped_column(Float)
    blocked_submits: Mapped[int] = mapped_column(Integer, default=0)


class VisibilityCheck(Base):
    __tablename__ = "visibility_checks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    audit_id: Mapped[str] = mapped_column(ForeignKey("audits.id"), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(64))
    sample: Mapped[int] = mapped_column(Integer, default=1)
    mentioned: Mapped[bool] = mapped_column(Boolean, default=False)
    cited_url: Mapped[str | None] = mapped_column(String(2048))
    in_sources: Mapped[bool] = mapped_column(Boolean, default=False)
    competitors: Mapped[list[str]] = mapped_column(JSON, default=list)
    answer: Mapped[str | None] = mapped_column(Text)
    source_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    searched: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text)


class Score(Base):
    __tablename__ = "scores"

    audit_id: Mapped[str] = mapped_column(ForeignKey("audits.id"), primary_key=True)
    category: Mapped[str] = mapped_column(String(32), primary_key=True)
    value: Mapped[float | None] = mapped_column(Float)
    # contributing checks and weights, so every score can explain itself
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    audit: Mapped[Audit] = relationship(back_populates="scores")
