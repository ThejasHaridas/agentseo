"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { ApiError, signIn, signUp } from "@/lib/api";
import { Mark } from "@/components/ui";

const Globe = dynamic(() => import("@/components/Globe"), { ssr: false, loading: () => null });

export default function AuthScreen({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next");
  const safeNext = next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isLogin = mode === "login";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!isLogin && password.length < 10) { setError("Use at least 10 characters for your password."); return; }
    setBusy(true);
    try {
      if (isLogin) await signIn(email, password); else await signUp(name, email, password);
      router.replace(safeNext);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
      setBusy(false);
    }
  }

  return (
    <main className="auth">
      <section className="auth-form">
        <Link href="/login" className="wordmark" aria-label="AgentRank"><Mark size={26} />AgentRank</Link>
        <h1 className="display" style={{ marginTop: 56, maxWidth: 520 }}>
          {isLogin ? "See your website the way AI agents do." : "Create your AgentRank account."}
        </h1>
        <p className="lede" style={{ marginTop: 16 }}>
          {isLogin
            ? "Audit any site for classic SEO and for AI agents: can they read it, use it, and do they recommend it?"
            : "Your audits, agent replays and fixes stay private to your account."}
        </p>

        <form onSubmit={submit} noValidate>
          {!isLogin && (
            <div className="field">
              <label htmlFor="name">Name</label>
              <input id="name" className="input" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" required />
            </div>
          )}
          <div className="field">
            <label htmlFor="email">Work email</label>
            <input id="email" className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required placeholder="you@agency.in" />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <div style={{ position: "relative" }}>
              <input id="password" className="input" type={show ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)}
                     autoComplete={isLogin ? "current-password" : "new-password"} required minLength={isLogin ? undefined : 10} style={{ paddingRight: 64 }} />
              <button type="button" className="btn ghost sm" onClick={() => setShow((s) => !s)} style={{ position: "absolute", right: 6, top: 7 }}
                      aria-pressed={show}>{show ? "Hide" : "Show"}</button>
            </div>
            {!isLogin && <span className="hint">At least 10 characters.</span>}
          </div>
          {error && <p className="notice red" role="alert">{error}</p>}
          <button className="btn primary" style={{ height: 44 }} disabled={busy || !email || !password || (!isLogin && !name)}>
            {busy ? (isLogin ? "Signing in…" : "Creating account…") : isLogin ? "Sign in" : "Create account"}
          </button>
          <p className="small muted">
            {isLogin ? <>New here? <Link className="link" href={`/register${next ? `?next=${encodeURIComponent(next)}` : ""}`}>Create an account</Link></>
              : <>Already have an account? <Link className="link" href={`/login${next ? `?next=${encodeURIComponent(next)}` : ""}`}>Sign in</Link></>}
          </p>
        </form>
      </section>

      <aside className="auth-art" aria-label="Illustration">
        <Globe />
        <div className="caption"><span>Drag to turn the web</span><span className="mono">1 agent · 6 sites</span></div>
      </aside>
    </main>
  );
}
