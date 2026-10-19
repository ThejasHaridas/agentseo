"""Agent task testing (FR-20..FR-22): an LLM browser agent tries real tasks on the site.

The agent sees a compact, numbered list of the page's interactive elements (roughly what a browser
agent reads from the accessibility tree) plus a short text excerpt, and picks one action per step.

Safety: the browser aborts every non-GET request except add-to-cart calls, so the agent can fill forms
and use a cart but never submit a booking, order, payment, sign-up or message to a real business.
For transactional tasks, "success" means it reached a filled form or checkout step ready to submit.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from app import llm
from app.config import settings
from app.modules.base import AuditContext, Check, ModuleResult

log = logging.getLogger(__name__)

_OBSERVE_JS = r"""
() => {
  const sel = 'a[href], button, input:not([type=hidden]), select, textarea, summary, ' +
              '[role=button], [role=link], [role=tab], [role=menuitem], [role=checkbox], [role=radio], ' +
              '[role=combobox], [role=option], [contenteditable=true]';
  const vh = window.innerHeight;
  const labelFor = el => {
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return l.innerText; }
    const p = el.closest('label'); return p ? p.innerText : '';
  };
  const clean = t => (t || '').replace(/\s+/g, ' ').trim().slice(0, 60);
  document.querySelectorAll('[data-ar-id]').forEach(e => e.removeAttribute('data-ar-id'));
  const found = [];
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    if (r.width <= 0 || r.height <= 0 || s.visibility === 'hidden' || s.display === 'none' || el.disabled) continue;
    // In-viewport elements first, then the nearest ones below/above, so scrolling changes what the agent sees.
    const dist = r.bottom < 0 ? -r.bottom + vh : r.top > vh ? r.top - vh : 0;
    found.push({el, dist, inView: dist === 0});
  }
  found.sort((a, b) => a.dist - b.dist);
  const items = [];
  found.slice(0, 60).forEach(({el, inView}, i) => {
    const id = i + 1;
    el.setAttribute('data-ar-id', id);
    const tag = el.tagName.toLowerCase();
    const role = el.getAttribute('role') || (tag === 'a' ? 'link' : tag === 'input' ? (el.type || 'text') : tag);
    const img = el.querySelector('img[alt]');
    const name = clean(el.getAttribute('aria-label') || labelFor(el) || el.innerText ||
                       el.getAttribute('placeholder') || el.getAttribute('title') || (img && img.alt) ||
                       el.getAttribute('name') || el.value);
    let extra = inView ? '' : ' (offscreen)';
    if (tag === 'select') extra += ' options: ' + [...el.options].slice(0, 10).map(o => clean(o.text)).join(' | ');
    else if ((tag === 'input' || tag === 'textarea') && el.value) extra += ` value="${clean(el.value)}"`;
    items.push(`[${id}] ${role} "${name}"${extra}`);
  });
  const main = document.querySelector('main, [role=main]') || document.body;
  const text = (main.innerText || '').replace(/\s+/g, ' ').trim();
  const maxScroll = Math.max(1, document.documentElement.scrollHeight - vh);
  const frac = Math.min(1, window.scrollY / maxScroll);
  const start = Math.max(0, Math.floor(frac * Math.max(0, text.length - 900)));
  return {title: document.title, url: location.href, elements: items, total_elements: found.length,
          scroll: Math.round(frac * 100), at_bottom: window.scrollY >= maxScroll - 5,
          text: text.slice(start, start + 900)};
}
"""

_ACTIONS = ["click", "type", "select", "press_enter", "scroll_down", "go_back", "done", "give_up"]

_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string", "description": "One short sentence: what you see and why this action."},
        "action": {"type": "string", "enum": _ACTIONS},
        "element_id": {"type": "integer", "description": "Target element number, or -1 if the action has none."},
        "text": {"type": "string", "description": "Text to type or option to select; empty otherwise."},
        "success": {"type": "boolean", "description": "For done/give_up: whether the task was accomplished."},
        "answer": {"type": "string", "description": "For done: the answer found or the state reached. For give_up: what blocked you."},
    },
    "required": ["thought", "action", "element_id", "text", "success", "answer"],
    "additionalProperties": False,
}

_SYSTEM = """You are a browser agent testing how usable a website is for AI agents acting on behalf of a customer.
Each turn you get the current page (title, URL, numbered interactive elements, a text excerpt) and your past actions.
Choose ONE action:
- click(element_id), type(element_id, text), select(element_id, text = option label), press_enter(element_id)
- scroll_down (reveal more of the page), go_back
- done(success=true, answer=...) when the task is accomplished
- give_up(success=false, answer=...) when you are blocked (login wall, CAPTCHA, missing information, broken flow)

