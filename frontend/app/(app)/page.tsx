"use client";

import { Plus } from "@phosphor-icons/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useUser } from "@/components/AppShell";
import { ProjectCard, ProjectDialog } from "@/components/projects";
import { CountUp, Reveal, useReveal } from "@/components/ui";
import { listProjects, Project } from "@/lib/api";

export default function ProjectsPage() {
  const router = useRouter();
  const user = useUser();
  const ref = useReveal<HTMLElement>();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    let alive = true;
    const load = () => listProjects().then((p) => { if (alive) { setProjects(p); setError(null); } }).catch((e) => alive && setError(e.message));
    load();
    const t = setInterval(load, 8000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const sites = projects?.reduce((n, p) => n + p.sites.length, 0) ?? 0;
  const audits = projects?.reduce((n, p) => n + p.audit_count, 0) ?? 0;
  const running = projects?.reduce((n, p) => n + p.running, 0) ?? 0;
  const scored = projects?.flatMap((p) => p.sites.filter((s) => s.status === "done" && s.agent_ready != null).map((s) => s.agent_ready!)) ?? [];
  const avg = scored.length ? scored.reduce((a, b) => a + b, 0) / scored.length : null;

  return (
    <main className="page" ref={ref}>
      <Reveal className="page-head">
        <div>
          <p className="small muted">{user ? `Welcome, ${user.name.split(" ")[0]}` : " "}</p>
          <h1 className="h1" style={{ marginTop: 6 }}>Projects</h1>
          <p className="lede" style={{ marginTop: 10 }}>Group the websites you look after, then audit each one for search and for AI agents.</p>
        </div>
        <button className="btn primary" onClick={() => setCreating(true)}><Plus size={16} weight="bold" />New project</button>
      </Reveal>

      <div className="bento" style={{ marginBottom: 16 }}>
        {[
          { label: "Projects", value: projects?.length ?? null, tone: "gray" },
          { label: "Websites", value: projects ? sites : null, tone: "blue" },
          { label: "Audits run", value: projects ? audits : null, tone: "teal", note: running ? `${running} running now` : undefined },
          { label: "Average Agent-Ready", value: avg, tone: "green", note: avg == null ? "No finished audits yet" : "Latest audit per site" },
        ].map((s, i) => (
          <Reveal key={s.label} i={i} className={`card tight tint c-${s.tone} span-3`}>
            <p className="small">{s.label}</p>
            <p className="figure" style={{ fontSize: 40, marginTop: 6 }}>
              {s.value == null ? (projects ? <span style={{ fontSize: 22 }}>—</span> : <span className="skeleton" style={{ width: 40, height: 34 }} />) : <CountUp value={Math.round(s.value)} />}
            </p>
            {s.note && <p className="small" style={{ marginTop: 4 }}>{s.note}</p>}
          </Reveal>
        ))}
      </div>

      {error && <p className="notice red" style={{ marginTop: 24 }}>{error}</p>}
      <div className="bento" style={{ marginTop: 32 }}>
        {projects === null && !error && [0, 1, 2].map((i) => <div key={i} className="card span-4" style={{ minHeight: 248 }}><span className="skeleton" style={{ width: 160, height: 22 }} /></div>)}
        {projects?.map((p, i) => <Reveal key={p.id} i={Math.min(i, 6)} className="span-4"><ProjectCard project={p} /></Reveal>)}
        {projects && (
          <Reveal i={Math.min(projects.length, 6)} className="span-4">
            <button className="new-card" style={{ width: "100%" }} onClick={() => setCreating(true)}>
              <span style={{ display: "grid", justifyItems: "center", gap: 10 }}>
                <Plus size={22} weight="bold" />
                <span className="h3" style={{ color: "inherit" }}>New project</span>
                <span className="small">A client, a brand, or a group of sites</span>
              </span>
            </button>
          </Reveal>
        )}
      </div>

      {creating && <ProjectDialog onClose={() => setCreating(false)} onSaved={(p) => router.push(`/projects/${p.id}`)} />}
    </main>
  );
}
