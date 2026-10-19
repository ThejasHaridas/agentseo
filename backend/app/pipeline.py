"""Audit pipeline (requirements doc, section 7).

URL -> Crawl -> (SEO | Readability | Actionability | Agent Tests | AI Visibility) -> Scoring -> Verdict -> Fixes.
Static results are committed as soon as they exist, so they are readable while agent tests and
visibility checks (the slow, LLM-bound stages) are still running.
"""

import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app import fixes as fix_gen
from app import verdict as verdict_mod
from app.config import settings
from app.crawler.crawl import CrawlResult, crawl
from app.db import SessionLocal
from app.models import AgentTest, Audit, Finding, Fix, Page, Score, VisibilityCheck
from app.modules import actionability, agent_tests, readability, seo, visibility
from app.modules.base import AuditContext, ModuleResult, PageData
from app.modules.classify import classify
from app.scoring import overall_agent_ready

log = logging.getLogger(__name__)


def _read(path: Path | None) -> str | None:
    return path.read_text(encoding="utf-8") if path else None


def build_context(audit: Audit, result: CrawlResult) -> AuditContext:
    url = audit.site.url
    base = url.split("/", 3)
    return AuditContext(
        base_url="/".join(base[:3]) + "/",
        site_files=result.site_files,
        pages=[PageData(p.url, p.status_code, _read(p.raw_html_path), _read(p.rendered_html_path), p.metrics)
               for p in result.pages],
        sitemap_urls=result.sitemap_urls,
        business_type=audit.business_type,
        tasks=audit.tasks,
    )


def analyse(ctx: AuditContext) -> tuple[list[ModuleResult], dict]:
    with httpx.Client(headers={"User-Agent": settings.user_agent}, timeout=settings.request_timeout_s,
                      follow_redirects=True) as client:
        results = [seo.run(ctx, client), readability.run(ctx), actionability.run(ctx)]
    return results, classify(ctx)


class _Timer:
    def __init__(self, audit_id: str):
        self.audit_id, self.t0 = audit_id, time.monotonic()

    def lap(self, stage: str, extra: str = "") -> None:
        now = time.monotonic()
        log.info("audit %s: %s in %.0fs %s", self.audit_id, stage, now - self.t0, extra)
        self.t0 = now


def run_audit(audit_id: str) -> None:
    with SessionLocal() as session:
        audit = session.get(Audit, audit_id)
        if audit is None:
            log.error("audit %s not found", audit_id)
            return
        audit.status = "running"
        audit.started_at = datetime.now(UTC)
        session.commit()
        timer = _Timer(audit.id)

        try:
            result = crawl(audit.site.url, settings.storage_dir / audit.id)
            timer.lap("crawl", f"({len(result.pages)} pages)")
            audit.site_files = result.site_files
            for p in result.pages:
                session.add(Page(
                    audit_id=audit.id,
                    url=p.url,
                    status_code=p.status_code,
                    raw_html_ref=str(p.raw_html_path) if p.raw_html_path else None,
                    rendered_html_ref=str(p.rendered_html_path) if p.rendered_html_path else None,
                    metrics=p.metrics,
                ))
            session.commit()

            ctx = build_context(audit, result)
            module_results, classification = analyse(ctx)
            timer.lap("static analysis")
            audit.classification = classification
            audit.site.type = classification["site_type"]
            findings = _store_module_results(session, audit, module_results)
            session.commit()

            runs, task_result = agent_tests.run(ctx, classification, settings.storage_dir / audit.id / "agent")
            timer.lap("agent tests", f"({len(runs)} runs)")
            _store_agent_runs(session, audit, runs)
            findings |= _store_module_results(session, audit, [task_result])
            session.commit()

            answers, vis_result, vis_summary = visibility.run(ctx, classification)
            timer.lap("ai visibility", f"({len(answers)} answers)")
            _store_visibility(session, audit, answers)
            audit.visibility = vis_summary
            findings |= _store_module_results(session, audit, [vis_result])
            all_results = module_results + [task_result, vis_result]
            _store_overall(session, audit, all_results)
            session.commit()

            generated = fix_gen.generate(ctx, classification, all_results)
            fixed_ids = _store_fixes(session, findings, generated)
            audit.verdict = verdict_mod.build(classification, all_results, vis_summary, fixed_ids)
            timer.lap("fixes + verdict", f"({len(generated)} fixes, {audit.verdict['priority']})")
            audit.status = "done"
        except Exception as exc:
            log.exception("audit %s failed", audit_id)
            audit.status = "failed"
            audit.error = str(exc)
        finally:
            audit.finished_at = datetime.now(UTC)
            session.commit()


def _store_module_results(session, audit: Audit, module_results: list[ModuleResult]) -> dict[str, Finding]:
    """Store each module's score and a finding per non-passing check; returns findings by check id."""
    findings: dict[str, Finding] = {}
    for mr in module_results:
        session.add(Score(audit_id=audit.id, category=mr.module, value=mr.score,
                          details={"checks": [c.to_dict() for c in mr.checks]}))
        for c in mr.checks:
            if c.status in ("partial", "fail"):
                finding = Finding(
                    audit_id=audit.id,
                    category=mr.module,
                    severity=c.severity if c.status == "fail" else _soften(c.severity),
                    title=c.title,
                    evidence={"check_id": c.id, "status": c.status, "detail": c.detail,
                              "fix_hint": c.fix_hint, **c.evidence},
                    impact_estimate=mr.impact(c),
                )
                session.add(finding)
                findings[c.id] = finding
    return findings


def _store_agent_runs(session, audit: Audit, runs: list[agent_tests.RunResult]) -> None:
    for r in runs:
        session.add(AgentTest(
            audit_id=audit.id, task=r.task, run_no=r.run_no, success=r.success, answer=r.answer,
            steps=r.steps, failure_reason=r.failure_reason, screenshots=r.screenshots,
            tokens=r.tokens, seconds=r.seconds, blocked_submits=r.blocked_submits,
        ))


def _store_visibility(session, audit: Audit, answers: list[visibility.VisibilityAnswer]) -> None:
    for a in answers:
        session.add(VisibilityCheck(
            audit_id=audit.id, prompt=a.prompt, intent=a.intent, provider=a.provider, sample=a.sample,
            mentioned=a.mentioned, cited_url=a.cited_url, in_sources=a.in_sources, competitors=a.competitors,
            answer=a.answer, source_urls=a.source_urls, searched=a.searched, error=a.error,
        ))


def _store_overall(session, audit: Audit, module_results: list[ModuleResult]) -> None:
    overall = overall_agent_ready({mr.module: mr.score for mr in module_results}, audit.site.type)
    session.add(Score(audit_id=audit.id, category="agent_ready", value=overall["value"], details=overall))


def _store_fixes(session, findings: dict[str, Finding], generated: list[fix_gen.GeneratedFix]) -> set[str]:
    """Attach each fix to every finding it resolves (FR-32); returns the check ids that now have a fix."""
    fixed: set[str] = set()
    for g in generated:
        for check_id in g.check_ids:
            finding = findings.get(check_id)
            if finding is None:
                continue
            session.add(Fix(finding=finding, type=g.type, title=g.title, content=g.content, meta=g.meta))
            fixed.add(check_id)
    return fixed


def _soften(severity: str) -> str:
    """A partially passing check is one step less severe than a failing one."""
    return {"critical": "warning", "warning": "info"}.get(severity, severity)
