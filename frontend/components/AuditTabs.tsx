"use client";

import { ArrowLeft, ArrowRight, CaretRight, CheckCircle, Copy, X, XCircle } from "@phosphor-icons/react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { AuditData } from "@/app/(app)/audits/[id]/page";
import { BarList, Gauge, Quadrant } from "@/components/charts";
import { ratioColor, type MapNode } from "@/components/SiteMap3D";
import { CountUp, Meter, PriorityTag, Reveal, SeverityTag } from "@/components/ui";
import { AgentRun, api, Check, Fix, host, MODULES, moduleLabel, pct, score, shortModel, VisibilityRow, when } from "@/lib/api";

const SiteMap3D = dynamic(() => import("@/components/SiteMap3D"), {
  ssr: false, loading: () => <div className="skeleton" style={{ width: "100%", height: "100%" }} />,
});

const href = (id: string, tab: string, extra = "") => `/audits/${id}?tab=${tab}${extra}`;
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

function Empty({ children }: { children: React.ReactNode }) {
  return <Reveal><p className="empty">{children}</p></Reveal>;
}

function Ok({ ok, label }: { ok: boolean; label?: string }) {
  return ok
    ? <CheckCircle size={18} weight="fill" color="var(--green)" aria-label={label ?? "Yes"} />
    : <XCircle size={18} weight="fill" color="var(--red)" aria-label={label ?? "No"} />;
}

// =====================================================================================================
// Overview
// =====================================================================================================

