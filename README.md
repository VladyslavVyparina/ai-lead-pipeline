# AI Lead Pipeline

> Current project documentation is dated **2026-07-25**. Start with
> [Architecture](docs/ARCHITECTURE.md), then use the
> [Release 1 runbook](docs/RELEASE1_RUNBOOK.md).

An evidence-first first-customer engine for agencies: import lawful business
records, enrich verified public websites, qualify leads, create a truthful
preview/proposal/draft package, and learn from commercial outcomes.

## Release 1

- Lawful CSV/manual input and official Google Places API discovery—never Google
  Maps HTML scraping.
- Bounded website crawl with robots, strict timeouts, evidence excerpts,
  confidence and review routing.
- FitQL, contactability/suppression/approval gates and immutable events.
- Template-driven Next.js previews, rendered Chromium desktop/mobile QA and
  idempotent preview/proposal/outreach packages.
- Optional structured OpenAI generation with deterministic fallback, token/cost
  ledger and a per-lead spend limit.
- Outcome capture for replies, meetings, proposals, wins, losses and reasons.
- Private R2-compatible artifact storage; production API + PostgreSQL + Valkey
  + Celery topology.

## Quick start (Windows)

```powershell
py -3.10 -m pip install -r requirements.txt
py -3.10 -m playwright install chromium
py -3.10 -m pytest -q
py -3.10 run_api.py
```

Run `npm run dev` to start the API. It uses a private local env file only when
`LOCAL_ENV_OWNER_KEY` is set; otherwise it injects the shared developer secrets
from Infisical. Developers authenticate once with
`infisical login --domain https://eu.infisical.com` and do not need to run
`infisical init`.

```powershell
npm run dev
npm run test:dev
npm run verify:ai
```

Open `http://127.0.0.1:8000/ui`. Set a non-default `ADMIN_TOKEN` in the local
`.env`; never commit `.env` or provider credentials. SQLite is for a single
local developer only.

## Documentation map

- [Architecture and current backlog](docs/ARCHITECTURE.md)
- [Production deployment](docs/PRODUCTION_DEPLOYMENT.md)
- [Release 1 operating runbook](docs/RELEASE1_RUNBOOK.md)
- [Engineering handoff](docs/DEVELOPER_HANDOFF.md)
- [Developer quick start](docs/DEVELOPER_QUICKSTART.md)
- [Technical marketing handoff](docs/TECHNICAL_MARKETER_HANDOFF.md)
- [Testing guide](docs/TESTING.md)
- [Infisical secrets operations](docs/SECRETS_OPERATIONS.md)
- [Proposal template policy](docs/PROPOSAL_TEMPLATE.md)
- [Brand image and logo asset workflow](docs/IMAGE_ASSET_WORKFLOW.md)
- [Website Factory v2 block-constructor plan](docs/WEBSITE_FACTORY_V2.md)
- [CSV contract](docs/real_leads_import_template.csv)

The first goal is a controlled Portuguese wellness cohort and one paid pilot.
Do not add autonomous outreach, a CRM rewrite, multi-tenancy or broad vertical
expansion before real outcomes validate the workflow.
