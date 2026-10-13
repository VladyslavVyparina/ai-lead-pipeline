# AI Lead Pipeline

An evidence-first engine for agencies that need a first customer: import lawful business records, check the public website, qualify the lead, and produce a preview, a proposal, and a draft the operator can actually stand behind.

## Problem

Outbound shops were mixing scraped guesses with real contact data and sending pitches that did not match the business. There was no single place that kept the source of a fact, the qualification reason, and the commercial outcome together.

## What was built

Release 1 is a control plane around that pipeline.

- Import of lawful business records and enrichment from verified public sites.
- Qualification that keeps evidence status on each fact instead of one opaque score.
- A preview, proposal, and draft package that stays truthful to what was found.
- A feedback loop from commercial outcomes back into later runs.
- Versioned configuration, migrations, and a production Docker compose file.

Documentation in `docs/` starts with the architecture notes and the Release 1 runbook (dated 2026-07-25 in the source tree).

## How it works

Records enter through importers, are normalized, and are enriched only from sources the pipeline is allowed to use. Qualification writes the reason next to the decision. Preview and proposal generation consume that record rather than a free-form model rewrite. Operators review the package before it is treated as sent. Later outcomes are stored so the next batch can learn what actually converted.

Private artifacts and local databases are not part of this repository.

## Stack

Python, FastAPI, Alembic, Docker, a small Node package for the preview surface.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/python run_api.py
```

## What this public copy leaves out

`.env`, SQLite databases, `private_artifacts`, and virtualenv. Do not point this tree at a production database without filling your own secrets locally.

## Documents

`docs/` holds the architecture note, the Release 1 runbook (dated 2026-07-25 in the source tree), the developer handoff, the production deploy, secrets handling, the proposal template, and the website-factory note. `site_template/README.md` is the Next.js preview: one lead changes `SiteConfig` only, the page is `force-dynamic`, and a missing fact is left off the page. The same testing steps as the AI Lead case apply: pytest, the operator UI on port 8000, and a seeded preview on port 3100. See `docs/TESTING.md` when that file is present in this tree.
