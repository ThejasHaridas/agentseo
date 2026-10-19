"use client";

import { ArrowRight, ChartBar, Folder, Globe as GlobeIcon, ListBullets, MagnifyingGlass, Plus, SignOut } from "@phosphor-icons/react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, Audit, currentUser, host, listProjects, normaliseUrl, Project, score, signOut, startAudit, User } from "@/lib/api";
import { ProjectDialog } from "@/components/projects";
import { initials, Mark } from "@/components/ui";

const UserContext = createContext<User | null>(null);
export const useUser = () => useContext(UserContext);

const PaletteContext = createContext<() => void>(() => {});
export const useOpenPalette = () => useContext(PaletteContext);

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [palette, setPalette] = useState(false);
  const [menu, setMenu] = useState(false);
  const [newProject, setNewProject] = useState(false);
  const router = useRouter();

  useEffect(() => { currentUser().then(setUser).catch(() => {}); }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setPalette((p) => !p); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  useEffect(() => { setMenu(false); setPalette(false); }, [pathname]);

  async function logout() {
    await signOut().catch(() => {});
    router.replace("/login");
    router.refresh();
  }

  const isMac = typeof navigator !== "undefined" && /Mac/i.test(navigator.platform);
  return (
    <UserContext.Provider value={user}>
      <PaletteContext.Provider value={() => setPalette(true)}>
        <header className="topbar">
          <div className="topbar-inner">
            <Link href="/" className="wordmark"><Mark />AgentRank</Link>
            <nav className="nav" aria-label="Main">
              <Link href="/" aria-current={pathname === "/" || pathname.startsWith("/projects") ? "page" : undefined}>Projects</Link>
              <Link href="/audits" aria-current={pathname.startsWith("/audits") ? "page" : undefined}>All audits</Link>
              <Link href="/rubric" aria-current={pathname === "/rubric" ? "page" : undefined}>Scoring rubric</Link>
            </nav>
            <span className="spacer" />
            <button className="cmdk-trigger" onClick={() => setPalette(true)} aria-label="Search or audit a website">
              <MagnifyingGlass size={15} weight="bold" />
              <span className="label">Audit a site or jump to…</span>
              <kbd>{isMac ? "⌘" : "Ctrl"}</kbd><kbd>K</kbd>
            </button>
            <div className="user">
              <button className="user-btn" onClick={() => setMenu((m) => !m)} aria-expanded={menu} aria-haspopup="menu">
                <span className="avatar">{user ? initials(user.name) : ""}</span>
                <span className="name small hide-sm">{user?.name.split(" ")[0] ?? ""}</span>
              </button>
              {menu && (
                <div className="menu" role="menu" onMouseLeave={() => setMenu(false)}>
                  <div className="who"><p className="h3">{user?.name}</p><p className="small muted">{user?.email}</p></div>
                  <Link href="/rubric" role="menuitem"><ChartBar size={16} weight="bold" />Scoring rubric</Link>
                  <button role="menuitem" onClick={logout}><SignOut size={16} weight="bold" />Sign out</button>
                </div>
              )}
            </div>
          </div>
        </header>
        {children}
        {palette && <CommandPalette onClose={() => setPalette(false)} onSignOut={logout} onNewProject={() => { setPalette(false); setNewProject(true); }} />}
        {newProject && <ProjectDialog onClose={() => setNewProject(false)} onSaved={(p) => { setNewProject(false); router.push(`/projects/${p.id}`); }} />}
      </PaletteContext.Provider>
    </UserContext.Provider>
  );
}

interface Item { id: string; group: string; label: React.ReactNode; hint?: string; icon: React.ReactNode; run: () => void | Promise<void> }

