"use client";

import { useEffect, useState } from "react";
import { Meter, Reveal, useReveal } from "@/components/ui";
import { api, moduleLabel, siteType } from "@/lib/api";

interface Rubric {
  version: string;
  base_weights: Record<string, number>;
  type_weights: Record<string, Record<string, number>>;
  type_need: Record<string, number>;
}

const NEED = ["Low", "Medium", "High"];
const STEPS = [
  ["Checks become module scores", "Each module is a weighted sum of its checks: pass counts in full, partial half, fail nothing. Checks that do not apply are left out."],
  ["Agents and AI answers are measured directly", "Task success is the share of agent runs that finished their task. AI visibility weighs discovery answers 60%, all answers 20% and links 20%."],
  ["Modules combine into Agent-Ready", "The four agent modules are combined with the weights for the site's type. A module that did not run is left out and the rest re-weighted; the audit says which."],
  ["The verdict adds up the reasons", "Points for the site type, task-heavy visitors, a low score, competitors named in AI answers instead, and failed agent tasks. Four or more is Critical, two or three Recommended."],
];

export default function RubricPage() {
  const ref = useReveal<HTMLElement>();
  const [rubric, setRubric] = useState<Rubric | null>(null);
  const [type, setType] = useState("ecommerce");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api<Rubric>("/rubric").then(setRubric).catch((e) => setError(e.message)); }, []);

  const types = rubric ? Object.keys(rubric.type_need) : [];
  const weights = rubric ? rubric.type_weights[type] ?? rubric.base_weights : {};

  return (
    <main className="page" ref={ref}>
      <Reveal className="page-head">
        <div>
          <h1 className="h1">Scoring rubric{rubric ? <span className="faint"> v{rubric.version}</span> : null}</h1>
          <p className="lede" style={{ marginTop: 10 }}>Every score AgentRank shows can be traced back to these weights and the checks behind them.</p>
        </div>
      </Reveal>
      {error && <p className="notice red">{error}</p>}

      <div className="bento">
        <Reveal className="card span-7" i={1}>
          <div className="card-head" style={{ flexWrap: "wrap" }}>
            <h2 className="h3">Weights by site type</h2>
            <select className="input" style={{ width: "auto", height: 34 }} value={type} onChange={(e) => setType(e.target.value)} aria-label="Site type">
              {types.map((t) => <option key={t} value={t}>{siteType(t)}</option>)}
            </select>
          </div>
          {!rubric ? <span className="skeleton" style={{ width: "100%", height: 120 }} /> : (
            <ul style={{ display: "grid", gap: 20 }}>
              {Object.entries(weights).map(([k, w]) => (
                <li key={`${type}-${k}`}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--ink)" }}>{moduleLabel(k)}</span>
                    <span className="figure" style={{ fontSize: 24 }}>{Math.round(w * 100)}<span className="faint" style={{ fontSize: 14 }}>%</span></span>
                  </div>
                  <div style={{ marginTop: 8 }}><Meter value={w * 100} /></div>
                </li>
              ))}
            </ul>
          )}
          {rubric && <p className="small muted" style={{ marginTop: 20 }}>How much agent traffic matters to a {siteType(type).toLowerCase()} site: <strong style={{ color: "var(--ink)", fontWeight: 600 }}>{NEED[rubric.type_need[type]] ?? "—"}</strong>.{!rubric.type_weights[type] && " This type uses the default weights."}</p>}
        </Reveal>
        <Reveal className="card flat span-5" i={2}>
          <h2 className="h3" style={{ marginBottom: 6 }}>How a score is made</h2>
          <ol className="list">
            {STEPS.map(([title, body], i) => (
              <li key={title} style={{ padding: "16px 0", display: "grid", gridTemplateColumns: "28px 1fr", gap: 8 }}>
                <span className="figure faint" style={{ fontSize: 20 }}>{i + 1}</span>
                <div><p className="h3" style={{ fontWeight: 500 }}>{title}</p><p className="small muted" style={{ marginTop: 4 }}>{body}</p></div>
              </li>
            ))}
          </ol>
        </Reveal>
      </div>
    </main>
  );
}