Rules:
- Information tasks (find hours, price, contact, docs): done when you have the answer; put it in `answer`.
- Transactional tasks (book, buy, sign up, contact): fill in the form with the test details below and stop at the final
  submit step. Form submissions are blocked in this test browser. Reaching a filled, ready-to-submit form is success.
- Test details: name "Alex Test", email "agent-test@example.com", phone "+1 555 0100", party size 2,
  any date about two weeks ahead. Never enter payment card details and never create accounts or log in.
- Prefer the site's own navigation and search. Elements marked (offscreen) can still be clicked directly.
- If an action caused "no visible change", do not repeat it; try something else or give up.
- If the site lacks what the task needs (no basket, no booking, info not published), give up and say so.
- Be efficient: you have a limited number of steps."""

# Writes that only change a shopping cart are harmless and needed to test e-commerce flows.
_CART_WRITE = re.compile(r"/(cart|basket|bag)(/|\.js|$)|add[-_]?to[-_]?(cart|basket|bag)", re.I)
_COMMIT_WORDS = re.compile(r"checkout|payment|pay|order|confirm|book|reserv|subscribe|register|signup|login|contact", re.I)

_SUBMIT_BLOCKED_NOTE = "Note: a form submission was blocked by the test browser (expected)."


@dataclass
class RunResult:
    task: str
    run_no: int
    success: bool = False
    answer: str = ""
    failure_reason: str | None = None
    steps: list[dict] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    tokens: dict = field(default_factory=dict)
    seconds: float = 0.0
    blocked_submits: int = 0


def choose_tasks(ctx: AuditContext, classification: dict) -> list[str]:
    tasks = [t for t in ctx.tasks if t.strip()] or list(classification.get("key_tasks") or [])
    return tasks[: settings.agent_max_tasks]


def run(ctx: AuditContext, classification: dict, out_dir: Path) -> tuple[list[RunResult], ModuleResult]:
    tasks = choose_tasks(ctx, classification)
    if not tasks or not llm.enabled() or not settings.agent_tests_enabled:
        reason = "no tasks given or suggested" if llm.enabled() else "no LLM key configured"
        check = Check("agent_tests.success_rate", "Agents can complete key tasks", "na", 1, detail=f"Skipped: {reason}.")
        return [], ModuleResult("task_success", [check])

    out_dir.mkdir(parents=True, exist_ok=True)
    start_url = ctx.home.url if ctx.home else ctx.base_url
    results: list[RunResult] = []
    with _Browser() as browser:
        for t_idx, task in enumerate(tasks):
            for run_no in range(1, settings.agent_runs_per_task + 1):
                result = run_task(browser, start_url, task, run_no, out_dir / f"t{t_idx}r{run_no}")
                log.info("agent task %r run %d: success=%s steps=%d", task, run_no, result.success, len(result.steps))
                results.append(result)
    checks = [_task_check(task, [r for r in results if r.task == task]) for task in tasks]
    rate = sum(r.success for r in results) / len(results)
    return results, ModuleResult("task_success", checks, score_override=round(100 * rate, 1))


def _task_check(task: str, runs: list[RunResult]) -> Check:
    successes = sum(r.success for r in runs)
    rate = successes / len(runs) if runs else 0.0
    status = "pass" if rate == 1 else "partial" if rate > 0 else "fail"
    reasons = sorted({r.failure_reason for r in runs if r.failure_reason})
    return Check(
        f"agent_tests.{re.sub(r'[^a-z0-9]+', '_', task.lower())[:40]}",
        f"Agent can: {task}", status, 1, "critical",
        detail=f"Succeeded in {successes}/{len(runs)} runs." + (f" Failures: {'; '.join(reasons)[:300]}" if reasons else ""),
        evidence={"success_rate": round(rate, 2), "runs": [
            {"run_no": r.run_no, "success": r.success, "steps": len(r.steps), "answer": r.answer[:300],
             "failure_reason": r.failure_reason, "stuck_at": r.steps[-1]["url"] if r.steps and not r.success else None}
            for r in runs]},
        fix_hint="Replay the failed run: the last step shows where the agent got stuck.",
    )


class _Browser:
    def __enter__(self):
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch()
        return self

    def new_context(self):
        context = self.browser.new_context(user_agent=settings.user_agent, viewport={"width": 1280, "height": 900},
                                           accept_downloads=False)
        return context

    def __exit__(self, *exc):
        self.browser.close()
        self._pw.stop()


def run_task(browser: _Browser, start_url: str, task: str, run_no: int, out_dir: Path) -> RunResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    result = RunResult(task=task, run_no=run_no)
    context = browser.new_context()
    page = context.new_page()

    def guard(route):
        # Never let the agent submit anything to a real business; cart updates are the one exception.
        req = route.request
        if req.method in ("GET", "HEAD", "OPTIONS") or _is_cart_write(req):
            route.continue_()
        else:
            if route.request.resource_type in ("document", "xhr", "fetch"):
                result.blocked_submits += 1
            route.abort()

    context.route("**/*", guard)
    started = time.monotonic()
    history: list[str] = []
    try:
        page.goto(start_url, wait_until="domcontentloaded", timeout=settings.request_timeout_s * 1000)
        _settle(page)
        for step in range(1, settings.agent_max_steps + 1):
            obs = page.evaluate(_OBSERVE_JS)
            shot = out_dir / f"step{step:02d}.jpg"
            page.screenshot(path=str(shot), type="jpeg", quality=50)
            result.screenshots.append(str(shot))

            blocked_before = result.blocked_submits
            decision = llm.complete_json(
                _SYSTEM, _prompt(task, obs, history, step, blocked_before), _SCHEMA, name="agent_action",
                model=settings.agent_model, usage=result.tokens,
            )
            record = {"n": step, "url": obs["url"], "title": obs["title"], **decision, "error": None}
            result.steps.append(record)

            action = decision["action"]
            if action in ("done", "give_up"):
                result.success = action == "done" and decision["success"]
                result.answer = decision["answer"]
                if not result.success:
                    result.failure_reason = decision["answer"] or "agent gave up"
                break
            try:
                _act(page, action, decision["element_id"], decision["text"])
                _settle(page)
                if action in ("click", "press_enter", "scroll_down", "go_back") and                         _fingerprint(page.evaluate(_OBSERVE_JS)) == _fingerprint(obs):
                    record["error"] = "no visible change"
            except Exception as exc:  # noqa: BLE001  a failed action is information for the next step
                record["error"] = str(exc).splitlines()[0][:200]
            history.append(_describe(step, decision, obs, record["error"]))
        else:
            result.failure_reason = f"did not finish within {settings.agent_max_steps} steps"
    except llm.LLMUnavailable as exc:
        result.failure_reason = f"LLM error: {exc}"
    except Exception as exc:  # noqa: BLE001
        log.warning("agent run failed: %s", exc)
        result.failure_reason = f"browser error: {str(exc).splitlines()[0][:200]}"
    finally:
        result.seconds = round(time.monotonic() - started, 1)
        context.close()
    return result


def _is_cart_write(req) -> bool:
    url = req.url.split("?")[0]
    try:
        body = req.post_data or ""
    except Exception:  # noqa: BLE001  binary bodies
        body = ""
    target = url + " " + body[:500]
    return bool(_CART_WRITE.search(target)) and not _COMMIT_WORDS.search(urlparse(url).path)


def _fingerprint(obs: dict) -> tuple:
    return obs["url"], obs["scroll"], tuple(obs["elements"][:30]), obs["text"][:200]


def _settle(page) -> None:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        page.wait_for_load_state("networkidle", timeout=2500)
    except Exception:  # noqa: BLE001
        pass


def _prompt(task: str, obs: dict, history: list[str], step: int, blocked: int) -> str:
    parts = [
        f"TASK: {task}",
        f"Step {step} of {settings.agent_max_steps}.",
        "PAST ACTIONS:\n" + ("\n".join(history[-8:]) or "(none)"),
    ]
    if blocked:
        parts.append(_SUBMIT_BLOCKED_NOTE)
    parts += [
        f"PAGE: {obs['title']} | {obs['url']} | scrolled {obs['scroll']}%" + (" (bottom)" if obs["at_bottom"] else ""),
        "ELEMENTS:\n" + "\n".join(obs["elements"]) if obs["elements"] else "ELEMENTS: (none visible)",
        f"TEXT: {obs['text']}",
    ]
    return "\n\n".join(parts)


def _describe(step: int, d: dict, obs: dict, error: str | None) -> str:
    target = next((e for e in obs["elements"] if e.startswith(f"[{d['element_id']}] ")), "") if d["element_id"] >= 0 else ""
    text = f' "{d["text"]}"' if d["text"] else ""
    outcome = f" -> {error}" if error == "no visible change" else f" -> FAILED: {error}" if error else ""
    return f"{step}. {d['action']} {target[:90]}{text} on {urlparse(obs['url']).path or '/'}{outcome}"


def _act(page, action: str, element_id: int, text: str) -> None:
    if action == "scroll_down":
        page.evaluate("window.scrollBy(0, Math.round(window.innerHeight * 0.8))")
        return
    if action == "go_back":
        page.go_back(timeout=10000)
        return
    if element_id < 0:
        raise ValueError(f"{action} needs an element_id")
    el = page.locator(f'[data-ar-id="{element_id}"]').first
    if action == "click":
        el.click(timeout=5000)
    elif action == "type":
        el.fill(text, timeout=5000)
    elif action == "select":
        el.select_option(label=text, timeout=5000)
    elif action == "press_enter":
        el.press("Enter", timeout=5000)
