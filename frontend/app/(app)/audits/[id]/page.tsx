"use client";

import { ArrowClockwise, ArrowSquareOut, Check as CheckIcon } from "@phosphor-icons/react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { AgentsTab, ChecksTab, FixesTab, OverviewTab, PagesTab, VisibilityTab } from "@/components/AuditTabs";
import { PriorityTag, Reveal, StatusTag, useReveal } from "@/components/ui";
import {
  AgentRun, api, Audit, duration, Finding, Fix, host, PageRow, Score, siteType, stages, startAudit, VisibilityRow, when,
} from "@/lib/api";

export interface AuditData {
  audit: Audit; scores: Score[]; findings: Finding[]; fixes: Fix[]; runs: AgentRun[];
  visibility: VisibilityRow[]; pages: PageRow[]; history: Audit[];
}

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "fixes", label: "Fixes" },
  { id: "agents", label: "Agent replays" },
  { id: "visibility", label: "AI visibility" },
  { id: "checks", label: "Checks" },
  { id: "pages", label: "Site map" },
] as const;
type TabId = (typeof TABS)[number]["id"];

export default function AuditPage() {
  return <Suspense><AuditScreen /></Suspense>;
}

function AuditScreen() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const ref = useReveal<HTMLElement>();
  const tab = (TABS.find((t) => t.id === search.get("tab"))?.id ?? "overview") as TabId;
  const [data, setData] = useState<AuditData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rerunning, setRerunning] = useState(false);

  const load = useCallback(async () => {
    try {
      const audit = await api<Audit>(`/audits/${id}`);
      const [scores, findings, fixes, runs, visibility, pages, history] = await Promise.all([
        api<Score[]>(`/audits/${id}/scores`), api<Finding[]>(`/audits/${id}/findings`), api<Fix[]>(`/audits/${id}/fixes`),
        api<AgentRun[]>(`/audits/${id}/agent-tests`), api<VisibilityRow[]>(`/audits/${id}/visibility`),
        api<PageRow[]>(`/audits/${id}/pages`), api<Audit[]>(`/audits?site_id=${audit.site_id}`),
      ]);
      setData({ audit, scores, findings, fixes, runs, visibility, pages, history });
      setError(null);
      return audit.status;
    } catch (e) {
      setError((e as Error).message);
      return "failed";
    }
  }, [id]);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      const status = await load();
      if (alive && (status === "running" || status === "queued")) timer = setTimeout(tick, 4000);
    };
    tick();
    return () => { alive = false; clearTimeout(timer); };
  }, [load]);

  async function rerun() {
    if (!data) return;
    setRerunning(true);
    try {
      const next = await startAudit(data.audit.site_url, data.audit.tasks, data.audit.business_type ?? undefined, data.audit.project_id);
      router.push(`/audits/${next.id}`);
    } catch (e) { setError((e as Error).message); setRerunning(false); }
  }

  if (error && !data) {
    return (
      <main className="page">
        <h1 className="h1">Audit</h1>
        <p className="notice red" style={{ marginTop: 24 }}>{error} <button className="link" onClick={() => load()}>Try again</button></p>
      </main>
    );
  }
  if (!data) return <main className="page"><span className="skeleton" style={{ width: 320, height: 40 }} /><p style={{ marginTop: 16 }}><span className="skeleton" style={{ width: 480, height: 14 }} /></p></main>;

  const { audit } = data;
  const running = audit.status === "running" || audit.status === "queued";
  const counts: Partial<Record<TabId, number>> = { fixes: data.fixes.length, agents: data.runs.length, visibility: data.visibility.length, pages: data.pages.length };
  const brand = audit.classification.brand_name;

  return (
    <main className="page" ref={ref}>
      <Reveal>
        <p className="small faint">
          <Link href="/" className="link" style={{ color: "var(--faint)" }}>Projects</Link>
          {audit.project_id && <> / <Link href={`/projects/${audit.project_id}`} className="link" style={{ color: "var(--faint)" }}>{audit.project_name}</Link></>}
          {" / "}<span className="mono">{host(audit.site_url)}</span>
        </p>
      </Reveal>
      <Reveal className="page-head" i={1} style={{ marginTop: 20, marginBottom: 0 }}>
        <div style={{ display: "flex", gap: 24, alignItems: "center", minWidth: 0 }}>
          {audit.screenshot_url
            // eslint-disable-next-line @next/next/no-img-element
            ? <img src={audit.screenshot_url} alt={`Homepage of ${host(audit.site_url)}`} className="hide-sm" style={{ width: 168, height: 118, objectFit: "cover", objectPosition: "top", borderRadius: 10, border: "1px solid var(--line)", flex: "none" }} />
            : <span className="hide-sm" style={{ width: 168, height: 118, borderRadius: 10, background: "var(--bone)", border: "1px solid var(--line)", flex: "none" }} />}
          <div style={{ minWidth: 0 }}>
            <h1 className="h1" style={{ overflowWrap: "anywhere" }}>{brand || host(audit.site_url)}</h1>
            <p className="muted" style={{ marginTop: 8 }}>
              <span className="mono">{host(audit.site_url)}</span> · {siteType(audit.site_type)} · {when(audit.started_at)}
              {audit.finished_at ? ` · ${duration(audit.started_at, audit.finished_at)}` : ""} · {audit.page_count} pages
            </p>
            <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
              <StatusTag status={audit.status} />
              {audit.verdict.priority && <PriorityTag priority={audit.verdict.priority} />}
            </div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <a className="btn" href={audit.site_url} target="_blank" rel="noreferrer"><ArrowSquareOut size={16} weight="bold" />Open site</a>
          <button className="btn primary" onClick={rerun} disabled={running || rerunning}><ArrowClockwise size={16} weight="bold" />{rerunning ? "Starting…" : "Re-run audit"}</button>
        </div>
      </Reveal>

      {running && <Stepper audit={audit} />}
      {audit.status === "failed" && <p className="notice red" style={{ marginTop: 24 }}>The audit stopped: {audit.error ?? "unknown error"}. Results gathered before it stopped are shown below.</p>}

      <nav className="tabs" role="tablist" aria-label="Audit sections">
        {TABS.map((t) => (
          <Link key={t.id} role="tab" scroll={false} aria-selected={tab === t.id}
                href={t.id === "overview" ? `/audits/${id}` : `/audits/${id}?tab=${t.id}`}>
            {t.label}{counts[t.id] ? <span className="count">{counts[t.id]}</span> : null}
          </Link>
        ))}
      </nav>

      {error && <p className="notice" style={{ marginBottom: 24 }}>Live updates paused: {error}</p>}
      {tab === "overview" && <OverviewTab data={data} />}
      {tab === "fixes" && <FixesTab data={data} />}
      {tab === "agents" && <AgentsTab data={data} />}
      {tab === "visibility" && <VisibilityTab data={data} />}
      {tab === "checks" && <ChecksTab data={data} />}
      {tab === "pages" && <PagesTab data={data} />}
    </main>
  );
}

