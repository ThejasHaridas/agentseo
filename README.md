# AgentRank

Audits a website for classic SEO and for AI agents (readability, actionability, task success, AI visibility).
Requirements: https://claude.ai/artifact/MPHR11WYUyuAa8apKLcLDR

## Status

Days 1–9 of the two-week plan (backend complete; dashboard next):

- Crawler: raw HTML + JS-rendered DOM, robots.txt, sitemaps, llms.txt, /.well-known/ files, OpenAPI specs
- Modules (`backend/app/modules/`): classic SEO + PageSpeed, agent readability, agent actionability
- Site-type classifier: type, brand, location and likely agent tasks (LLM, schema-based fallback without a key)
- Agent task testing: an LLM browser agent runs the owner's tasks (or suggested ones) with per-step
  screenshots, tokens and timing. Its browser blocks every non-GET request except add-to-cart, so it never
  submits a booking, order, payment or message to a real business.
- AI visibility: generated customer questions answered by Groq models with web search; mention, citation
  and share-of-voice rates with 95% intervals, plus the competitors recommended instead
- Scoring rubric v0.1 (`backend/app/scoring.py`); every score stores its contributing checks
- Verdict (`backend/app/verdict.py`): Critical / Recommended / Low priority, the factors behind it, and
  projected scores if the fixes are applied
- Fixes (`backend/app/fixes.py`): ready-to-paste llms.txt, JSON-LD, robots.txt, sitemap.xml, head tags,
  titles/descriptions and accessibility fixes, each linked to the findings it resolves

- Dashboard (days 10–11, `frontend/`): Next.js app with the audits list, the audit screen (verdict,
  fixes with copy, agent replays, AI visibility, checks, pages) and the scoring rubric. See `frontend/README.md`.

Next: testing on 10–15 real sites and calibrating weights (days 12–14).

Run both: the backend on :8000 (below), then `cd frontend && npm install && npm run dev` and open
http://localhost:3000.

LLM calls go through `backend/app/llm.py` (any OpenAI-compatible endpoint), so switching provider is a config
change: `AGENTRANK_LLM_BASE_URL`, `AGENTRANK_LLM_MODEL`, `AGENTRANK_LLM_API_KEY` (or `GROQ_API_KEY`).

### Groq free-tier budget

gpt-oss-120b and gpt-oss-20b each allow 8K tokens/minute and 200K/day. A full audit uses roughly
30–50K tokens for agent tests and 20–80K for AI visibility (search answers vary from 3K to 25K each).
Per-minute limits are waited out; when a model's daily quota is spent, structured calls fall back to
`AGENTRANK_LLM_FALLBACK_MODEL` and visibility skips that model (recorded per answer), so audits still finish.

## Run (no Docker)

SQLite, with audits run in-process:

```sh
cd backend
uv sync
uv run python -m playwright install chromium
uv run uvicorn app.main:app --reload
```

Then open http://localhost:8000/docs, or:

```sh
curl -X POST localhost:8000/audits -H "content-type: application/json" -d '{"url":"https://example.com"}'
curl localhost:8000/audits/<id>
curl localhost:8000/audits/<id>/pages
curl localhost:8000/audits/<id>/site-files
curl localhost:8000/audits/<id>/scores
curl localhost:8000/audits/<id>/findings
curl localhost:8000/audits/<id>/agent-tests   # screenshots served under /storage
curl localhost:8000/audits/<id>/visibility
curl localhost:8000/audits/<id>/fixes
```

## Run with Postgres + Redis queue

```sh
docker compose up -d
cp backend/.env.example backend/.env   # uncomment the three lines at the top
cd backend
uv run uvicorn app.main:app --reload
uv run celery -A app.worker worker --pool=solo --loglevel=info   # second terminal; solo pool for Windows
```

## Tests

```sh
cd backend && uv run pytest
```
