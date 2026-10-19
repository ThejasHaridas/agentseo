// Types and fetchers for the AgentRank FastAPI backend (proxied at /api by next.config.ts).

export type Status = "queued" | "running" | "done" | "failed";

export interface Factor { factor: string; points: number; why: string }
export interface Projection {
  label: string;
  current: Record<string, number | null>;
  projected: Record<string, number | null>;
}
export interface Verdict {
  priority?: "Critical" | "Recommended" | "Low priority";
  points?: number;
  factors?: Factor[];
  headline?: string;
  explanation?: string;
  projection?: Projection;
}
export interface Classification {
  site_type?: string; brand_name?: string; offering?: string; location?: string; summary?: string;
  key_tasks?: string[]; task_heaviness?: string; source?: string;
}
export interface VisibilitySummary {
  brand?: string; domain?: string; answers?: number; errors?: number;
  mention_rate?: number; mention_interval_95?: [number, number]; unbranded_mention_rate?: number;
  citation_rate?: number; share_of_voice?: number; score?: number | null;
  per_provider?: Record<string, { answers: number; mentions: number; mention_rate: number; interval_95: [number, number] }>;
  top_competitors?: { domain: string; answers: number }[];
}
export interface Audit {
  id: string; site_id: string; status: Status; rubric_version: string; business_type: string | null;
  tasks: string[]; classification: Classification; visibility: VisibilitySummary; verdict: Verdict;
  error: string | null; started_at: string | null; finished_at: string | null; page_count: number;
  site_url: string; site_type: string | null; score_summary: Record<string, number | null>;
  priority: string | null; screenshot_url: string | null;
  project_id: string | null; project_name: string | null;
}
export interface Check {
  id: string; title: string; status: "pass" | "partial" | "fail" | "na"; weight: number;
  severity: "critical" | "warning" | "info"; detail: string; evidence: Record<string, unknown>; fix_hint: string;
}
export interface Score { category: string; value: number | null; details: { checks?: Check[]; included?: string[]; missing?: string[]; weights?: Record<string, number> } }
export interface Finding {
  id: string; category: string; severity: "critical" | "warning" | "info"; title: string;
  evidence: { check_id?: string; detail?: string; fix_hint?: string; status?: string; [k: string]: unknown };
  impact_estimate: number | null;
}
export interface Fix {
  id: string; finding_ids: string[]; finding_titles: string[]; check_ids: string[]; severity: string;
  impact_estimate: number | null; type: string; title: string; content: string;
  meta: { filename?: string; location?: string; note?: string; missing_facts?: string[]; pages?: string[] };
}
export interface Step { n: number; url: string; title: string; thought: string; action: string; element_id: number; text: string; answer: string; success: boolean; error: string | null }
export interface AgentRun {
  id: string; task: string; run_no: number; success: boolean; answer: string | null; failure_reason: string | null;
  steps: Step[]; screenshots: string[]; tokens: { total_tokens?: number }; seconds: number | null; blocked_submits: number;
}
export interface VisibilityRow {
  prompt: string; intent: string | null; provider: string; sample: number; mentioned: boolean; cited_url: string | null;
  in_sources: boolean; competitors: string[]; answer: string | null; source_urls: string[]; searched: boolean; error: string | null;
}
export interface PageRow { id: string; url: string; status_code: number | null; metrics: Record<string, unknown> }

export class ApiError extends Error {
  constructor(message: string, public status = 0) { super(message); }
}

async function detailOf(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join(". ");
  } catch { /* not JSON */ }
  return `The API answered ${res.status}.`;
}

/** Calls the API; on 401 (no or expired session) it sends the browser to sign in and comes back after. */
export async function api<T>(path: string, init?: RequestInit, { redirectOn401 = true } = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { cache: "no-store", credentials: "same-origin", ...init });
  } catch {
    throw new ApiError("Couldn't reach the AgentRank API on localhost:8000.");
  }
  if (res.status === 401 && redirectOn401 && typeof window !== "undefined") {
    const next = window.location.pathname + window.location.search;
    window.location.href = `/login?next=${encodeURIComponent(next)}`;
    throw new ApiError("Sign in to continue.", 401);
  }
  if (!res.ok) throw new ApiError(res.status === 404 ? "Not found." : await detailOf(res), res.status);
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export interface User { id: string; email: string; name: string; created_at: string }

