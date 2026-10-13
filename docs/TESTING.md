# Testing guide — Release 1

Last reviewed: 2026-07-25. The full Python suite must pass before deployment:

```powershell
py -3.10 -m pytest -q
```

Install browser dependencies once for rendered-preview tests:

```powershell
py -3.10 -m playwright install chromium
```

## Local smoke test

```powershell
py -3.10 run_api.py
Invoke-WebRequest http://127.0.0.1:8000/health | Select-Object -Expand Content
```

Open `/ui/login` and authenticate with the local `ADMIN_TOKEN`. Do not use a
default token outside a private local checkout.

## Required coverage

The test suite covers CSV/provider metadata, official Places adapter behavior,
bounded crawl extraction, evidence and confidence, FitQL, lead gates,
idempotent asset package creation, rendered QA screenshots, template routing,
private artifacts, task queue contracts, outcomes, UI and migrations.

For the real Next.js preview template:

```powershell
Set-Location site_templates/massage-spa
npm ci
npm run typecheck
```

The local Jinja artifact is an offline QA substitute only. Before contacting a
real lead, test a deployed Vercel preview URL through the browser QA gate and
inspect both desktop/mobile screenshots.

## AI-enabled end-to-end verification

Run the controlled local scenario with a temporary SQLite database and an
`OPENROUTER_API_KEY` or `OPENAI_API_KEY` only when a provider call is intended.
For OpenRouter development set `AI_PROVIDER=openrouter` and pin
`OPENROUTER_MODEL=qwen/qwen3-32b`; use `openrouter/free` only for smoke tests. Verify
the ledger records model, request ID, tokens, latency and estimated cost; a
provider error must fall back deterministically rather than inventing facts.

Never use a real contact route or send outreach as part of automated testing.
Use synthetic/local records, inspect the completed dossier, and clean up test
artifacts under the configured retention policy.
