"use client";

import { CaretRight, PencilSimple, Trash } from "@phosphor-icons/react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { AuditForm, AuditRows, Monogram, ProjectDialog } from "@/components/projects";
import { CountUp, Meter, Reveal, StatusTag, useReveal } from "@/components/ui";
import { api, ApiError, Audit, deleteProject, getProject, host, Project, score, when } from "@/lib/api";

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const ref = useReveal<HTMLElement>();
  const [project, setProject] = useState<Project | null>(null);
  const [audits, setAudits] = useState<Audit[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const load = useCallback(async () => {
    try {
      const [p, a] = await Promise.all([getProject(id), api<Audit[]>(`/audits?project_id=${id}`)]);
      setProject(p); setAudits(a); setError(null);
      return p.running > 0;
    } catch (e) { setError((e as Error).message); return false; }
  }, [id]);

  useEffect(() => {
    let alive = true;
    let t: ReturnType<typeof setTimeout>;
    const tick = async () => { const running = await load(); if (alive) t = setTimeout(tick, running ? 4000 : 15000); };
    tick();
    return () => { alive = false; clearTimeout(t); };
  }, [load]);

  async function remove() {
    try { await deleteProject(id); router.push("/"); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Couldn't delete the project."); setConfirmDelete(false); }
  }

  if (error && !project) return <main className="page"><h1 className="h1">Project</h1><p className="notice red" style={{ marginTop: 24 }}>{error}</p></main>;
  if (!project) return <main className="page"><span className="skeleton" style={{ width: 280, height: 40 }} /></main>;

  const done = project.sites.filter((s) => s.status === "done" && s.agent_ready != null);
  const best = done.slice().sort((a, b) => (b.agent_ready ?? 0) - (a.agent_ready ?? 0))[0];
  const worst = done.slice().sort((a, b) => (a.agent_ready ?? 0) - (b.agent_ready ?? 0))[0];

  return (
    <main className="page" ref={ref}>
      <Reveal><p className="small faint"><Link href="/" className="link" style={{ color: "var(--faint)" }}>Projects</Link> / {project.name}</p></Reveal>
      <Reveal className="page-head" i={1} style={{ marginTop: 20 }}>
        <div style={{ display: "flex", gap: 18, alignItems: "center", minWidth: 0 }}>
          <Monogram name={project.name} color={project.color} size="lg" />
          <div style={{ minWidth: 0 }}>
            <h1 className="h1" style={{ overflowWrap: "anywhere" }}>{project.name}</h1>
            <p className="muted" style={{ marginTop: 6 }}>{project.description || "No description"} · created {when(project.created_at)}</p>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn" onClick={() => setEditing(true)}><PencilSimple size={16} weight="bold" />Edit</button>
          {project.audit_count === 0 && <button className="btn ghost" onClick={() => setConfirmDelete(true)} aria-label="Delete project"><Trash size={16} weight="bold" /></button>}
        </div>
      </Reveal>
      {error && <p className="notice" style={{ marginBottom: 24 }}>{error}</p>}
      {confirmDelete && (
        <div className="notice red" role="alert" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, marginBottom: 24 }}>
          <span>Delete the empty project “{project.name}”? This can&apos;t be undone.</span>
          <span style={{ display: "flex", gap: 8 }}><button className="btn sm" onClick={() => setConfirmDelete(false)}>Keep it</button><button className="btn sm primary" onClick={remove}>Delete project</button></span>
        </div>
      )}

      <div className="bento">
        <Reveal className={`card span-7 c-${project.color}`} i={2} style={{ borderTop: "3px solid var(--c)" }}>
          <AuditForm projectId={project.id} />
        </Reveal>
        <Reveal className={`card tint c-${project.color} span-5`} i={3}>
          <p className="small">Average Agent-Ready across {done.length} {done.length === 1 ? "site" : "sites"}</p>
          <p className="figure" style={{ fontSize: 64, marginTop: 8 }}>{project.avg_agent_ready != null ? <CountUp value={Math.round(project.avg_agent_ready)} /> : <span style={{ fontSize: 24 }}>No finished audits yet</span>}</p>
          {project.avg_agent_ready != null && <div style={{ marginTop: 14 }}><Meter value={project.avg_agent_ready} tone={project.color} /></div>}
          <dl style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 24 }}>
            <div><dt className="small">Audits run</dt><dd className="figure" style={{ fontSize: 28, marginTop: 2 }}>{project.audit_count}</dd></div>
            <div><dt className="small">Running now</dt><dd className="figure" style={{ fontSize: 28, marginTop: 2 }}>{project.running}</dd></div>
            {best && done.length > 1 && <div><dt className="small">Most agent-ready</dt><dd className="mono small" style={{ marginTop: 4, color: "var(--ink)" }}>{host(best.url)} · {score(best.agent_ready)}</dd></div>}
            {worst && done.length > 1 && <div><dt className="small">Needs most work</dt><dd className="mono small" style={{ marginTop: 4, color: "var(--ink)" }}>{host(worst.url)} · {score(worst.agent_ready)}</dd></div>}
          </dl>
        </Reveal>
      </div>

      <section className="section" aria-labelledby="sites-h">
        <Reveal className="section-head"><h2 id="sites-h" className="h2">Websites</h2><span className="small faint">Latest audit of each site</span></Reveal>
        {project.sites.length === 0 ? <Reveal><p className="empty">No websites yet. Paste an address above to audit the first one.</p></Reveal> : (
          <div className="bento">
            {project.sites.map((s, i) => (
              <Reveal key={s.site_id} i={Math.min(i, 6)} className="span-4">
                <Link href={`/audits/${s.latest_audit_id}`} className="card lift" style={{ display: "block", padding: 0, overflow: "hidden" }}>
                  {s.screenshot_url
                    // eslint-disable-next-line @next/next/no-img-element
                    ? <img src={s.screenshot_url} alt="" style={{ width: "100%", aspectRatio: "16 / 9", objectFit: "cover", objectPosition: "top", borderBottom: "1px solid var(--line)" }} />
                    : <div style={{ aspectRatio: "16 / 9", background: "var(--bone)", borderBottom: "1px solid var(--line)" }} />}
                  <div style={{ padding: "16px 20px 20px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                      <p className="mono" style={{ color: "var(--ink)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{host(s.url)}</p>
                      {s.status === "done" ? <span className="figure" style={{ fontSize: 28 }}>{score(s.agent_ready)}</span> : <StatusTag status={s.status} />}
                    </div>
                    {s.status === "done" && <div style={{ marginTop: 10 }}><Meter value={s.agent_ready} tone={project.color} /></div>}
                    <p className="small muted" style={{ marginTop: 10, display: "flex", justifyContent: "space-between" }}>
                      <span>{when(s.started_at)} · SEO {score(s.seo)}</span><CaretRight size={14} weight="bold" />
                    </p>
                  </div>
                </Link>
              </Reveal>
            ))}
          </div>
        )}
      </section>

      <section className="section" aria-labelledby="hist-h">
        <Reveal className="section-head"><h2 id="hist-h" className="h2">Audit history</h2><span className="small faint">{project.audit_count} in this project</span></Reveal>
        {audits && audits.length > 0 ? <AuditRows audits={audits} /> : <Reveal><p className="empty">Every audit you run in this project will be listed here.</p></Reveal>}
      </section>

      {editing && <ProjectDialog project={project} onClose={() => setEditing(false)} onSaved={(p) => { setProject(p); setEditing(false); }} />}
    </main>
  );
}
