from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app import auth
from app.auth import current_user
from app.db import get_session, init_db
from app.models import AgentTest, Audit, Finding, Fix, Page, Project, Site, User, VisibilityCheck
from app.pipeline import run_audit
from app.schemas import (
    AgentTestOut, AuditCreate, AuditOut, FindingOut, FixOut, LoginIn, PageOut, ProjectIn, ProjectOut, ProjectPatch,
    ProjectSite, RegisterIn, ScoreOut, SiteFileOut, UserOut, VisibilityCheckOut,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="AgentRank API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_methods=["*"], allow_headers=["*"])
settings.storage_dir.mkdir(parents=True, exist_ok=True)
# Raw evidence (HTML, agent screenshots) for every finding.
app.mount("/storage", StaticFiles(directory=settings.storage_dir), name="storage")


def _audit_out(session: Session, audit: Audit) -> AuditOut:
    pages = session.scalars(select(Page).where(Page.audit_id == audit.id)).all()
    shot = next((p.metrics["screenshot"] for p in pages if p.metrics.get("screenshot")), None)
    return AuditOut.model_validate(audit).model_copy(update={
        "page_count": len(pages),
        "site_url": audit.site.url,
        "site_type": audit.site.type,
        "score_summary": {s.category: s.value for s in audit.scores},
        "priority": (audit.verdict or {}).get("priority"),
        "screenshot_url": _storage_url(shot) if shot else None,
        "project_id": audit.project_id,
        "project_name": audit.project.name if audit.project else None,
    })


def _get_audit(session: Session, audit_id: str, user: User) -> Audit:
    audit = session.get(Audit, audit_id)
    # Another user's audit is reported as missing, not forbidden, so ids reveal nothing.
    if audit is None or audit.site.user_id != user.id:
        raise HTTPException(404, "audit not found")
    return audit


@app.get("/health")
def health() -> dict:
    return {"ok": True, "queue": settings.use_queue}


@app.post("/audits", response_model=AuditOut, status_code=202)
def create_audit(body: AuditCreate, background: BackgroundTasks, user: User = Depends(current_user), session: Session = Depends(get_session)):
    url = str(body.url)
    project = _get_project(session, body.project_id, user) if body.project_id else _default_project(session, user)
    site = session.scalar(select(Site).where(Site.url == url, Site.user_id == user.id)) or Site(url=url, user_id=user.id)
    audit = Audit(site=site, project=project, business_type=body.business_type, tasks=body.tasks)
    session.add(audit)
    session.commit()

    if settings.use_queue:
        from app.worker import run_audit_task

        run_audit_task.delay(audit.id)
    else:
        background.add_task(run_audit, audit.id)
    return _audit_out(session, audit)


@app.get("/audits", response_model=list[AuditOut])
def list_audits(site_id: str | None = None, project_id: str | None = None,
                user: User = Depends(current_user), session: Session = Depends(get_session)):
    query = (select(Audit).join(Site).where(Site.user_id == user.id)
             .order_by(Audit.started_at.desc().nulls_first()).limit(200))
    if site_id:
        query = query.where(Audit.site_id == site_id)
    if project_id:
        query = query.where(Audit.project_id == project_id)
    return [_audit_out(session, a) for a in session.scalars(query)]


@app.get("/audits/{audit_id}", response_model=AuditOut)
def get_audit(audit_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    return _audit_out(session, _get_audit(session, audit_id, user))


@app.get("/audits/{audit_id}/pages", response_model=list[PageOut])
def get_audit_pages(audit_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    return _get_audit(session, audit_id, user).pages


@app.get("/audits/{audit_id}/site-files", response_model=dict[str, SiteFileOut])
def get_site_files(audit_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    return _get_audit(session, audit_id, user).site_files


@app.get("/audits/{audit_id}/scores", response_model=list[ScoreOut])
def get_scores(audit_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    return _get_audit(session, audit_id, user).scores


_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


@app.get("/audits/{audit_id}/findings", response_model=list[FindingOut])
def get_findings(audit_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    findings = session.scalars(select(Finding).where(Finding.audit_id == _get_audit(session, audit_id, user).id))
    return sorted(findings, key=lambda f: (_SEVERITY_ORDER.get(f.severity, 3), -(f.impact_estimate or 0)))


def _storage_url(path: str) -> str:
    return "/storage/" + Path(path).resolve().relative_to(settings.storage_dir.resolve()).as_posix()


@app.get("/audits/{audit_id}/agent-tests", response_model=list[AgentTestOut])
def get_agent_tests(audit_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    audit = _get_audit(session, audit_id, user)
    runs = session.scalars(select(AgentTest).where(AgentTest.audit_id == audit.id)
                           .order_by(AgentTest.task, AgentTest.run_no))
    return [AgentTestOut.model_validate(r).model_copy(update={"screenshots": [_storage_url(s) for s in r.screenshots]})
            for r in runs]


@app.get("/audits/{audit_id}/visibility", response_model=list[VisibilityCheckOut])
def get_visibility(audit_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    audit = _get_audit(session, audit_id, user)
    return session.scalars(select(VisibilityCheck).where(VisibilityCheck.audit_id == audit.id)
                           .order_by(VisibilityCheck.prompt, VisibilityCheck.provider))


@app.get("/audits/{audit_id}/fixes", response_model=list[FixOut])
def get_fixes(audit_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    audit = _get_audit(session, audit_id, user)
    rows = session.execute(select(Fix, Finding).join(Finding).where(Finding.audit_id == audit.id)).all()
    merged: dict[tuple, FixOut] = {}
    for fix, finding in rows:
        key = (fix.type, fix.content)
        if key not in merged:
            merged[key] = FixOut(id=fix.id, finding_ids=[], finding_titles=[], check_ids=[], severity=finding.severity,
                                 impact_estimate=0.0, type=fix.type, title=fix.title, content=fix.content, meta=fix.meta)
        out = merged[key]
        out.finding_ids.append(finding.id)
        out.finding_titles.append(finding.title)
        out.check_ids.append(finding.evidence.get("check_id"))
        out.impact_estimate = round((out.impact_estimate or 0) + (finding.impact_estimate or 0), 1)
        if _SEVERITY_ORDER.get(finding.severity, 3) < _SEVERITY_ORDER.get(out.severity, 3):
            out.severity = finding.severity
    return sorted(merged.values(), key=lambda f: (_SEVERITY_ORDER.get(f.severity, 3), -(f.impact_estimate or 0)))


@app.get("/rubric")
def get_rubric() -> dict:
    """The scoring rubric in force, so every score can be explained (requirements section 9)."""
    from app.scoring import BASE_WEIGHTS, RUBRIC_VERSION, TYPE_WEIGHTS
    from app.verdict import TYPE_NEED

    return {"version": RUBRIC_VERSION, "base_weights": BASE_WEIGHTS, "type_weights": TYPE_WEIGHTS,
            "type_need": TYPE_NEED}


# ---------- accounts ----------

@app.post("/auth/register", response_model=UserOut, status_code=201)
def register(body: RegisterIn, response: Response, session: Session = Depends(get_session)):
    email = body.email.strip().lower()
    if auth.find_user(session, email):
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    user = User(email=email, name=body.name.strip(), password_hash=auth.hash_password(body.password))
    session.add(user)
    session.flush()
    starter = Project(user_id=user.id, name="My websites", description="Sites you audit for yourself.", color="blue")
    session.add(starter)
    # Audits made before accounts existed belong to whoever registers first.
    if session.scalar(select(func.count()).select_from(User)) == 1:
        for site in session.scalars(select(Site).where(Site.user_id.is_(None))):
            site.user_id = user.id
            for audit in site.audits:
                audit.project = audit.project or starter
    session.commit()
    auth.start_session(session, user, response)
    return user


@app.post("/auth/login", response_model=UserOut)
def login(body: LoginIn, response: Response, session: Session = Depends(get_session)):
    email = body.email.strip().lower()
    auth.check_login_allowed(email)
    user = auth.find_user(session, email)
    if user is None or not auth.verify_password(body.password, user.password_hash):
        auth.record_failure(email)
        raise HTTPException(401, "That email and password don't match.")
    auth.start_session(session, user, response)
    return user


@app.post("/auth/logout", status_code=204)
def logout(request: Request, response: Response, session: Session = Depends(get_session)):
    auth.end_session(session, request, response)


@app.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


# ---------- projects ----------

def _get_project(session: Session, project_id: str, user: User) -> Project:
    project = session.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(404, "project not found")
    return project


def _default_project(session: Session, user: User) -> Project:
    project = session.scalar(select(Project).where(Project.user_id == user.id).order_by(Project.created_at))
    if project is None:
        project = Project(user_id=user.id, name="My websites", color="blue")
        session.add(project)
    return project


def _project_out(session: Session, project: Project) -> ProjectOut:
    audits = session.scalars(select(Audit).where(Audit.project_id == project.id)
                             .order_by(Audit.started_at.desc().nulls_first())).all()
    sites: dict[str, ProjectSite] = {}
    for a in audits:  # newest first, so the first audit seen per site is its latest
        if a.site_id in sites:
            continue
        scores = {sc.category: sc.value for sc in a.scores}
        shot = next((pg.metrics["screenshot"] for pg in a.pages if pg.metrics and pg.metrics.get("screenshot")), None)
        sites[a.site_id] = ProjectSite(site_id=a.site_id, url=a.site.url, latest_audit_id=a.id, status=a.status,
                                       agent_ready=scores.get("agent_ready"), seo=scores.get("seo"),
                                       started_at=a.started_at, screenshot_url=_storage_url(shot) if shot else None)
    scored = [x.agent_ready for x in sites.values() if x.status == "done" and x.agent_ready is not None]
    return ProjectOut(
        id=project.id, name=project.name, description=project.description, color=project.color,
        created_at=project.created_at, audit_count=len(audits),
        running=sum(a.status in ("queued", "running") for a in audits),
        last_audit_at=audits[0].started_at if audits else None,
        avg_agent_ready=round(sum(scored) / len(scored), 1) if scored else None,
        sites=list(sites.values()),
    )


def _adopt_orphan_audits(session: Session, user: User) -> None:
    """Audits made before projects existed join the account's first project."""
    orphans = session.scalars(select(Audit).join(Site).where(Site.user_id == user.id, Audit.project_id.is_(None))).all()
    if orphans:
        project = _default_project(session, user)
        for audit in orphans:
            audit.project = project
        session.commit()


@app.get("/projects", response_model=list[ProjectOut])
def list_projects(user: User = Depends(current_user), session: Session = Depends(get_session)):
    _adopt_orphan_audits(session, user)
    projects = session.scalars(select(Project).where(Project.user_id == user.id).order_by(Project.created_at)).all()
    return [_project_out(session, p) for p in projects]


@app.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectIn, user: User = Depends(current_user), session: Session = Depends(get_session)):
    project = Project(user_id=user.id, name=body.name, description=body.description.strip(), color=body.color)
    session.add(project)
    session.commit()
    return _project_out(session, project)


@app.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    return _project_out(session, _get_project(session, project_id, user))


@app.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, body: ProjectPatch, user: User = Depends(current_user),
                   session: Session = Depends(get_session)):
    project = _get_project(session, project_id, user)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(project, field, value.strip() if field in ("name", "description") else value)
    session.commit()
    return _project_out(session, project)


@app.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)):
    project = _get_project(session, project_id, user)
    if session.scalar(select(func.count()).select_from(Audit).where(Audit.project_id == project.id)):
        raise HTTPException(409, "Only empty projects can be deleted. This one still has audits.")
    session.delete(project)
    session.commit()
