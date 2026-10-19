"use client";

import { ArrowRight, CaretRight } from "@phosphor-icons/react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { CountUp, Meter, PriorityTag, StatusTag } from "@/components/ui";
import {
  ApiError, Audit, createProject, duration, host, normaliseUrl, Project, PROJECT_COLORS, ProjectColor, score,
  siteType, startAudit, updateProject, when,
} from "@/lib/api";

export function Monogram({ name, color, size = "" }: { name: string; color: string; size?: "" | "sm" | "lg" }) {
  const letter = name.trim().charAt(0).toUpperCase() || "?";
  return <span className={`monogram c-${color} ${size}`} aria-hidden="true">{letter}</span>;
}

/** Create a project, or edit one when `project` is given. */
export function ProjectDialog({ project, onClose, onSaved }: { project?: Project; onClose: () => void; onSaved: (p: Project) => void }) {
  const [name, setName] = useState(project?.name ?? "");
  const [description, setDescription] = useState(project?.description ?? "");
  const [color, setColor] = useState<ProjectColor>(project?.color ?? "teal");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const first = useRef<HTMLInputElement>(null);

  useEffect(() => {
    first.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) { setError("Give the project a name."); return; }
    setBusy(true); setError(null);
    try {
      const saved = project ? await updateProject(project.id, { name, description, color }) : await createProject({ name, description, color });
      onSaved(saved);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't save the project.");
      setBusy(false);
    }
  }

  return (
    <div className="dialog-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <form className="dialog" role="dialog" aria-modal="true" aria-labelledby="pd-title" onSubmit={submit} style={{ display: "grid", gap: 18 }}>
        <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
          <Monogram name={name || "P"} color={color} />
          <h2 id="pd-title" className="h2">{project ? "Edit project" : "New project"}</h2>
        </div>
        <div className="field">
          <label htmlFor="pd-name">Name</label>
          <input id="pd-name" ref={first} className="input" value={name} onChange={(e) => setName(e.target.value)} maxLength={80} placeholder="Rosa's Trattoria" />
        </div>
        <div className="field">
          <label htmlFor="pd-desc">Description <span className="faint" style={{ fontWeight: 400 }}>optional</span></label>
          <input id="pd-desc" className="input" value={description} onChange={(e) => setDescription(e.target.value)} maxLength={280} placeholder="Restaurant website and booking page" />
        </div>
        <div className="field">
          <span style={{ fontSize: 13, fontWeight: 500, color: "var(--ink)" }}>Colour</span>
          <div className="swatches" role="group" aria-label="Colour">
            {PROJECT_COLORS.map((c) => <button key={c} type="button" className={`c-${c}`} aria-pressed={c === color} aria-label={c} onClick={() => setColor(c)} />)}
          </div>
        </div>
        {error && <p className="notice red" role="alert">{error}</p>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 4 }}>
          <button type="button" className="btn ghost" onClick={onClose}>Cancel</button>
          <button className="btn primary" disabled={busy || !name.trim()}>{busy ? "Saving…" : project ? "Save changes" : "Create project"}</button>
        </div>
      </form>
    </div>
  );
}

const TYPES = ["", "E-commerce shop", "Local business", "SaaS product", "Documentation", "Blog or publication", "Portfolio"];

/** Start an audit. With `projectId` it audits into that project; with `projects` it offers a choice. */
export function AuditForm({ projectId, projects, compact = false }: { projectId?: string; projects?: Project[]; compact?: boolean }) {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [type, setType] = useState("");
  const [tasks, setTasks] = useState("");
  const [project, setProject] = useState(projectId ?? "");
  const [more, setMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const taskList = tasks.split("\n").map((t) => t.trim()).filter(Boolean);
  const target = normaliseUrl(url);

  useEffect(() => { if (!projectId && projects?.length && !project) setProject(projects[0].id); }, [projects, projectId, project]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!target) { setError("Enter a website address, like rosastrattoria.in."); return; }
    if (taskList.length > 5) { setError("Up to 5 tasks."); return; }
    setBusy(true); setError(null);
    try {
      const audit = await startAudit(target, taskList, type, projectId ?? project);
      router.push(`/audits/${audit.id}`);
    } catch (err) { setError((err as Error).message); setBusy(false); }
  }

  return (
    <form onSubmit={submit} style={{ display: "grid", gap: 16 }}>
      {!compact && <h2 className="h2">Audit a website</h2>}
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        <input className="input mono" value={url} onChange={(e) => { setUrl(e.target.value); setError(null); }} placeholder="rosastrattoria.in"
               aria-label="Website address" inputMode="url" spellCheck={false} style={{ height: 48, fontSize: 15, flex: "1 1 240px" }} />
        <button className="btn primary" style={{ height: 48, padding: "0 20px" }} disabled={busy || !url.trim()}>
          {busy ? "Starting…" : <>Run audit <ArrowRight size={16} weight="bold" /></>}
        </button>
      </div>
      {!projectId && projects && projects.length > 0 && (
        <div className="field">
          <label htmlFor="af-project">Project</label>
          <select id="af-project" className="input" value={project} onChange={(e) => setProject(e.target.value)}>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
      )}
      <p className="hint">{target ? <>Crawls up to 25 pages of <span className="mono">{new URL(target).host}</span>, then tests it with an AI agent. About 5–10 minutes.</> : "Crawls up to 25 pages, tests the site with an AI agent and asks AI assistants about it."}</p>
      <div className="acc">
        <div className={`item${more ? " open" : ""}`} style={{ borderBottom: 0, borderTop: "1px solid var(--line)" }}>
          <button type="button" className="acc-head" style={{ padding: "14px 0 2px" }} onClick={() => setMore((m) => !m)} aria-expanded={more}>
            <span className="pm" /><span className="h3" style={{ fontWeight: 500 }}>Business type and agent tasks</span><span className="small faint">optional</span>
          </button>
          <div className="acc-body"><div>
            <div className="inner" style={{ display: "grid", gap: 14, paddingTop: 12, paddingBottom: 4 }}>
              <div className="field">
                <label htmlFor="af-type">Business type</label>
                <select id="af-type" className="input" value={type} onChange={(e) => setType(e.target.value)}>
                  {TYPES.map((t) => <option key={t} value={t}>{t || "Detect automatically"}</option>)}
                </select>
              </div>
              <div className="field">
                <label htmlFor="af-tasks">Tasks for the test agent</label>
                <textarea id="af-tasks" className="input" rows={3} value={tasks} onChange={(e) => setTasks(e.target.value)} placeholder={"Book a table for 2 on Friday\nFind the opening hours on Sunday"} />
                <span className="hint">One per line, up to 5. Left empty, AgentRank suggests tasks from the site. The agent never submits forms.</span>
              </div>
            </div>
          </div></div>
        </div>
      </div>
      {error && <p className="notice red" role="alert">{error}</p>}
    </form>
  );
}