function CommandPalette({ onClose, onSignOut, onNewProject }: { onClose: () => void; onSignOut: () => void; onNewProject: () => void }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [audits, setAudits] = useState<Audit[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [active, setActive] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    input.current?.focus();
    api<Audit[]>("/audits").then(setAudits).catch(() => {});
    listProjects().then(setProjects).catch(() => {});
  }, []);

  const go = useCallback((href: string) => { router.push(href); onClose(); }, [router, onClose]);

  const items = useMemo<Item[]>(() => {
    const out: Item[] = [];
    const url = normaliseUrl(q);
    if (url) {
      out.push({
        id: "audit", group: "Audit", icon: <ArrowRight size={16} weight="bold" />,
        label: <>Audit <span className="mono">{host(url)}</span></>, hint: "25 pages · 5–10 min",
        run: async () => {
          setBusy(true); setError(null);
          try { const a = await startAudit(url); go(`/audits/${a.id}`); } catch (e) { setError((e as Error).message); setBusy(false); }
        },
      });
    }
    const term = q.trim().toLowerCase();
    for (const p of projects) {
      if (term && !p.name.toLowerCase().includes(term)) continue;
      out.push({
        id: `p-${p.id}`, group: "Projects", icon: <span className={`swatch-dot c-${p.color}`} style={{ margin: "0 4px" }} />,
        label: p.name, hint: `${p.sites.length} ${p.sites.length === 1 ? "site" : "sites"}`, run: () => go(`/projects/${p.id}`),
      });
    }
    const seen = new Set<string>();
    for (const a of audits) {
      if (seen.has(a.site_id)) continue;
      seen.add(a.site_id);
      if (term && !a.site_url.toLowerCase().includes(term)) continue;
      out.push({
        id: a.id, group: "Sites", icon: <GlobeIcon size={16} weight="bold" />,
        label: <span className="mono">{host(a.site_url)}</span>,
        hint: a.status === "done" ? `Agent-Ready ${score(a.score_summary.agent_ready)}` : a.status,
        run: () => go(`/audits/${a.id}`),
      });
    }
    const nav: Item[] = [
      { id: "new-project", group: "Go to", icon: <Plus size={16} weight="bold" />, label: "New project", run: onNewProject },
      { id: "nav-projects", group: "Go to", icon: <Folder size={16} weight="bold" />, label: "Projects", run: () => go("/") },
      { id: "nav-audits", group: "Go to", icon: <ListBullets size={16} weight="bold" />, label: "All audits", run: () => go("/audits") },
      { id: "nav-rubric", group: "Go to", icon: <ChartBar size={16} weight="bold" />, label: "Scoring rubric", run: () => go("/rubric") },
      { id: "signout", group: "Account", icon: <SignOut size={16} weight="bold" />, label: "Sign out", run: onSignOut },
    ];
    return out.concat(nav.filter((n) => !term || String(n.label).toLowerCase().includes(term)));
  }, [q, audits, projects, go, onSignOut, onNewProject]);

  useEffect(() => setActive(0), [q]);

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "Escape") onClose();
    else if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(items.length - 1, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
    else if (e.key === "Enter" && items[active]) { e.preventDefault(); items[active].run(); }
  }

  let lastGroup = "";
  return (
    <div className="cmdk-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="cmdk" role="dialog" aria-modal="true" aria-label="Command palette" onKeyDown={onKey}>
        <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Paste a website to audit, or search your sites"
               aria-label="Search" spellCheck={false} disabled={busy} />
        <ul role="listbox">
          {items.length === 0 && <li className="group">No matches. Paste a full address like rosastrattoria.in to audit it.</li>}
          {items.map((it, i) => {
            const header = it.group !== lastGroup ? <li key={`g-${it.group}`} className="group" role="presentation">{it.group}</li> : null;
            lastGroup = it.group;
            return [header, (
              <li key={it.id}>
                <button role="option" aria-selected={i === active} onMouseEnter={() => setActive(i)} onClick={() => it.run()}>
                  <span className="faint">{it.icon}</span>
                  <span style={{ flex: 1, minWidth: 0 }}>{it.label}</span>
                  {it.hint && <span className="small faint">{it.hint}</span>}
                </button>
              </li>
            )];
          })}
        </ul>
        {error && <p className="notice red" style={{ margin: "0 12px 12px" }}>{error}</p>}
        <div className="foot"><span><kbd>↑</kbd> <kbd>↓</kbd> move</span><span><kbd>Enter</kbd> open</span><span><kbd>Esc</kbd> close</span>{busy && <span>Starting audit…</span>}</div>
      </div>
    </div>
  );
}
