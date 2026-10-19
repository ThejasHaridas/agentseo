"use client";

import { useEffect, useRef, useState } from "react";

interface Point { x: number; y: number; label?: string }

/** Semicircle gauge, 0-100. The ink arc is now; a pale blue arc runs on to the estimate after fixes. */
export function Gauge({ value, after, size = 240 }: { value: number | null; after?: number | null; size?: number }) {
  const [on, setOn] = useState(false);
  useEffect(() => { const t = requestAnimationFrame(() => setOn(true)); return () => cancelAnimationFrame(t); }, []);
  const stroke = 10, r = (size - stroke) / 2, cx = size / 2, cy = size / 2;
  const len = Math.PI * r;
  const d = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;
  const v = value ?? 0;
  const a = after != null && after > v ? after : v;
  const offset = (p: number) => (on ? len * (1 - p / 100) : len);
  return (
    <svg viewBox={`0 0 ${size} ${size / 2 + stroke}`} width="100%" style={{ maxWidth: size }} role="img"
         aria-label={value == null ? "Not scored yet" : `Agent-Ready ${Math.round(v)} of 100${a > v ? `, about ${Math.round(a)} after fixes` : ""}`}>
      <path d={d} fill="none" stroke="#efeeea" strokeWidth={stroke} strokeLinecap="round" />
      {a > v && <path d={d} fill="none" stroke="var(--data-soft)" strokeWidth={stroke} strokeLinecap="round"
                      strokeDasharray={len} strokeDashoffset={offset(a)} style={{ transition: "stroke-dashoffset 1200ms var(--ease) 200ms" }} />}
      {value != null && <path d={d} fill="none" stroke="var(--data)" strokeWidth={stroke} strokeLinecap="round"
                              strokeDasharray={len} strokeDashoffset={offset(v)} style={{ transition: "stroke-dashoffset 1100ms var(--ease)" }} />}
    </svg>
  );
}

const ZONES = [
  { x: 0, y: 50, label: "Ready for agents, weak classic SEO" },
  { x: 50, y: 50, label: "Ready for agents and search" },
  { x: 0, y: 0, label: "Behind on both" },
  { x: 50, y: 0, label: "Strong classic SEO, weak for agents" },
];

/** Classic SEO (x) against Agent-Ready (y). Hover a dot or a quadrant for what it means. */
export function Quadrant({ now, after, history = [] }: { now: Point | null; after?: Point | null; history?: Point[] }) {
  const W = 340, H = 260, L = 30, R = 10, T = 10, B = 28;
  const pw = W - L - R, ph = H - T - B;
  const sx = (v: number) => L + (v / 100) * pw;
  const sy = (v: number) => T + ph - (v / 100) * ph;
  const wrap = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<{ x: number; y: number; text: React.ReactNode } | null>(null);
  const [zone, setZone] = useState<number | null>(null);
  const [on, setOn] = useState(false);
  useEffect(() => { const t = setTimeout(() => setOn(true), 120); return () => clearTimeout(t); }, []);

  const show = (px: number, py: number, text: React.ReactNode) => {
    const box = wrap.current?.getBoundingClientRect();
    const scale = box ? box.width / W : 1;
    setTip({ x: px * scale, y: py * scale, text });
  };
  const moved = now && after && (Math.abs(after.x - now.x) > 0.5 || Math.abs(after.y - now.y) > 0.5);

  return (
    <div ref={wrap} style={{ position: "relative" }} onMouseLeave={() => { setTip(null); setZone(null); }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img"
           aria-label={now ? `Classic SEO ${Math.round(now.x)}, Agent-Ready ${Math.round(now.y)}` : "No scores yet"}>
        {ZONES.map((z, i) => (
          <rect key={i} x={sx(z.x)} y={sy(z.y + 50)} width={pw / 2} height={ph / 2} fill={zone === i ? "#f7f6f3" : "transparent"}
                onMouseEnter={() => { setZone(i); show(sx(z.x + 25), sy(z.y + 50) + 6, z.label); }} style={{ transition: "fill 150ms ease" }} />
        ))}
        {[0, 25, 50, 75, 100].map((t) => (
          <g key={t} pointerEvents="none">
            <line x1={L} x2={W - R} y1={sy(t)} y2={sy(t)} stroke={t === 50 ? "#dddcd8" : "#efeeea"} strokeDasharray={t === 50 ? "3 4" : undefined} />
            <text x={L - 8} y={sy(t) + 4} textAnchor="end" fontSize="11" fill="var(--faint)" fontFamily="var(--mono)">{t}</text>
            <text x={sx(t)} y={H - 8} textAnchor={t === 0 ? "start" : t === 100 ? "end" : "middle"} fontSize="11" fill="var(--faint)" fontFamily="var(--mono)">{t}</text>
          </g>
        ))}
        <line x1={sx(50)} x2={sx(50)} y1={T} y2={T + ph} stroke="#dddcd8" strokeDasharray="3 4" pointerEvents="none" />
        {history.map((p, i) => (
          <circle key={i} cx={sx(p.x)} cy={sy(p.y)} r="4" fill="#d9d7d0"
                  onMouseEnter={() => show(sx(p.x), sy(p.y), <>{p.label ?? "Earlier audit"}<br />SEO {Math.round(p.x)} · Agent-Ready {Math.round(p.y)}</>)} />
        ))}
        {now && moved && after && (
          <g>
            <line x1={sx(now.x)} y1={sy(now.y)} x2={sx(after.x)} y2={sy(after.y)} stroke="var(--data)" strokeWidth="1.5" strokeDasharray="4 4"
                  pointerEvents="none" style={{ opacity: on ? 1 : 0, transition: "opacity 600ms ease 500ms" }} />
            <circle cx={sx(after.x)} cy={sy(after.y)} r="7" fill="var(--surface)" stroke="var(--data)" strokeWidth="2"
                    style={{ opacity: on ? 1 : 0, transition: "opacity 600ms ease 700ms" }}
                    onMouseEnter={() => show(sx(after.x), sy(after.y), <>After the generated fixes (estimate)<br />SEO {Math.round(after.x)} · Agent-Ready {Math.round(after.y)}</>)} />
          </g>
        )}
        {now && (
          <circle cx={sx(now.x)} cy={sy(now.y)} r="7.5" fill="var(--data)"
                  onMouseEnter={() => show(sx(now.x), sy(now.y), <>This audit<br />SEO {Math.round(now.x)} · Agent-Ready {Math.round(now.y)}</>)} />
        )}
      </svg>
      {tip && <div className="tip" style={{ left: tip.x, top: tip.y }}>{tip.text}</div>}
    </div>
  );
}

/** A ranked list with a thin proportional bar under each label. */
export function BarList({ rows, unit }: { rows: { label: string; value: number }[]; unit: (n: number) => string }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="list">
      {rows.map((r, i) => (
        <li key={r.label} style={{ padding: "12px 0" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 14 }}>
            <span className="mono" style={{ color: "var(--ink)", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>{r.label}</span>
            <span className="num muted">{r.value}{unit(r.value)}</span>
          </div>
          <div style={{ marginTop: 8, height: 2, background: "#efeeea", borderRadius: 1 }}>
            <div style={{ height: 2, width: `${(r.value / max) * 100}%`, background: i === 0 ? "var(--ink)" : "#bab8b1", borderRadius: 1 }} />
          </div>
        </li>
      ))}
    </ul>
  );
}