export function OverviewTab({ data }: { data: AuditData }) {
  const router = useRouter();
  const { audit, scores, findings, fixes, runs, history } = data;
  const s = audit.score_summary;
  const v = audit.verdict;
  const projected = v.projection?.projected ?? {};
  const fixed = new Set(fixes.flatMap((f) => f.check_ids));
  const checks = Object.fromEntries(scores.map((sc) => [sc.category, sc.details.checks ?? []]));
  const top = findings.slice().sort((a, b) => (b.impact_estimate ?? 0) - (a.impact_estimate ?? 0)).slice(0, 5);
  const now = s.seo != null && s.agent_ready != null ? { x: s.seo, y: s.agent_ready } : null;
  const after = projected.seo != null && projected.agent_ready != null ? { x: projected.seo, y: projected.agent_ready } : null;
  const past = history.filter((h) => h.id !== audit.id && h.status === "done" && h.score_summary.seo != null && h.score_summary.agent_ready != null)
    .map((h) => ({ x: h.score_summary.seo!, y: h.score_summary.agent_ready!, label: `Audit of ${when(h.started_at)}` }));
  const vis = audit.visibility;
  const gain = s.agent_ready != null && projected.agent_ready != null ? projected.agent_ready - s.agent_ready : 0;

  return (
    <div className="bento">
      <Reveal className="card span-7" i={0}>
        <div className="card-head"><h2 className="h3">Does this site need agent optimisation?</h2>{v.priority && <PriorityTag priority={v.priority} />}</div>
        <div style={{ display: "flex", gap: 32, alignItems: "flex-end", flexWrap: "wrap" }}>
          <div style={{ position: "relative", width: 240 }}>
            <Gauge value={s.agent_ready ?? null} after={projected.agent_ready ?? null} />
            <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, textAlign: "center" }}>
              <div className="figure" style={{ fontSize: 64 }}>{s.agent_ready != null ? <CountUp value={Math.round(s.agent_ready)} /> : <span className="faint" style={{ fontSize: 28 }}>Scoring…</span>}</div>
            </div>
          </div>
          <div style={{ flex: 1, minWidth: 200, paddingBottom: 6 }}>
            <p className="small muted">Agent-Ready score, out of 100</p>
            {gain > 0.5 ? (
              <p style={{ marginTop: 6 }}>About <span className="figure" style={{ fontSize: 28, color: "var(--data)" }}>{score(projected.agent_ready)}</span> after the {plural(fixes.length, "generated fix", "generated fixes")}.</p>
            ) : <p className="small muted" style={{ marginTop: 6 }}>{audit.status === "done" ? "No score gain is estimated from the generated fixes." : "The estimate after fixes comes at the end."}</p>}
          </div>
        </div>
        {v.headline ? (
          <>
            <p className="h2" style={{ marginTop: 28, fontSize: 22 }}>{v.headline}</p>
            <p style={{ marginTop: 10, maxWidth: "64ch" }}>{v.explanation}</p>
            <ul className="list" style={{ marginTop: 18, borderTop: "1px solid var(--line)" }}>
              {v.factors?.map((f) => (
                <li key={f.factor} className="row" style={{ padding: "12px 0", alignItems: "flex-start" }}>
                  <span className="mono faint" style={{ width: 24 }}>+{f.points}</span><span className="small" style={{ flex: 1 }}>{f.why}</span>
                </li>
              ))}
            </ul>
          </>
        ) : <p className="muted" style={{ marginTop: 28 }}>{audit.status === "failed" ? "No verdict: the audit stopped before scoring finished." : "The verdict is written once agent tests and AI visibility finish."}</p>}
      </Reveal>

      <Reveal className="card span-5" i={1}>
        <div className="card-head"><h2 className="h3">Search and agents, side by side</h2></div>
        <Quadrant now={now} after={after} history={past} />
        <p className="small muted" style={{ marginTop: 12 }}>Classic SEO across, Agent-Ready up. Hover a point or an area. The open circle is the estimate after fixes.</p>
        {now && (
          <div style={{ marginTop: 20, paddingTop: 18, borderTop: "1px solid var(--line)" }}>
            <p className="small muted">Where this site sits</p>
            <p className="h2" style={{ fontSize: 20, marginTop: 4 }}>{zoneOf(now.x, now.y)}</p>
            {after && zoneOf(after.x, after.y) !== zoneOf(now.x, now.y) && <p className="small" style={{ marginTop: 4 }}>After the fixes: <span style={{ color: "var(--data)" }}>{zoneOf(after.x, after.y)}</span></p>}
          </div>
        )}
      </Reveal>

      <Reveal className="card span-12" i={2} style={{ padding: 0 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
          {MODULES.map((m, i) => {
            const value = s[m.key];
            const list = checks[m.key] ?? [];
            const needs = list.filter((c) => c.status === "fail" || c.status === "partial").length;
            let note = list.length ? `${needs} of ${list.filter((c) => c.status !== "na").length} checks need work` : "";
            if (m.key === "task_success") note = runs.length ? `${runs.filter((r) => r.success).length} of ${plural(runs.length, "agent run")} succeeded` : "";
            if (m.key === "visibility") note = vis.answers ? `Named in ${pct(vis.unbranded_mention_rate)} of discovery answers` : "";
            return (
              <button key={m.key} onClick={() => router.push(href(audit.id, "checks", `&m=${m.key}`), { scroll: false })}
                      style={{ textAlign: "left", padding: "24px 24px 22px", border: 0, borderLeft: i ? "1px solid var(--line)" : 0, background: "none", cursor: "pointer" }}
                      className="module-cell">
                <p className="small muted" style={{ display: "flex", alignItems: "center", gap: 8 }}><span className={`swatch-dot c-${m.tone}`} />{m.label}</p>
                <p className="figure" style={{ fontSize: 44, marginTop: 8 }}>
                  {value != null ? <><CountUp value={Math.round(value)} /><span className="faint" style={{ fontSize: 18 }}>{m.key === "task_success" ? "%" : ""}</span></>
                    : value === undefined && audit.status !== "done" && audit.status !== "failed" ? <span className="skeleton" style={{ width: 56, height: 40 }} />
                    : <span className="faint" style={{ fontSize: 22 }}>—</span>}
                </p>
                <div style={{ marginTop: 14 }}><Meter value={value ?? 0} after={projected[m.key] ?? null} tone={m.tone} /></div>
                <p className="small muted" style={{ marginTop: 10, minHeight: 40 }}>{note || (value === undefined ? "Waiting for this stage" : "Not measured")}</p>
              </button>
            );
          })}
        </div>
      </Reveal>

      <Reveal className="card span-7" i={3}>
        <div className="card-head"><h2 className="h3">Fix first</h2><span className="small faint">Points gained in each module</span></div>
        {findings.length === 0 ? <p className="empty">{audit.status === "done" ? "Nothing to fix: every check passed." : "Findings appear when the checks finish."}</p> : (
          <ul className="list">
            {top.map((f) => {
              const has = f.evidence.check_id && fixed.has(f.evidence.check_id);
              return (
                <li key={f.id}>
                  <div className="row interactive" role="link" tabIndex={0}
                       onClick={() => router.push(has ? href(audit.id, "fixes", `&open=${f.evidence.check_id}`) : href(audit.id, "checks", `&m=${f.category}`), { scroll: false })}
                       onKeyDown={(e) => e.key === "Enter" && (e.currentTarget as HTMLElement).click()}>
                    <span className="hide-sm"><SeverityTag severity={f.severity} /></span>
                    <div className="grow"><p className="title">{f.title}</p><p className="sub">{moduleLabel(f.category)} · {has ? "Fix ready to copy" : "Needs a manual change"}</p></div>
                    <span className="figure" style={{ fontSize: 22, color: "var(--data)" }}>+{score(f.impact_estimate)}</span>
                    <CaretRight className="chev" size={16} weight="bold" />
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        {findings.length > top.length && <p style={{ marginTop: 14 }}><Link className="link small" href={href(audit.id, "checks")}>All {findings.length} findings</Link></p>}
      </Reveal>

      <div className="span-5" style={{ display: "grid", gap: 16, alignContent: "start" }}>
        <Reveal className="card" i={4}>
          <div className="card-head"><h2 className="h3">Agent replays</h2>{runs.length > 0 && <Link className="link small" href={href(audit.id, "agents")}>Watch</Link>}</div>
          {runs.length === 0 ? <p className="empty">{audit.status === "done" ? "No agent tests ran for this audit." : "Agent tests run after the checks."}</p> : (
            <ul className="list">
              {runs.slice(0, 4).map((r) => (
                <li key={r.id}>
                  <Link className="row interactive" href={href(audit.id, "agents", `&run=${r.id}`)} scroll={false}>
                    {r.screenshots[r.screenshots.length - 1]
                      // eslint-disable-next-line @next/next/no-img-element
                      ? <img src={r.screenshots[r.screenshots.length - 1]} alt="" style={{ width: 52, height: 36, objectFit: "cover", objectPosition: "top", borderRadius: 4, border: "1px solid var(--line)", flex: "none" }} />
                      : null}
                    <div className="grow"><p className="title small" style={{ fontSize: 14 }}>{r.task}</p><p className="sub">Run {r.run_no} · {plural(r.steps.length, "step")} · {r.seconds ?? "—"} s</p></div>
                    <Ok ok={r.success} label={r.success ? "Succeeded" : "Failed"} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Reveal>
        <Reveal className="card" i={5}>
          <div className="card-head"><h2 className="h3">Who AI assistants recommend</h2>{vis.answers ? <Link className="link small" href={href(audit.id, "visibility")}>Answers</Link> : null}</div>
          {!vis.answers ? <p className="empty">{audit.status === "done" ? "AI visibility was not measured." : "AI visibility runs after the agent tests."}</p>
            : vis.top_competitors?.length ? <BarList rows={vis.top_competitors.slice(0, 4).map((c) => ({ label: c.domain, value: c.answers }))} unit={(n) => (n === 1 ? " answer" : " answers")} />
            : <p className="muted small">No other sites were named.</p>}
        </Reveal>
      </div>
    </div>
  );
}

function zoneOf(seo: number, agent: number): string {
  if (agent >= 50) return seo >= 50 ? "Ready for search and agents" : "Ready for agents, weak classic SEO";
  return seo >= 50 ? "Strong classic SEO, weak for agents" : "Behind on both";
}

// =====================================================================================================
// Fixes
// =====================================================================================================

const KIND: Record<string, string> = {
  llms_txt: "New file", json_ld: "Snippet", robots_txt: "Replace file", sitemap_xml: "New file", meta_tags: "Snippets",
  html_snippet: "Snippet", a11y_list: "Checklist",
};

export function FixesTab({ data }: { data: AuditData }) {
  const { audit, fixes } = data;
  const params = useSearchParams();
  const wanted = params.get("open");
  const [open, setOpen] = useState<string | null>(() => fixes.find((f) => wanted && f.check_ids.includes(wanted))?.id ?? fixes[0]?.id ?? null);
  const p = audit.verdict.projection;
  if (!fixes.length) return <Empty>{audit.status === "done" ? "No fixes were generated: nothing failed that AgentRank can write a fix for." : "Fixes are written at the end of the audit."}</Empty>;

  return (
    <div className="bento">
      <div className="span-8">
        <Reveal className="section-head"><h2 className="h2">{plural(fixes.length, "fix", "fixes")}, ready to paste</h2></Reveal>
        <div className="acc" style={{ borderTop: "1px solid var(--line)" }}>
          {fixes.map((f, i) => <FixItem key={f.id} fix={f} i={i} open={open === f.id} onToggle={() => setOpen(open === f.id ? null : f.id)} />)}
        </div>
      </div>
      <Reveal className="card flat span-4" i={2} style={{ alignSelf: "start", position: "sticky", top: 84 }}>
        <h2 className="h3">If you apply all {fixes.length}</h2>
        <p className="small muted" style={{ marginTop: 4 }}>An estimate: each fix is assumed to make its check pass.</p>
        {p ? (
          <ul style={{ marginTop: 18, display: "grid", gap: 16 }}>
            {["agent_ready", ...MODULES.map((m) => m.key)].map((k) => (
              <li key={k}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14 }}>
                  <span style={{ fontWeight: k === "agent_ready" ? 600 : 400, color: "var(--ink)" }}>{moduleLabel(k)}</span>
                  <span className="num"><span className="muted">{score(p.current[k])}</span>{(p.projected[k] ?? 0) > (p.current[k] ?? 0) + 0.5 && <> <ArrowRight size={11} weight="bold" style={{ display: "inline" }} /> <span style={{ color: "var(--data)", fontWeight: 600 }}>{score(p.projected[k])}</span></>}</span>
                </div>
                <div style={{ marginTop: 8 }}><Meter value={p.current[k] ?? 0} after={p.projected[k] ?? null} tone={MODULES.find((m) => m.key === k)?.tone ?? "blue"} /></div>
              </li>
            ))}
          </ul>
        ) : <p className="muted" style={{ marginTop: 16 }}>No projection yet.</p>}
      </Reveal>
    </div>
  );
}

function FixItem({ fix, i, open, onToggle }: { fix: Fix; i: number; open: boolean; onToggle: () => void }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try { await navigator.clipboard.writeText(fix.content); setCopied(true); setTimeout(() => setCopied(false), 1800); } catch { /* clipboard blocked */ }
  }
  return (
    <Reveal className={`item${open ? " open" : ""}`} i={Math.min(i, 6)}>
      <button className="acc-head" onClick={onToggle} aria-expanded={open}>
        <span className="pm" />
        <span style={{ flex: 1, minWidth: 0 }}>
          <span className="h3" style={{ display: "block" }}>{fix.title}</span>
          <span className="small muted" style={{ display: "block", marginTop: 2 }}>Resolves {fix.finding_titles.map((t) => t.toLowerCase()).join("; ")}</span>
        </span>
        <span className="figure hide-sm" style={{ fontSize: 22, color: "var(--data)" }}>+{score(fix.impact_estimate)}</span>
        <SeverityTag severity={fix.severity} />
      </button>
      <div className="acc-body"><div><div className="inner">
        <p className="small" style={{ marginBottom: 12 }}>
          <span className="tag" style={{ marginRight: 8 }}>{KIND[fix.type] ?? "Fix"}</span>
          {fix.meta.filename ? <>Save as <span className="mono">{fix.meta.filename}</span> at the {fix.meta.location}.</> : <>Add to {fix.meta.location ?? "the affected pages"}.</>}
        </p>
        <div style={{ position: "relative" }}>
          <pre className="code" tabIndex={0}>{fix.content}</pre>
          <button className="btn sm" onClick={copy} style={{ position: "absolute", top: 10, right: 10, background: "var(--surface)" }}>
            {copied ? <><CheckCircle size={14} weight="fill" color="var(--green)" />Copied</> : <><Copy size={14} weight="bold" />Copy</>}
          </button>
        </div>
        {fix.meta.missing_facts?.length ? <p className="notice" style={{ marginTop: 12 }}>Fill in before publishing: {fix.meta.missing_facts.join(", ")}.</p> : null}
        {fix.meta.note && <p className="small muted" style={{ marginTop: 10 }}>{fix.meta.note}</p>}
      </div></div></div>
    </Reveal>
  );
}

// =====================================================================================================
// Agent replays: what the agent saw, step by step, with a lightbox
// =====================================================================================================

const ACTION: Record<string, string> = {
  click: "Clicked", type: "Typed", select: "Selected", press_enter: "Pressed Enter", scroll_down: "Scrolled down",
  go_back: "Went back", done: "Finished", give_up: "Gave up",
};

export function AgentsTab({ data }: { data: AuditData }) {
  const { audit, runs } = data;
  const params = useSearchParams();
  const [selected, setSelected] = useState<string | null>(params.get("run"));
  const run = runs.find((r) => r.id === selected) ?? runs.find((r) => !r.success) ?? runs[0];
  if (!runs.length) return <Empty>{audit.status === "done" ? "No agent tests ran for this audit." : "Agent tests run after the checks; each run takes about a minute."}</Empty>;
  const tasks = [...new Set(runs.map((r) => r.task))];

  return (
    <div className="bento">
      <div className="span-4" style={{ alignSelf: "start" }}>
        <Reveal className="section-head"><h2 className="h2">Runs</h2><span className="small faint">{runs.filter((r) => r.success).length} of {runs.length} succeeded</span></Reveal>
        {tasks.map((t, ti) => (
          <Reveal key={t} i={ti} style={{ marginBottom: 20 }}>
            <p className="small muted" style={{ marginBottom: 6 }}>{t}</p>
            <div className="segmented" style={{ display: "flex" }}>
              {runs.filter((r) => r.task === t).map((r) => (
                <button key={r.id} aria-pressed={r.id === run?.id} onClick={() => setSelected(r.id)} style={{ display: "flex", alignItems: "center", gap: 6, flex: 1 }}>
                  <Ok ok={r.success} />Run {r.run_no}
                </button>
              ))}
            </div>
          </Reveal>
        ))}
        <p className="small muted">{audit.tasks.length ? "Tasks given with the audit." : "Tasks suggested by AgentRank from the site."} The test browser blocks every form submission except add-to-cart, so nothing reaches the business.</p>
      </div>
      {run && <RunDetail run={run} key={run.id} />}
    </div>
  );
}

function RunDetail({ run }: { run: AgentRun }) {
  const [zoom, setZoom] = useState<number | null>(null);
  const last = run.steps.length - 1;
  return (
    <Reveal className="card span-8" i={1}>
      <div className="card-head" style={{ alignItems: "flex-start" }}>
        <div style={{ minWidth: 0 }}>
          <h2 className="h2" style={{ fontSize: 22 }}>{run.task}</h2>
          <p className="small muted" style={{ marginTop: 6 }}>
            Run {run.run_no} · {plural(run.steps.length, "step")} · {run.seconds ?? "—"} s · {(run.tokens.total_tokens ?? 0).toLocaleString("en-GB")} tokens
            {run.blocked_submits ? ` · ${plural(run.blocked_submits, "submission")} blocked` : ""}
          </p>
        </div>
        <span className={`tag ${run.success ? "green" : "red"}`}>{run.success ? "Succeeded" : "Failed"}</span>
      </div>
      <p style={{ marginBottom: 20 }}><span className="muted">{run.success ? "Agent's answer: " : "Where it got stuck: "}</span>{run.success ? run.answer : run.failure_reason}</p>
      <div className="film" aria-label="What the agent saw at each step">
        {run.steps.map((s, i) => (
          <figure key={s.n} className={`frame${i === last ? (run.success ? " done" : " stuck") : ""}`}>
            <button className="shot" onClick={() => setZoom(i)} aria-label={`Enlarge step ${s.n}`}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {run.screenshots[i] ? <img src={run.screenshots[i]} alt={`Step ${s.n}: ${s.title}`} loading="lazy" /> : null}
            </button>
            <figcaption style={{ marginTop: 10 }}>
              <p className="small"><span className="mono faint">{s.n}</span>&nbsp; <span style={{ color: "var(--ink)", fontWeight: 500 }}>{ACTION[s.action] ?? s.action}{s.text ? ` “${s.text}”` : ""}</span></p>
              <p className="small muted" style={{ marginTop: 2 }}>{s.thought}</p>
              {s.error && <p className="small" style={{ marginTop: 4, color: "var(--yellow)" }}>{s.error === "no visible change" ? "Nothing changed on the page" : s.error}</p>}
            </figcaption>
          </figure>
        ))}
      </div>
      {zoom != null && <Lightbox run={run} index={zoom} onIndex={setZoom} onClose={() => setZoom(null)} />}
    </Reveal>
  );
}

function Lightbox({ run, index, onIndex, onClose }: { run: AgentRun; index: number; onIndex: (i: number) => void; onClose: () => void }) {
  const n = run.steps.length;
  const step = run.steps[index];
  const prev = useCallback(() => onIndex(Math.max(0, index - 1)), [index, onIndex]);
  const next = useCallback(() => onIndex(Math.min(n - 1, index + 1)), [index, n, onIndex]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose(); else if (e.key === "ArrowLeft") prev(); else if (e.key === "ArrowRight") next();
    };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => { window.removeEventListener("keydown", onKey); document.body.style.overflow = ""; };
  }, [onClose, prev, next]);
  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label={`Step ${step.n} of ${n}`}>
      <div className="bar">
        <p><span className="mono faint">{step.n} / {n}</span>&nbsp;&nbsp;<span style={{ color: "var(--ink)", fontWeight: 500 }}>{ACTION[step.action] ?? step.action}{step.text ? ` “${step.text}”` : ""}</span></p>
        <button className="btn ghost sm" onClick={onClose} aria-label="Close"><X size={16} weight="bold" /><kbd>Esc</kbd></button>
      </div>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {run.screenshots[index] ? <img src={run.screenshots[index]} alt={`Step ${step.n}: ${step.title}`} /> : <div />}
      <div className="bar" style={{ paddingTop: 16 }}>
        <button className="btn" onClick={prev} disabled={index === 0}><ArrowLeft size={16} weight="bold" />Previous</button>
        <p className="small muted" style={{ textAlign: "center", maxWidth: 640 }}>{step.thought}<br /><span className="mono faint">{(() => { try { return new URL(step.url).pathname; } catch { return step.url; } })()}</span></p>
        <button className="btn" onClick={next} disabled={index === n - 1}>Next<ArrowRight size={16} weight="bold" /></button>
      </div>
    </div>
  );
}

// =====================================================================================================
// AI visibility
// =====================================================================================================

export function VisibilityTab({ data }: { data: AuditData }) {
  const { audit, visibility } = data;
  const v = audit.visibility;
  const [open, setOpen] = useState<string | null>(null);
  const providers = useMemo(() => [...new Set(visibility.map((r) => r.provider))], [visibility]);
  const prompts = useMemo(() => [...new Set(visibility.map((r) => r.prompt))], [visibility]);
  if (!visibility.length) return <Empty>{audit.status === "done" ? "AI visibility was not measured for this audit." : "AI visibility runs after the agent tests."}</Empty>;
  const [lo, hi] = v.mention_interval_95 ?? [0, 0];
  const cell = (q: string, p: string) => visibility.find((r) => r.prompt === q && r.provider === p);
  const stats = [
    { label: "Named in discovery answers", value: (v.unbranded_mention_rate ?? 0) * 100, note: `Questions that don't name ${v.brand || "the brand"}` },
    { label: "Named in all answers", value: (v.mention_rate ?? 0) * 100, note: `95% range ${pct(lo)} to ${pct(hi)}, ${plural(v.answers ?? 0, "answer")}` },
    { label: "Linked as a source", value: (v.citation_rate ?? 0) * 100, note: `Answers linking to ${v.domain}` },
    { label: "Share of voice", value: (v.share_of_voice ?? 0) * 100, note: "Against the five most-named sites" },
  ];
  return (
    <div className="bento">
      <Reveal className="card span-12" style={{ padding: 0 }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
          {stats.map((s, i) => (
            <div key={s.label} style={{ padding: 24, borderLeft: i ? "1px solid var(--line)" : 0 }}>
              <p className="small muted">{s.label}</p>
              <p className="figure" style={{ fontSize: 44, marginTop: 8 }}><CountUp value={Math.round(s.value)} /><span className="faint" style={{ fontSize: 18 }}>%</span></p>
              <p className="small muted" style={{ marginTop: 6 }}>{s.note}</p>
            </div>
          ))}
        </div>
      </Reveal>

      <div className="span-8">
        <Reveal className="section-head" style={{ marginTop: 16 }}>
          <h2 className="h2">Questions customers ask</h2>
          <span className="small faint">{v.errors ? `${v.errors} of ${visibility.length} answers skipped (model quota)` : "Answered with web search"}</span>
        </Reveal>
        <div className="acc" style={{ borderTop: "1px solid var(--line)" }}>
          {prompts.map((q, i) => {
            const first = visibility.find((r) => r.prompt === q)!;
            const isOpen = open === q;
            return (
              <Reveal key={q} i={i} className={`item${isOpen ? " open" : ""}`}>
                <button className="acc-head" onClick={() => setOpen(isOpen ? null : q)} aria-expanded={isOpen}>
                  <span className="pm" />
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ display: "block", color: "var(--ink)" }}>{q}</span>
                    <span className="small faint">{first.intent === "branded" ? "Names the brand" : first.intent === "comparison" ? "Comparison" : first.intent === "problem" ? "Problem-led" : "Discovery"}</span>
                  </span>
                  {providers.map((p) => {
                    const r = cell(q, p);
                    return <span key={p} title={`${shortModel(p)}: ${!r || r.error ? "skipped" : r.mentioned ? "named" : "not named"}`} style={{ width: 22, display: "flex", justifyContent: "center" }}>
                      {!r || r.error ? <span className="faint">—</span> : <Ok ok={r.mentioned} label={r.mentioned ? "Named" : "Not named"} />}
                    </span>;
                  })}
                </button>
                <div className="acc-body"><div><div className="inner" style={{ display: "grid", gap: 20, gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
                  {providers.map((p) => <Answer key={p} provider={p} row={cell(q, p)} />)}
                </div></div></div>
              </Reveal>
            );
          })}
        </div>
      </div>

      <div className="span-4" style={{ display: "grid", gap: 16, alignContent: "start", marginTop: 16 }}>
        <Reveal className="card" i={1}>
          <h2 className="h3" style={{ marginBottom: 8 }}>Recommended instead</h2>
          {v.top_competitors?.length ? <BarList rows={v.top_competitors.slice(0, 8).map((c) => ({ label: c.domain, value: c.answers }))} unit={(n) => (n === 1 ? " answer" : " answers")} />
            : <p className="small muted">No other sites were named.</p>}
        </Reveal>
        <Reveal className="card flat" i={2}>
          <h2 className="h3" style={{ marginBottom: 8 }}>By model</h2>
          <ul className="list">
            {Object.entries(v.per_provider ?? {}).map(([p, r]) => (
              <li key={p} className="row" style={{ padding: "12px 0" }}>
                <div className="grow"><p className="title mono" style={{ fontSize: 13 }}>{shortModel(p)}</p><p className="sub">{r.mentions} of {plural(r.answers, "answer")}</p></div>
                <span className="figure" style={{ fontSize: 24 }}>{pct(r.mention_rate)}</span>
              </li>
            ))}
          </ul>
        </Reveal>
      </div>
    </div>
  );
}

function Answer({ provider, row }: { provider: string; row?: VisibilityRow }) {
  return (
    <div style={{ minWidth: 0 }}>
      <p className="small" style={{ marginBottom: 8, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <span className="mono" style={{ color: "var(--ink)" }}>{shortModel(provider)}</span>
        {row && !row.error && (row.mentioned ? <span className="tag green">Named</span> : <span className="tag red">Not named</span>)}
        {row?.cited_url && <span className="tag blue">Linked</span>}
        {row && !row.error && !row.searched && <span className="tag">No search</span>}
      </p>
      {!row || row.error ? <p className="small muted">Skipped: {row?.error?.includes("daily") ? "the model's daily quota ran out." : row?.error?.slice(0, 120) ?? "no answer."}</p> : (
        <>
          <div className="small" style={{ whiteSpace: "pre-wrap", maxHeight: 240, overflow: "auto", padding: "14px 16px", background: "var(--bone)", borderRadius: 8, border: "1px solid var(--line)" }}>{(row.answer ?? "").slice(0, 1400)}</div>
          {row.competitors.length > 0 && <p className="small muted" style={{ marginTop: 8 }}>Also named: <span className="mono">{row.competitors.slice(0, 5).join(", ")}</span></p>}
        </>
      )}
    </div>
  );
}

// =====================================================================================================
// Checks
// =====================================================================================================

const STATUS: Record<Check["status"], [string, string]> = { pass: ["green", "Pass"], partial: ["yellow", "Partial"], fail: ["red", "Fail"], na: ["", "n/a"] };

export function ChecksTab({ data }: { data: AuditData }) {
  const { scores, audit } = data;
  const params = useSearchParams();
  const modules = MODULES.filter((m) => scores.some((s) => s.category === m.key));
  const [mod, setMod] = useState(params.get("m") && modules.some((m) => m.key === params.get("m")) ? params.get("m")! : modules[0]?.key ?? "seo");
  const [open, setOpen] = useState<string | null>(null);
  if (!modules.length) return <Empty>Checks appear when the crawl finishes.</Empty>;
  const current = scores.find((s) => s.category === mod);
  const list = (current?.details.checks ?? []).slice().sort((a, b) => ["fail", "partial", "pass", "na"].indexOf(a.status) - ["fail", "partial", "pass", "na"].indexOf(b.status));
  const agentReady = scores.find((s) => s.category === "agent_ready");

  return (
    <div className="bento">
      <div className="span-8">
        <Reveal style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap", marginBottom: 20 }}>
          <div className="segmented" role="group" aria-label="Module">
            {modules.map((m) => <button key={m.key} aria-pressed={m.key === mod} onClick={() => { setMod(m.key); setOpen(null); }}>{m.label}</button>)}
          </div>
          <span className="figure" style={{ fontSize: 32 }}><CountUp value={current?.value != null ? Math.round(current.value) : null} /><span className="faint" style={{ fontSize: 16 }}>{mod === "task_success" ? "%" : " / 100"}</span></span>
        </Reveal>
        <div className="acc" style={{ borderTop: "1px solid var(--line)" }} key={mod}>
          {list.map((c, i) => (
            <Reveal key={c.id} i={Math.min(i, 8)} className={`item${open === c.id ? " open" : ""}`}>
              <button className="acc-head" style={{ padding: "16px 0" }} onClick={() => setOpen(open === c.id ? null : c.id)} aria-expanded={open === c.id}>
                <span className="pm" />
                <span style={{ flex: 1, minWidth: 0, color: "var(--ink)" }}>{c.title}</span>
                <span className="small faint mono hide-sm">×{c.weight}</span>
                <span className={`tag ${STATUS[c.status][0]}`} style={{ width: 72, justifyContent: "center" }}>{STATUS[c.status][1]}</span>
              </button>
              <div className="acc-body"><div><div className="inner">
                <p>{c.detail || "No detail recorded."}</p>
                {c.status !== "pass" && c.status !== "na" && c.fix_hint && <p className="small" style={{ marginTop: 8 }}><span className="muted">How to fix: </span>{c.fix_hint}</p>}
                <p className="small faint mono" style={{ marginTop: 8 }}>{c.id}</p>
              </div></div></div>
            </Reveal>
          ))}
        </div>
      </div>
      <Reveal className="card flat span-4" i={1} style={{ alignSelf: "start" }}>
        <h2 className="h3">How Agent-Ready is built</h2>
        <p className="small muted" style={{ marginTop: 4 }}>Weights for a {(audit.site_type ?? "other").replace("_", " ")} site. Pass counts in full, partial half, fail nothing.</p>
        <ul style={{ marginTop: 16, display: "grid", gap: 14 }}>
          {Object.entries(agentReady?.details.weights ?? {}).map(([k, w]) => (
            <li key={k}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14 }}>
                <span style={{ color: "var(--ink)" }}>{moduleLabel(k)}</span>
                <span className="num muted">{Math.round(w * 100)}% · {agentReady?.details.missing?.includes(k) ? "—" : score(audit.score_summary[k])}</span>
              </div>
              <div style={{ marginTop: 8 }}><Meter value={audit.score_summary[k] ?? 0} tone={MODULES.find((m) => m.key === k)?.tone} /></div>
            </li>
          ))}
        </ul>
        <p className="small muted" style={{ marginTop: 16 }}>Classic SEO is reported beside Agent-Ready, not inside it. <Link className="link" href="/rubric">Full rubric</Link></p>
      </Reveal>
    </div>
  );
}

// =====================================================================================================
// Site map (3D) and pages
// =====================================================================================================

interface SiteFile { url: string; found: boolean; status: number | null }

export function PagesTab({ data }: { data: AuditData }) {
  const { audit, pages } = data;
  const [files, setFiles] = useState<Record<string, SiteFile> | null>(null);
  const [selected, setSelected] = useState<MapNode | null>(null);
  useEffect(() => { api<Record<string, SiteFile>>(`/audits/${audit.id}/site-files`).then(setFiles).catch(() => setFiles({})); }, [audit.id]);
  if (!pages.length) return <Empty>{audit.status === "failed" ? "The crawl did not fetch any pages." : "Pages appear when the crawl finishes."}</Empty>;
  const sel = selected?.id ? selected : null;
  const legend = [["#346538", "80% or more readable without JavaScript"], ["#956400", "50 to 79%"], ["#9f2f2d", "Under 50%, or an error"], ["#a5a49f", "Not rendered"]];

  return (
    <div className="bento">
      <Reveal className="card span-8" style={{ padding: 0, overflow: "hidden", background: "var(--bone)" }}>
        <div style={{ height: 480, position: "relative" }}>
          <SiteMap3D pages={pages} selected={sel?.id ?? null} onSelect={(n) => setSelected(n.id ? n : null)} />
          <p className="small muted" style={{ position: "absolute", left: 20, bottom: 16, pointerEvents: "none" }}>Drag to turn · scroll to zoom · click a page</p>
        </div>
      </Reveal>
      <div className="span-4" style={{ display: "grid", gap: 16, alignContent: "start" }}>
        <Reveal className="card" i={1}>
          {sel ? (
            <>
              <p className="small muted">Selected page</p>
              <p className="mono" style={{ color: "var(--ink)", marginTop: 6, overflowWrap: "anywhere" }}>{sel.path}</p>
              <p className="small muted" style={{ marginTop: 4 }}>{sel.title || "No title"}</p>
              <p className="figure" style={{ fontSize: 40, marginTop: 16, color: ratioColor(sel.ratio, sel.status) }}>{sel.status != null && sel.status >= 400 ? sel.status : sel.ratio == null ? "—" : pct(sel.ratio)}</p>
              <p className="small muted">{sel.status != null && sel.status >= 400 ? "HTTP error" : "of its text is in the raw HTML, readable without JavaScript"}</p>
              <a className="link small" href={sel.url} target="_blank" rel="noreferrer" style={{ display: "inline-block", marginTop: 14 }}>Open page</a>
            </>
          ) : (
            <>
              <h2 className="h3">The crawled site</h2>
              <p className="small muted" style={{ marginTop: 4 }}>{plural(pages.length, "page")}, placed by URL depth around the homepage.</p>
              <ul style={{ marginTop: 16, display: "grid", gap: 10 }}>
                {legend.map(([c, l]) => <li key={l} className="small" style={{ display: "flex", gap: 10, alignItems: "center" }}><span style={{ width: 10, height: 10, borderRadius: "50%", background: c, flex: "none" }} />{l}</li>)}
              </ul>
            </>
          )}
        </Reveal>
        <Reveal className="card flat" i={2}>
          <h2 className="h3" style={{ marginBottom: 6 }}>Files agents look for</h2>
          {files === null ? <span className="skeleton" style={{ width: 200, height: 12 }} /> : (
            <ul className="list">
              {Object.entries(files).map(([path, f]) => (
                <li key={path} className="row" style={{ padding: "10px 0", gap: 10 }}>
                  <Ok ok={f.found} label={f.found ? "Found" : "Missing"} /><span className="grow mono small title">{path}</span>
                </li>
              ))}
            </ul>
          )}
        </Reveal>
      </div>

      <div className="span-12" style={{ marginTop: 32 }}>
        <Reveal className="section-head"><h2 className="h2">All pages</h2><span className="small faint">Crawled as AgentRankBot, robots.txt respected</span></Reveal>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Page</th><th className="n">Status</th><th className="n">Without JavaScript</th><th className="n hide-sm">Text</th></tr></thead>
            <tbody>
              {pages.map((p) => {
                const ratio = p.metrics.no_js_text_ratio as number | null | undefined;
                const path = (() => { try { const u = new URL(p.url); return u.pathname + u.search; } catch { return p.url; } })();
                return (
                  <tr key={p.id}>
                    <td style={{ maxWidth: 0, width: "62%" }}>
                      <a href={p.url} target="_blank" rel="noreferrer" className="mono link" style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textDecorationColor: "transparent" }}>{path}</a>
                      <span className="sub" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{(p.metrics.title as string) || (p.metrics.blocked_by_robots ? "Blocked by robots.txt" : "No title")}</span>
                    </td>
                    <td className="n num" style={{ color: (p.status_code ?? 0) >= 400 ? "var(--red)" : undefined }}>{p.status_code ?? "—"}</td>
                    <td className="n num" style={{ color: ratio != null && ratio < 0.5 ? "var(--red)" : undefined }}>{ratio == null ? "—" : pct(ratio)}</td>
                    <td className="n num hide-sm">{p.metrics.rendered_text_chars != null ? (p.metrics.rendered_text_chars as number).toLocaleString("en-GB") : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="small faint" style={{ marginTop: 12 }}>Audited {when(audit.started_at)} · {host(audit.site_url)}</p>
      </div>
    </div>
  );
}
