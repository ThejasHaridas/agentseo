"""Analysis modules, one per requirements section 4.2-4.7:

seo.py            Classic SEO checks + PageSpeed (FR-5..FR-7)
readability.py    Agent readability: AI bot access, llms.txt, JSON-LD, no-JS ratio, a11y (FR-10..FR-16)
actionability.py  Forms, CAPTCHAs, bot walls, APIs/MCP, anti-agent blockers (FR-17..FR-19)
classify.py       Site type + likely agent tasks (FR-26)
agent_tests.py    LLM browser agent task runs (FR-20..FR-22)
visibility.py     AI visibility across LLM providers (FR-23..FR-25)

Verdict (FR-26..28) lives in app/verdict.py and fix generation (FR-29..32) in app/fixes.py.
"""
