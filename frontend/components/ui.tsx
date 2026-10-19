"use client";

import { useEffect, useRef, useState } from "react";
import type { Status } from "@/lib/api";

const reducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Adds `.in` to every `.reveal` inside once it enters the viewport (IntersectionObserver, no scroll listeners). */
export function useReveal<T extends HTMLElement>() {
  // A callback ref, so the observer re-binds when the element appears later (after a loading state).
  const [root, setRoot] = useState<T | null>(null);
  useEffect(() => {
    if (!root) return;
    const targets = () => [root, ...root.querySelectorAll<HTMLElement>(".reveal")].filter((el) => el.classList.contains("reveal"));
    if (reducedMotion() || !("IntersectionObserver" in window)) {
      targets().forEach((el) => el.classList.add("in"));
      return;
    }
    const settle = (el: Element) => el.addEventListener("transitionend", () => el.classList.add("settled"), { once: true });
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) { e.target.classList.add("in"); settle(e.target); io.unobserve(e.target); }
    }, { rootMargin: "0px 0px -6% 0px" });
    const observe = () => targets().forEach((el) => { if (!el.classList.contains("in")) io.observe(el); });
    observe();
    // Blocks that arrive later (a running audit filling in) reveal too.
    const mo = new MutationObserver(observe);
    mo.observe(root, { childList: true, subtree: true });
    return () => { io.disconnect(); mo.disconnect(); };
  }, [root]);
  return setRoot as (el: HTMLElement | null) => void;
}

export function Reveal({ children, className = "", i = 0, as: Tag = "div", style, ...rest }:
  { children: React.ReactNode; className?: string; i?: number; as?: "div" | "section" | "li" } & React.HTMLAttributes<HTMLElement>) {
  return <Tag className={`reveal ${className}`} style={{ ["--i" as string]: i, ...style }} {...rest}>{children}</Tag>;
}

/** A figure that counts up from 0 (or its previous value) when it first comes into view. */
export function CountUp({ value, decimals = 0, suffix = "" }: { value: number | null | undefined; decimals?: number; suffix?: string }) {
  const [shown, setShown] = useState<number | null>(value == null ? null : reducedMotion() ? value : 0);
  const ref = useRef<HTMLSpanElement>(null);
  const from = useRef(0);
  useEffect(() => {
    if (value == null) { setShown(null); return; }
    if (reducedMotion()) { setShown(value); return; }
    const el = ref.current;
    let raf = 0;
    const run = () => {
      const start = performance.now();
      const a = from.current;
      const tick = (t: number) => {
        const k = Math.min(1, (t - start) / 900);
        const eased = 1 - Math.pow(1 - k, 4);
        setShown(a + (value - a) * eased);
        if (k < 1) raf = requestAnimationFrame(tick); else from.current = value;
      };
      raf = requestAnimationFrame(tick);
    };
    if (!el || !("IntersectionObserver" in window)) { run(); return () => cancelAnimationFrame(raf); }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { run(); io.disconnect(); } });
    io.observe(el);
    return () => { io.disconnect(); cancelAnimationFrame(raf); };
  }, [value]);
  if (shown == null) return <span className="faint">—</span>;
  return <span ref={ref} className="num">{shown.toFixed(decimals)}{suffix}</span>;
}

/** A 0-100 bar that grows into place; an optional lighter segment shows a projected value. */
export function Meter({ value, after, label, tone }: { value: number | null | undefined; after?: number | null; label?: string; tone?: string }) {
  const [on, setOn] = useState(false);
  useEffect(() => { const t = requestAnimationFrame(() => setOn(true)); return () => cancelAnimationFrame(t); }, []);
  const v = value ?? 0;
  const a = after != null && after > v ? after : null;
  return (
    <div className={`meter${tone ? ` colored c-${tone}` : ""}`} role="img" aria-label={label ?? `${Math.round(v)} of 100`}>
      {a != null && <span className="ghost" style={{ width: on ? `${a}%` : 0 }} />}
      <span style={{ width: on ? `${v}%` : 0 }} />
    </div>
  );
}

export function StatusTag({ status }: { status: Status }) {
  if (status === "running" || status === "queued") return <span className="tag blue"><span className="pulse" />{status === "queued" ? "Queued" : "Running"}</span>;
  if (status === "failed") return <span className="tag red">Failed</span>;
  return <span className="tag green">Done</span>;
}

export function PriorityTag({ priority }: { priority: string }) {
  const cls = priority === "Critical" ? "red" : priority === "Recommended" ? "yellow" : "";
  return <span className={`tag ${cls}`}>{priority}</span>;
}

export function SeverityTag({ severity }: { severity: string }) {
  const map: Record<string, [string, string]> = { critical: ["red", "Critical"], warning: ["yellow", "Warning"], info: ["", "Info"] };
  const [cls, label] = map[severity] ?? ["", severity];
  return <span className={`tag ${cls}`}>{label}</span>;
}

/** AgentRank's mark: a cursor (the agent) on a rising rank. */
export function Mark({ size = 22 }: { size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">
      <rect x="2.5" y="15" width="4" height="6.5" rx="1" fill="#d9d7d0" />
      <rect x="8.5" y="11" width="4" height="10.5" rx="1" fill="#9c9a93" />
      <rect x="14.5" y="6" width="4" height="15.5" rx="1" fill="#111111" />
      <path d="M13.2 2.2v9.1l2.4-2.2 1.7 3.6 1.6-.7-1.7-3.5 3.3-.2z" fill="#1f6c9f" stroke="#fbfbfa" strokeWidth="1.1" strokeLinejoin="round" />
    </svg>
  );
}

export function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]!.toUpperCase()).join("") || "?";
}
