# AgentRank dashboard

Next.js 15 (App Router) front end for the AgentRank API in `../backend`. It proxies `/api/*` and
`/storage/*` to the backend (`AGENTRANK_API_URL`, default `http://localhost:8000`), so the session cookie
is same-origin and no CORS setup is needed.

```sh
npm install
npm run dev        # http://localhost:3000, with the backend running on :8000
```

## Accounts

Sign up at `/register`, sign in at `/login`. Passwords are hashed with scrypt; the session is an httpOnly
cookie (30 days). Every audit belongs to the account that ran it. Audits made before accounts existed are
given to the first account registered. `middleware.ts` sends signed-out visitors to `/login`; the API
checks the session on every request.

## Screens

- **Projects** (`/`): your projects as cards (colour, average Agent-Ready, sites, last audit) and totals.
  New project opens a dialog with a name, description and colour.
- **Project** (`/projects/[id]`): audit a website into this project, its average score, each website's
  latest audit as a card, and the project's audit history. Edit renames or recolours it; an empty project
  can be deleted. Audits made before projects existed are placed in your first project.
- **All audits** (`/audits`): every audit across projects, filterable by project, and what each module
  measures.
- **Audit** (`/audits/[id]`): live progress while it runs, then tabs:
  - Overview: verdict with an animated gauge and the estimate after fixes, an interactive SEO-vs-agents
    quadrant, module scores (click one to see its checks), fixes ranked by impact, agent replays, and the
    sites AI assistants recommend instead
  - Fixes: each fix in an accordion with copy, and the projected scores
  - Agent replays: every step's screenshot in a filmstrip; click to open a lightbox (arrow keys, Esc)
  - AI visibility: rates, every question with each model's answer, competitors
  - Checks: every check behind a module's score, with how to fix it
  - Site map: the crawled site as an interactive 3D graph (drag, zoom, click a page), coloured by how much
    content is readable without JavaScript, plus every page and the files agents look for
- **Scoring rubric** (`/rubric`): weights per site type, from the API.
- **Command palette**: Ctrl+K (Cmd+K on a Mac) anywhere: paste a URL to audit it, or jump to a site.

## Design

Utilitarian minimalism: warm monochrome (`#FBFBFA` canvas, `#EAEAEA` hairlines), Newsreader for headings
and figures, Geist for text, Geist Mono for URLs and code, washed pastels only for status. Icons from
Phosphor (bold). Motion is opacity and transform only, revealed with IntersectionObserver, and switched
off under `prefers-reduced-motion`. 3D uses three.js through @react-three/fiber and drei, loaded only on
the screens that use it.
