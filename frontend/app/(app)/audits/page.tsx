"use client";

import { useEffect, useState } from "react";
import { AuditForm, AuditRows } from "@/components/projects";
import { Reveal, useReveal } from "@/components/ui";
import { api, Audit, listProjects, Project } from "@/lib/api";

const MEASURES = [
  { key: "seo", name: "Classic SEO", tone: "blue", what: "Titles, descriptions, headings, canonicals, broken links, sitemap coverage, indexability and mobile speed from PageSpeed.", scope: "14 checks" },
  { key: "readability", name: "Agent readability", tone: "teal", what: "Whether AI crawlers are allowed, llms.txt, structured data, how much content exists without JavaScript, and whether prices, hours and contact details can be extracted.", scope: "8 checks" },
  { key: "actionability", name: "Actionability", tone: "yellow", what: "Labelled forms, CAPTCHAs, login and bot walls, content locked in images or canvas, and machine interfaces such as OpenAPI or MCP.", scope: "8 checks" },
  { key: "task_success", name: "Task success", tone: "rose", what: "A browser agent tries the site's key tasks twice each, with a screenshot of every step. It may add to a cart but never submits a booking, order or form.", scope: "2 tasks, 2 runs each" },
  { key: "visibility", name: "AI visibility", tone: "green", what: "Questions customers ask, answered by AI models with web search: is the site named, linked, or are other sites recommended instead?", scope: "4 to 6 questions, 2 models" },
];

export default function AllAuditsPage() {
  const ref = useReveal<HTMLElement>();
  const [audits, setAudits] = useState<Audit[] | null>(null);
  const [projects, setProjects] = useState<Project[] | undefined>();
  const [filter, setFilter] = useState<string>("all");
  const [open, setOpen] = useState<string | null>(null);
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => api<Audit[]>("/audits").then((a) => { if (alive) { setAudits(a); setError(null); } }).catch((e) => alive && setError(e.message));
    load();
    listProjects().then(setProjects).catch(() => {});
    api<{ base_weights: Record<string, number> }>("/rubric").then((r) => setWeights(r.base_weights)).catch(() => {});
    const t = setInterval(load, 6000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const shown = audits?.filter((a) => filter === "all" || a.project_id === filter) ?? [];

  return (
    <main className="page" ref={ref}>
      <Reveal className="page-head">
        <div>
          <h1 className="h1">All audits</h1>
          <p className="lede" style={{ marginTop: 10 }}>Every audit across your projects, newest first.</p>
        </div>
      </Reveal>

      <div className="bento">
        <Reveal className="card span-7" i={1}><AuditForm projects={projects} /></Reveal>
        <Reveal className="card flat span-5" i={2}>
          <h2 className="h3" style={{ marginBottom: 6 }}>What an audit measures</h2>
          <div className="acc">
            {MEASURES.map((m) => (
              <div key={m.key} className={`item${open === m.key ? " open" : ""}`}>
                <button className="acc-head" style={{ padding: "13px 0" }} onClick={() => setOpen(open === m.key ? null : m.key)} aria-expanded={open === m.key}>
                  <span className={`swatch-dot c-${m.tone}`} />
                  <span style={{ flex: 1, color: "var(--ink)", fontSize: 14 }}>{m.name}</span>
                  <span className="small faint num">{m.key === "seo" ? "beside" : weights[m.key] != null ? `${Math.round(weights[m.key] * 100)}%` : ""}</span>
                  <span className="pm" style={{ width: 10, height: 10 }} />
                </button>
                <div className="acc-body"><div><p className="small muted" style={{ padding: "0 0 14px 20px" }}>{m.what} <span className="faint">({m.scope})</span></p></div></div>
              </div>
            ))}
          </div>
        </Reveal>
      </div>

      <section className="section" aria-labelledby="all-h">
        <Reveal className="section-head" style={{ flexWrap: "wrap" }}>
          <h2 id="all-h" className="h2">Audits</h2>
          {projects && projects.length > 1 && (
            <div className="segmented" role="group" aria-label="Filter by project">
              <button aria-pressed={filter === "all"} onClick={() => setFilter("all")}>All</button>
              {projects.map((p) => (
                <button key={p.id} aria-pressed={filter === p.id} onClick={() => setFilter(p.id)} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                  <span className={`swatch-dot c-${p.color}`} />{p.name}
                </button>
              ))}
            </div>
          )}
        </Reveal>
        {error && <p className="notice red">{error}</p>}
        {audits === null && !error && <p><span className="skeleton" style={{ width: "100%", height: 50 }} /></p>}
        {audits && shown.length === 0 && <Reveal><p className="empty">No audits here yet.</p></Reveal>}
        {shown.length > 0 && <AuditRows audits={shown} showProject />}
      </section>
    </main>
  );
}