function Thumb({ src, w = 72, h = 50 }: { src: string | null; w?: number; h?: number }) {
  return src
    // eslint-disable-next-line @next/next/no-img-element
    ? <img src={src} alt="" width={w} height={h} style={{ width: w, height: h, objectFit: "cover", objectPosition: "top", borderRadius: 6, border: "1px solid var(--line)", flex: "none" }} />
    : <span style={{ width: w, height: h, borderRadius: 6, background: "var(--bone)", border: "1px solid var(--line)", flex: "none" }} />;
}

/** Audits as document rows: thumbnail, site, project, score bar, verdict. */
export function AuditRows({ audits, showProject = false }: { audits: Audit[]; showProject?: boolean }) {
  const router = useRouter();
  return (
    <ul className="list">
      {audits.map((a) => (
        <li key={a.id}>
          <div className="row interactive" role="link" tabIndex={0} onClick={() => router.push(`/audits/${a.id}`)}
               onKeyDown={(e) => { if (e.key === "Enter") router.push(`/audits/${a.id}`); }}>
            <Thumb src={a.screenshot_url} />
            <div className="grow">
              <p className="title mono">{host(a.site_url)}</p>
              <p className="sub">
                {showProject && a.project_name ? `${a.project_name} · ` : ""}{siteType(a.site_type)} · {when(a.started_at)}
                {a.status === "done" ? ` · ${duration(a.started_at, a.finished_at)}` : ` · ${a.page_count} pages so far`}
              </p>
            </div>
            <div className="hide-sm" style={{ width: 150 }}>{a.status === "done" ? <Meter value={a.score_summary.agent_ready} tone="blue" /> : null}</div>
            <span className="figure hide-sm" style={{ fontSize: 26, width: 44, textAlign: "right" }}>{a.status === "done" ? score(a.score_summary.agent_ready) : ""}</span>
            <span style={{ width: 128, display: "flex", justifyContent: "flex-end" }}>
              {a.status === "done" && a.priority ? <PriorityTag priority={a.priority} /> : <StatusTag status={a.status} />}
            </span>
            <CaretRight className="chev" size={16} weight="bold" />
          </div>
        </li>
      ))}
    </ul>
  );
}

export function ProjectCard({ project }: { project: Project }) {
  const router = useRouter();
  const done = project.sites.filter((s) => s.status === "done");
  return (
    <article className={`card lift project-card c-${project.color}`} role="link" tabIndex={0}
             onClick={() => router.push(`/projects/${project.id}`)} onKeyDown={(e) => { if (e.key === "Enter") router.push(`/projects/${project.id}`); }}>
      <div style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
        <Monogram name={project.name} color={project.color} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <h3 className="h2" style={{ fontSize: 22, overflowWrap: "anywhere" }}>{project.name}</h3>
          <p className="small muted" style={{ marginTop: 2, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
            {project.description || `${project.sites.length} ${project.sites.length === 1 ? "site" : "sites"}`}
          </p>
        </div>
        {project.running > 0 && <span className="tag blue"><span className="pulse" />{project.running} running</span>}
      </div>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 12 }}>
        <div>
          <p className="small muted">Average Agent-Ready</p>
          <p className="figure" style={{ fontSize: 40, marginTop: 4, color: project.avg_agent_ready != null ? "var(--c)" : undefined }}>
            {project.avg_agent_ready != null ? <CountUp value={Math.round(project.avg_agent_ready)} /> : <span className="faint" style={{ fontSize: 20 }}>No audits yet</span>}
          </p>
        </div>
        <p className="small muted" style={{ textAlign: "right" }}>
          {project.sites.length} {project.sites.length === 1 ? "site" : "sites"} · {project.audit_count} {project.audit_count === 1 ? "audit" : "audits"}<br />
          {project.last_audit_at ? `Last audit ${when(project.last_audit_at)}` : "Not audited yet"}
        </p>
      </div>
      {project.avg_agent_ready != null && <Meter value={project.avg_agent_ready} tone={project.color} />}
      <div className="thumbs" aria-hidden="true">
        {done.slice(0, 5).map((s) => s.screenshot_url
          // eslint-disable-next-line @next/next/no-img-element
          ? <img key={s.site_id} src={s.screenshot_url} alt="" /> : <span key={s.site_id} />)}
      </div>
    </article>
  );
}
