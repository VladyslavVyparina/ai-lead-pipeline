# Full-stack engineering execution handoff

Last reviewed: 2026-07-25. This is the build queue for completing the AI Lead
Platform. Read [ARCHITECTURE.md](ARCHITECTURE.md) first; it defines the
non-negotiable evidence, consent, suppression, audit and idempotency rules.

## Run and verify locally

```powershell
py -3.10 -m pip install -r requirements.txt
py -3.10 -m playwright install chromium
py -3.10 -m pytest -q
py -3.10 run_api.py
```

For real AI development, use a scoped `OPENROUTER_API_KEY` in local `.env`:

```dotenv
AI_PROVIDER=openrouter
OPENROUTER_MODEL=openrouter/free
# For repeatable cheap tests, set: OPENROUTER_MODEL=qwen/qwen3-32b
PER_LEAD_TOKEN_BUDGET=0.25
```

Run `py -3.10 scripts/verify_ai_e2e.py` with a disposable SQLite database,
local artifacts and Vercel disabled. It never sends outreach and fails unless a
provider-backed AI ledger row exists.

## Feature completion matrix

| Feature | Done now | Finish / next implementation |
|---|---|---|
| Domain core | FastAPI, SQLAlchemy models, state machine, immutable `Event`, idempotency keys and versioned YAML config | Keep every new operation within state/guard/event contracts; add migrations and tests for any persisted field |
| Input and discovery | CSV/manual contract and official Google Places Text Search adapter; provider IDs, ratings, review counts, timestamps | Persist async discovery-query/rate-limit state; add one additional licensed provider only after legal review. Never scrape Google Maps HTML |
| Website enrichment | Bounded crawler, robots/timeout/page/size limits, canonicalization, contacts/services/booking/gap extraction and evidence | Add opt-in browser fallback for JS-heavy sites and linked stylesheet/logo colour extraction while retaining budgets/robots |
| Research AI | Evidence-only structured research, grounding check, deterministic fallback, usage ledger; OpenAI/OpenRouter compatible provider routing | Pin OpenRouter models by environment, add schema-native response format when a chosen model supports it, expose failures/costs in UI |
| FitQL and dossier | Scoring, tiers, review warnings, approve/reject/suppress actions and dossier views | Calibrate weights using actual outcomes; add correction reason and reviewer quality metrics |
| Preview factory | `SITE_CONFIG`, category registry, real Next.js templates, Vercel/local adapters and idempotent build package | Add dental/coach templates only after design/compliance review; never generate a codebase per lead |
| Rendered QA | Browser QA checks identity, sections, links, forms, disclaimer, placeholders, mobile/desktop screenshots | Test a real production Vercel deployment on every template release; add regression screenshot baseline only if it remains stable |
| Proposal and assets | Proposal JSON plus idempotent branded `proposal_pdf`, private local/R2 artifacts, checksums, expiry and authenticated dossier download links; active four-page Skylix/Kaapora renderer from `pricebook/v2` | Add scheduled retention deletion, a branded PDF visual regression check, then an optional PyMuPDF/pypdf source-PDF overlay for pixel matching; see `PROPOSAL_TEMPLATE.md` |
| Outreach and outcomes | Channel/recipient recommendation, draft, human approval, mark-sent, replies/meetings/proposal/won/lost | Keep sending manual for first cohort; add inbound reply/webhook adapters and controlled follow-up workflow after compliance approval |
| Jobs | `PipelineJob`, Celery/Valkey task boundary, ID-only payloads | Production worker deployment, retry classification, queue dashboard, DLQ/replay controls and alerts |
| UI | Server-rendered operator control plane and dossier | Add secure artifact downloads, job status/retry visibility, outcome comparison and reviewer notes; do not rebuild as a CRM |
| Production platform | Docker production topology, Alembic, startup validation, R2-compatible storage | Provision managed PostgreSQL/Valkey, domain/TLS, Vercel mappings, backups/restore drill, monitoring and secret management |

## Delivery order

1. **Provision production safely.** Separate API/worker, managed PostgreSQL,
   Valkey, private R2, Vercel mappings, TLS, secrets, logs/metrics and backups.
2. **Close the customer asset loop.** PDF proposal plus secure artifact links in
   the dossier.
3. **Run the 10–20 business cohort.** Fix observed defects; do not expand scope.
4. **Make operations replayable.** Discovery-query persistence, retries, DLQ,
   monitoring and R2 cleanup.
5. **Improve coverage carefully.** Browser fallback and stylesheets, then a
   second niche template after the first paid pilot.

## Definition of done

- Unit plus failure/guard tests pass; full suite: `py -3.10 -m pytest -q`.
- Persisted changes have an Alembic migration and PostgreSQL verification.
- The operator sees a clear review/failure reason; no silent state changes.
- Facts retain source URL, excerpt, capture time and confidence.
- AI is bounded, structured, cost-recorded and may never invent facts, prices,
  testimonials, credentials or contact details.
- Preview changes preserve `data-qa` hooks, form/link tests, noindex and the
  unofficial-preview disclaimer; run template typecheck and rendered QA.
- Secrets, raw personal data and R2 keys never enter Git, screenshots or logs.

## OpenRouter development policy

Use `openrouter/free` for smoke tests only: availability/model choice can vary
and free limits apply. For repeatable development, pin `qwen/qwen3-32b` first;
its current listed price is low and it is multilingual/structured-output capable.
Keep `PER_LEAD_TOKEN_BUDGET=0.25`, inspect `AIUsageLedger`, and set a lower
OpenRouter project/key spend cap for dev than production. Do not share a personal
root key: issue a distinct, revocable development key with a hard cap.
`AI_REQUEST_TIMEOUT_SECONDS=30` bounds individual provider calls; a timeout is
recorded and falls back safely rather than holding a worker indefinitely.

## Explicit non-goals until paid-pilot evidence

Autonomous cold outreach, cold WhatsApp, multi-tenancy, broad niche/template
expansion, a React CRM rewrite, predictive ML and Cloudflare workflow migration.