const json = (body: unknown): RequestInit => ({
  method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
});
export const signIn = (email: string, password: string) => api<User>("/auth/login", json({ email, password }), { redirectOn401: false });
export const signUp = (name: string, email: string, password: string) => api<User>("/auth/register", json({ name, email, password }), { redirectOn401: false });
export const signOut = () => api<void>("/auth/logout", { method: "POST" }, { redirectOn401: false });
export const currentUser = () => api<User>("/auth/me");

export function startAudit(url: string, tasks: string[] = [], business_type?: string, project_id?: string | null) {
  return api<Audit>("/audits", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url, tasks, business_type: business_type || null, project_id: project_id || null }),
  });
}

// ---------- projects ----------

export const PROJECT_COLORS = ["blue", "teal", "green", "yellow", "rose", "red", "gray"] as const;
export type ProjectColor = (typeof PROJECT_COLORS)[number];

export interface ProjectSite {
  site_id: string; url: string; latest_audit_id: string; status: Status;
  agent_ready: number | null; seo: number | null; started_at: string | null; screenshot_url: string | null;
}
export interface Project {
  id: string; name: string; description: string; color: ProjectColor; created_at: string;
  audit_count: number; running: number; last_audit_at: string | null; avg_agent_ready: number | null;
  sites: ProjectSite[];
}

export const listProjects = () => api<Project[]>("/projects");
export const getProject = (id: string) => api<Project>(`/projects/${id}`);
export const createProject = (body: { name: string; description?: string; color: ProjectColor }) =>
  api<Project>("/projects", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
export const updateProject = (id: string, body: Partial<{ name: string; description: string; color: ProjectColor }>) =>
  api<Project>(`/projects/${id}`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
export const deleteProject = (id: string) => api<void>(`/projects/${id}`, { method: "DELETE" });

// ---------- formatting ----------

export function host(url: string): string {
  try { return new URL(url).host.replace(/^www\./, ""); } catch { return url; }
}

export function normaliseUrl(input: string): string | null {
  const raw = input.trim();
  if (!raw) return null;
  try {
    const url = new URL(/^https?:\/\//i.test(raw) ? raw : `https://${raw}`);
    return url.hostname.includes(".") ? url.toString() : null;
  } catch { return null; }
}

/** Scores are 0-100 with one decimal in the API; the screen shows whole points. */
export function score(v: number | null | undefined): string {
  return v == null ? "—" : String(Math.round(v));
}

export function pct(v: number | null | undefined, digits = 0): string {
  return v == null ? "—" : `${(v * 100).toFixed(digits)}%`;
}

const SITE_TYPES: Record<string, string> = {
  ecommerce: "E-commerce", local_business: "Local business", saas: "SaaS", docs: "Docs",
  blog: "Blog", portfolio: "Portfolio", government: "Government", other: "Other",
};
export function siteType(t: string | null | undefined): string {
  return t ? SITE_TYPES[t] ?? t : "Not classified yet";
}

/** Each module keeps one muted colour everywhere it appears. */
export const MODULES: { key: string; label: string; tone: string }[] = [
  { key: "seo", label: "Classic SEO", tone: "blue" },
  { key: "readability", label: "Agent readability", tone: "teal" },
  { key: "actionability", label: "Actionability", tone: "yellow" },
  { key: "task_success", label: "Task success", tone: "rose" },
  { key: "visibility", label: "AI visibility", tone: "green" },
];
export function moduleLabel(key: string): string {
  return MODULES.find((m) => m.key === key)?.label ?? (key === "agent_ready" ? "Agent-Ready" : key);
}

export function when(iso: string | null): string {
  if (!iso) return "—";
  // The API stores UTC without an offset.
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  return d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function duration(start: string | null, end: string | null): string {
  if (!start || !end) return "—";
  const s = Math.max(0, Math.round((Date.parse(`${end}Z`) - Date.parse(`${start}Z`)) / 1000));
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} m ${String(s % 60).padStart(2, "0")} s`;
}

export function shortModel(provider: string): string {
  return provider.replace(/^openai\//, "");
}

/** Pipeline stages, derived from what the API already holds for a running audit. */
export function stages(a: Audit): { label: string; done: boolean }[] {
  const s = a.score_summary;
  return [
    { label: "Crawl", done: a.page_count > 0 },
    { label: "Checks", done: s.seo !== undefined },
    { label: "Agent tests", done: s.task_success !== undefined },
    { label: "AI visibility", done: s.visibility !== undefined },
    { label: "Fixes and verdict", done: Boolean(a.verdict?.priority) },
  ];
}
