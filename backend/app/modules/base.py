"""Shared types for analysis modules: the audit context they read and the checks they return."""

import json
from dataclasses import asdict, dataclass, field
from functools import cached_property
from typing import Literal

from bs4 import BeautifulSoup

Status = Literal["pass", "partial", "fail", "na"]
Severity = Literal["critical", "warning", "info"]

CREDIT: dict[str, float] = {"pass": 1.0, "partial": 0.5, "fail": 0.0}


@dataclass
class PageData:
    url: str
    status_code: int | None
    raw_html: str | None
    rendered_html: str | None
    metrics: dict = field(default_factory=dict)

    @property
    def html(self) -> str:
        """Best available DOM: rendered if we have it, else raw."""
        return self.rendered_html or self.raw_html or ""

    @cached_property
    def soup(self) -> BeautifulSoup:
        return BeautifulSoup(self.html, "lxml")

    @cached_property
    def raw_soup(self) -> BeautifulSoup:
        return BeautifulSoup(self.raw_html or "", "lxml")

    @cached_property
    def json_ld(self) -> list[dict]:
        """JSON-LD objects from the raw HTML (what an agent sees without running JS), @graph flattened."""
        items: list[dict] = []
        for tag in self.raw_soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "")
            except (json.JSONDecodeError, TypeError):
                items.append({"_invalid": True})
                continue
            stack = data if isinstance(data, list) else [data]
            while stack:
                obj = stack.pop()
                if isinstance(obj, dict):
                    items.append(obj)
                    stack.extend(obj.get("@graph", []) if isinstance(obj.get("@graph"), list) else [])
                elif isinstance(obj, list):
                    stack.extend(obj)
        return items


@dataclass
class AuditContext:
    base_url: str
    site_files: dict
    pages: list[PageData]
    sitemap_urls: list[str] = field(default_factory=list)
    business_type: str | None = None
    tasks: list[str] = field(default_factory=list)

    @property
    def html_pages(self) -> list[PageData]:
        return [p for p in self.pages if p.html]

    @property
    def home(self) -> PageData | None:
        pages = self.html_pages
        return pages[0] if pages else None

    def file_body(self, path: str) -> str | None:
        f = self.site_files.get(path) or {}
        return f.get("body") if f.get("found") else None


@dataclass
class Check:
    id: str
    title: str
    status: Status
    weight: float
    severity: Severity = "warning"  # severity if this check does not pass
    detail: str = ""
    evidence: dict = field(default_factory=dict)
    fix_hint: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ModuleResult:
    module: str
    checks: list[Check]
    # Set when a module measures a rate directly (e.g. agent task success) rather than pass/partial/fail.
    score_override: float | None = None

    @property
    def score(self) -> float | None:
        """Weighted sum of check credit (pass = full, partial = half, fail = 0); n/a checks excluded."""
        if self.score_override is not None:
            return self.score_override
        scored = [c for c in self.checks if c.status in CREDIT]
        total = sum(c.weight for c in scored)
        if not total:
            return None
        return round(100 * sum(c.weight * CREDIT[c.status] for c in scored) / total, 1)

    def impact(self, check: Check) -> float:
        """Points this module's score would gain if `check` passed."""
        total = sum(c.weight for c in self.checks if c.status in CREDIT)
        if not total or check.status not in CREDIT:
            return 0.0
        return round(100 * check.weight * (1 - CREDIT[check.status]) / total, 1)


def ratio_status(ratio: float, pass_at: float, partial_at: float) -> Status:
    if ratio >= pass_at:
        return "pass"
    if ratio >= partial_at:
        return "partial"
    return "fail"


def pct(n: int, d: int) -> float:
    return n / d if d else 0.0


def schema_types(items: list[dict]) -> set[str]:
    types: set[str] = set()
    for obj in items:
        t = obj.get("@type")
        for name in t if isinstance(t, list) else [t]:
            if isinstance(name, str):
                types.add(name.split("/")[-1])
    return types