/** Live pipeline progress: done stages ticked, the current one pulsing. */
function Stepper({ audit }: { audit: Audit }) {
  const s = stages(audit);
  const current = s.findIndex((x) => !x.done);
  return (
    <div className="card flat" style={{ marginTop: 28, padding: "18px 24px" }} aria-live="polite">
      <ol style={{ display: "grid", gridTemplateColumns: `repeat(${s.length}, minmax(0, 1fr))`, gap: 12 }}>
        {s.map((x, i) => (
          <li key={x.label} style={{ display: "grid", gap: 10 }}>
            <div style={{ height: 3, borderRadius: 2, background: x.done ? "var(--ink)" : i === current ? "var(--data-soft)" : "#efeeea", transition: "background-color 400ms ease" }} />
            <span className="small" style={{ display: "flex", alignItems: "center", gap: 6, color: x.done || i === current ? "var(--ink)" : "var(--faint)" }}>
              {x.done ? <CheckIcon size={13} weight="bold" /> : i === current ? <span className="tag blue" style={{ height: 8, width: 8, padding: 0 }}><span className="pulse" /></span> : null}
              <span className="hide-sm">{x.label}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="small muted" style={{ marginTop: 12 }}>{current >= 0 ? `${s[current].label}… Results appear as each stage finishes.` : "Finishing…"}</p>
    </div>
  );
}
