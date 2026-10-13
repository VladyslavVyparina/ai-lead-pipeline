# Production deployment

Last reviewed: 2026-07-25.

Release 1 runs as an API process plus a Celery worker, backed by PostgreSQL and
Valkey. Slow discovery, research, preview, and QA work crosses an ID-only queue
boundary; outbound messages still require explicit human approval.

## Prerequisites

- A Linux host with Docker Engine and Compose
- A TLS reverse proxy for the public API hostname
- Audited Vercel project(s) connected to the applicable `site_templates/`
  application(s), with `VERCEL_TEMPLATE_PROJECTS` mappings for every live
  template
- Official Google Places API credentials, or lawful provider CSV exports
- DNS for the API hostname

## Configure

Use Infisical as the production secret source; see
[SECRETS_OPERATIONS.md](SECRETS_OPERATIONS.md). It injects secrets into Docker
Compose at deployment time, so a production `.env` file is not required. At
minimum, the `prod` environment requires:

```dotenv
POSTGRES_PASSWORD=<url-safe-random-password>
PUBLIC_BASE_URL=https://leads.example.com
ALLOWED_HOSTS=leads.example.com
ADMIN_TOKEN=<random-32-byte-or-longer-token>
INBOUND_WEBHOOK_SECRET=<different-random-token>
R2_ACCOUNT_ID=<cloudflare-account-id>
R2_ACCESS_KEY_ID=<scoped-r2-access-key-id>
R2_SECRET_ACCESS_KEY=<scoped-r2-secret>
R2_BUCKET_PRIVATE=ai-lead-private-prod
ARTIFACT_RETENTION_DAYS=90
TASK_QUEUE_MODE=celery
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=<prod-scoped-key>
OPENROUTER_MODEL=qwen/qwen3-32b
PER_LEAD_TOKEN_BUDGET=0.25
# Optional: required only for official Google Places discovery
GOOGLE_PLACES_API_KEY=<key>
VERCEL_TOKEN=<token>
VERCEL_PROJECT_ID=<project-id>
VERCEL_GITHUB_REPO_ID=<numeric-repository-id>
```

Generate independent secrets with a password manager or:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Restrict the Places key to the required API and restrict the Vercel token to
the deployment project/team. Set `PREVIEW_ORIGIN_REGEX` explicitly if preview
forms are served from domains other than `*.vercel.app`.

## Deploy

```bash
infisical run --env=prod -- docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
curl --fail https://leads.example.com/health
```

The API and worker containers run `alembic upgrade head` before starting.
Production startup refuses SQLite, HTTP public URLs, wildcard hosts, default
secrets, or an incomplete Vercel configuration.

Terminate TLS at the reverse proxy and forward only trusted proxy traffic to
`127.0.0.1:8000`. Set `FORWARDED_ALLOW_IPS` to the proxy container or private
IP. Add edge rate limiting for `/preview-form` before increasing API workers.

## First-lead smoke test

1. Sign in at `/ui/login`.
2. Import `docs/real_leads_import_template.csv` or run the official Places
   connector for a narrow Portugal category/city query.
3. Open the dossier and verify provenance, contacts, evidence, score, and
   warnings.
4. Approve one lead. Confirm the connected package contains a reachable preview
   URL, desktop/mobile screenshots, passed QA, proposal, recipient, recommended
   channel, message draft, and evidence.
5. Approve and mark the draft sent only after human review.
6. Record the reply and commercial outcome beside the original score/message.

## Operations

- Back up the `postgres_data` volume daily and test restores.
- Retain the `qa_artifacts` volume for the evidence period, then purge it under
  the retention policy. In production, the authoritative copies are private R2
  artifacts; the volume is only transient browser-QA workspace.
- Keep the R2 bucket private. The API issues five-minute signed downloads for
  authenticated operators and records object hashes, retention deadlines, and
  deletion state in PostgreSQL.
- Rotate operator, webhook, Google, Vercel, and OpenAI credentials.
- Monitor `/health`, worker health, queue depth, 5xx responses, failed pipeline
  jobs, per-lead AI spend, crawl failures, QA failures, and Vercel deployment
  failures.
- Run only lawful provider exports or official APIs. Do not scrape Google Maps
  HTML.

Rollback application code by deploying the previous image. Database migrations
are forward-applied; take a database backup before every production upgrade.
