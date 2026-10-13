# AI Lead Pipeline — Architecture & Handoff

> **Single source of truth** for how the system works. Team members and AI
> agents should read this first and **keep it updated** whenever a feature
> changes. Deep design rationale lives in
> [`ARCHITECTURE_SOURCE.txt`](ARCHITECTURE_SOURCE.txt); GTM context in
> [`EXECUTIVE_PRODUCT_GTM_STRATEGY.md`](EXECUTIVE_PRODUCT_GTM_STRATEGY.md).
>
> Last updated: 2026-07-25.

---

## 1. What this is

A deterministic orchestrator that turns discovered or imported businesses into
**verified leads → personalized preview websites → proposals → controlled
outreach**. Pilot vertical: beauty/wellness in Porto, Lisbon, Braga.

The guiding idea: **AI fills structured content, never rewrites code.** Preview
sites are produced by injecting a per-lead `SITE_CONFIG` into a fixed, audited
template — so every preview is on-brand, safe, and cheap.

## 2. Non-negotiable invariants

These hold everywhere. Break one and you break the product's trust model.

1. **Facts are never invented.** Every fact on a preview comes from stored
   `Evidence` with a `source_url` and `confidence`. Low confidence (< 0.7)
   blocks the build and routes to human review.
2. **No send without approval + consent + suppression check.** WhatsApp only on
   opt-in; max 4 touches; any reply/opt-out/bounce halts the sequence.
3. **Every state transition writes an immutable `Event`** (actor, reason, config
   version, correlation id, idempotency key).
4. **Prices live only in the versioned Pricebook** (YAML), never in code or
   prompts.
5. **Idempotency.** Re-imports/webhooks/reruns never duplicate; a failed
   `SourceRun` resumes from checkpoint.
6. **Previews are `noindex`, time-limited, and torn down**, and carry an
   "unofficial concept" disclaimer.

## 3. End-to-end flow

```
discover / import           adapters/ (google_places, csv_import, directory_seed)
  → normalize + dedupe      services/ingestion.py, services/dedupe.py
  → enrich + evidence       services/enrichment.py  (+ web_crawler, brand_extractor)
  → evidence-grounded AI    services/research_agent.py (fallback when offline)
  → FitQL score + tier      services/scoring.py       (thresholds 75 / 55, Tier A/B)
  → shortlist
  ── human gate: Approve preview ──
  → ContentPack (AI copy)   services/ai_agent.py      (deterministic fallback = $0)
  → SiteConfig (mapping)    services/content_mapping.py
  → template + deploy + QA  services/site_factory.py, adapters/hosting.py
  → preview_ready
  → personalized outreach   services/outreach.py
  ── human gate: Approve outreach ── → mark sent
```

Slow work is queueable without changing the business flow:

```
FastAPI request → ID-only task payload → Celery/Valkey queue
  → worker-owned DB session → PipelineJob status/result → operator dossier
```

`TASK_QUEUE_MODE=inline` is the safe default for a local checkout. Production
uses `celery` for crawl/research, preview, QA, and configured discovery tasks.

Lifecycle states and guards: [`app/core/state_machine.py`](../app/core/state_machine.py).
Immutable log + transitions: [`app/services/events.py`](../app/services/events.py).

## 4. Layout

```
app/
  core/         schemas.py (contracts), state_machine.py
  adapters/     google_places, csv_import, directory_seed, hosting (deploy)
  services/     ingestion, dedupe, enrichment, brand_extractor, web_crawler,
                scoring, ai_agent, content_mapping, site_factory, rendered_qa,
                proposal, outreach, events, config_loader, analytics,
                task_queue, artifact_storage, research_agent
  main.py       FastAPI control plane · ui.py operator UI
config/         versioned config (NOT code): markets, scoring, pricebook,
                messaging, templates — each domain: vN.yaml (immutable) + ACTIVE
templates/      Jinja renderers used for OFFLINE QA only (see §6)
site_templates/ real deployable Next.js templates, one per niche family (§7)
site_template/  legacy single wellness template
tests/          pytest suite
docs/           this file + runbooks
```

## 5. Website factory (the core feature)

`services/site_factory.py` → `run_preview_pipeline()`:

1. Pick template by `business.category` from `config/templates` (§6).
2. `content_mapping.generate_mapped_content()`:
   - build a `BusinessProfile` from evidence,
   - resolve theme = niche defaults **overlaid with the lead's extracted brand**
     (`brand_theme_from_profile`, §8),
   - `ai_agent.generate_content_pack()` fills a **`ContentPack`** (hero,
     services, cta, contact, seo) — deterministic without `OPENAI_API_KEY`,
   - map to a **`SiteConfig`** (facts + brand + logo/hero/colors).
3. Deploy via the hosting adapter (§6) injecting `SITE_CONFIG`.
4. **QA gate** (`run_qa` + `rendered_qa.validate_rendered_preview`): required
   sections present, contact links work, booking form submits, no placeholders,
   **no invented social proof**, unofficial disclaimer, responsive. Fails →
   `failed` (never shipped).
5. `preview_ready`, with 30-day expiry + teardown.

Key contracts in [`app/core/schemas.py`](../app/core/schemas.py): `SourcedFact`,
`ServiceItem`, `SiteConfig`, `ContentPack`, `BusinessProfile`, `QAResult`.

## 6. Template registry & hosting (multi-niche)

**Registry:** [`config/templates/v2.yaml`](../config/templates/v2.yaml) (active).
Two blocks:

- `templates:` — one manifest per template id: `deploy_key`, `local_renderer`
  (Jinja file for offline QA), `source_dir` (real Next.js app), `status`
  (`live`/`pending`), `required_sections`.
- `categories:` — maps `business.category` → `{id, version, theme}`.

Current coverage:

| Category | Template id | Status |
|---|---|---|
| massage_wellness, spa, cosmetology, beauty_aesthetics | `massage-spa-template` | live (kaapora-derived) |
| dental | `dental-next-template` | pending |
| coach_trainer | `coach-next-template` | pending |
| default | `wellness-next-template` | live |

**Hosting adapters** ([`app/adapters/hosting.py`](../app/adapters/hosting.py)):

- **`LocalStubAdapter`** — renders the manifest's `local_renderer` (a Jinja
  file under `templates/`) to a static HTML artifact. **This is for offline
  browser QA and local smoke tests only — it is NOT the shipped preview.** It is
  an approximation of the real template.
- **`VercelAdapter`** — deploys the **real Next.js template** with `SITE_CONFIG`
  injected. Routes each template to its own Vercel project via
  `VERCEL_TEMPLATE_PROJECTS` (JSON: `{deploy_key: {project_id, github_repo_id,
  git_ref}}`); unmapped templates fall back to the default project.

> **The shipped, customer-facing preview is always the real Next.js template on
> Vercel.** The Jinja renderer only exists so QA can run without a Node build.

## 7. Real templates (`site_templates/`)

Each niche family is a self-contained Next.js app, **copied** into the pipeline
(never edited in a client's production repo). It reads `SITE_CONFIG` and renders
the lead's data in that design.

- **`site_templates/massage-spa/`** — kaapora-derived (terracotta/sage design
  system, Playfair/Inter, glass cards, bilingual PT/EN). SITE_CONFIG adapter:
  - `src/lib/preview-config.ts` — parses `SITE_CONFIG` → typed `LeadOverlay`
    (read once at module load; each lead = its own deployment). Returns `null`
    without the env var, so the template's built-in defaults render unchanged.
  - `src/lib/dictionaries.ts` — overlays lead data as `dict.lead`, passed to
    client components via props (avoids server-env-in-client bugs).
  - `app/[lang]/layout.tsx` — injects the lead's brand palette into the
    `hsl(var(--token))` system, renders the unofficial-preview banner + noindex,
    and forces framer-motion entrance states settled in preview (so a preview
    reads as complete instantly, no scroll dependency).
  - Components (`HeroSection`, `PricingClient`, `LocationClient`, `NavbarClient`,
    `StickyCTA`, `page.tsx`) prefer lead data when a preview overlay is present.
  - See `site_templates/massage-spa/PIPELINE_TEMPLATE.md`.

## 8. Brand extraction (makes previews look like the lead)

[`app/services/brand_extractor.py`](../app/services/brand_extractor.py), called
from `enrichment._enrich_live_website` on the already-crawled homepage HTML.
Pulls, with confidence + source:

- **logo** — og:logo → header `<img class=logo>` → apple-touch-icon,
- **brand colors** — `theme-color` meta, `--primary/--brand/--accent` CSS vars,
  most-frequent vibrant hues (neutrals filtered),
- **hero image** — og:image → hero-flagged `<img>`.

Stored as evidence (`logo_url`, `primary_color`, `accent_color`, `brand_colors`,
`hero_image_url`), overlaid onto the template theme so buttons/accents/logo/hero
match the lead's real identity. Pure/deterministic, no new deps.

**Known gaps (improvement backlog):** colors declared only in *external*
stylesheets aren't read yet (extractor reads inline `<style>` + `theme-color`);
JS-rendered (client-side) sites yield thin static HTML. See §12.

## 9. Configuration (versioned, not code)

`config/<domain>/vN.yaml` is immutable; an `ACTIVE` marker selects the live
version; historical runs keep the version string they used. Domains: `markets`,
`scoring`, `pricebook`, `messaging`, `templates`. Publish/rollback via
`services/config_loader.set_active`.

## 10. Cost model

Per lead, the only paid step is the optional copy generation
(`gpt-4o-mini`, ~cents, capped by `PER_LEAD_TOKEN_BUDGET`) — and it's **$0** with
the deterministic fallback (no `OPENAI_API_KEY`). Discovery, enrichment, brand
extraction, mapping, QA and local render are free. Real hosting builds run on
Vercel (platform cost, not tokens). **Do not build templates locally per lead —
let Vercel compile on push.**

> **Release 1 update:** the preceding cost model is superseded by the actual
> runtime ledger. Optional research, preview copy, and outreach copy use the
> configured structured-output model (`gpt-4o-mini` by default). Each call
> records provider request ID, token usage, latency, and estimated cost in
> `AIUsageLedger`; the per-lead spend ceiling defaults to `$0.25`. Without
> `OPENAI_API_KEY`, these steps use deterministic fallbacks at `$0` model cost.

## 11. Artifact storage and retention

PostgreSQL stores artifact metadata only. Private bytes are stored through
`services/artifact_storage.py`:

| Environment | Backend | What is stored |
|---|---|---|
| Local development | private filesystem | screenshots and proposal JSON artifacts |
| Staging / production | Cloudflare R2 private bucket | QA screenshots, proposal documents, exports, and evidence captures |

Every artifact has a storage key, SHA-256, content type, byte size, business /
build association, expiry date, and deletion timestamp. The operator API issues
short-lived signed R2 downloads; there are no permanent public evidence URLs.
`ARTIFACT_RETENTION_DAYS=90` is the current default. Raw crawl captures must
use a shorter, explicit retention policy (recommended: 30 days).

### Proposal PDF template

The active renderer recreates the owner-approved four-page Skylix/Kaapora
proposal using versioned `pricebook/v2` data. The canonical visual reference is
[`assets/proposal/skylix-proposal-master.pdf`](../assets/proposal/skylix-proposal-master.pdf).
See [Proposal template policy](PROPOSAL_TEMPLATE.md). A source-PDF overlay via
PyMuPDF/pypdf is a future pixel-matching enhancement; it is not yet the active
renderer and must retain the same evidence and artifact controls.

## 12. Running & testing

- Full suite: `python -m pytest` (see [`TESTING.md`](TESTING.md)).
- Provider-backed local package check: `python scripts/verify_ai_e2e.py` with a
  disposable SQLite `DATABASE_URL`, local artifacts/hosting, and a configured
  OpenAI or OpenRouter key. It never sends outreach and fails if every provider
  call falls back; see [`TESTING.md`](TESTING.md).
- Verify a real template compiles: `cd site_templates/<name> && npm run typecheck`
  (fast; skip local `next build` — Vercel builds on deploy).
- Local end-to-end preview (offline, $0): ingest → `enrich_business` →
  `run_preview_pipeline`; artifact lands in `artifacts/local_previews/`.
- Runbooks: [`RELEASE1_RUNBOOK.md`](RELEASE1_RUNBOOK.md),
  [`PRODUCTION_DEPLOYMENT.md`](PRODUCTION_DEPLOYMENT.md).

## 13. Adding a new niche template (team/AI runbook)

1. Build/copy a Next.js app into `site_templates/<niche>/`. Add a
   `src/lib/preview-config.ts` adapter that reads `SITE_CONFIG` and returns
   `null` when absent (keep built-in defaults working).
2. Add a Jinja `local_renderer` under `templates/` for offline QA (keep the
   `data-qa` hooks: `hero`, `services`, `contact`, `disclaimer`; a
   `booking-form`; `data-qa-link` on tel/mailto/whatsapp).
3. Register both in `config/templates/vN.yaml` (`templates:` manifest +
   `categories:` routing + a theme), publish via `ACTIVE`.
4. Create the Vercel project from the app dir; add it to
   `VERCEL_TEMPLATE_PROJECTS`.
5. Add tests mirroring `tests/test_multi_template.py`.

## 14. Done, next, and operating boundary

### Done in Release 1

- Lawful CSV/manual ingestion and official Google Places API discovery; no
  Google Maps HTML scraping.
- Bounded website crawler: robots handling, strict timeouts/retries, limited
  page budget, canonicalization, JSON-LD, contacts/services/booking/gap
  extraction, evidence excerpts and confidence.
- Evidence-grounded research agent with human-review routing for conflicts and
  missing facts; unified across CSV, seed, and Places lead flows.
- FitQL scoring, shortlist tiers, explicit approve/reject/suppress gates,
  outcome capture, and idempotent lead asset packages.
- Rendered desktop/mobile preview QA with screenshots, form interception, and
  explicit unofficial-preview checks.
- Private artifact registry plus R2-compatible storage; R2 connectivity has
  been verified with a private upload, signed read, integrity check, and
  cleanup.
- Deterministic branded proposal PDFs registered as private `proposal_pdf`
  artifacts, idempotently linked to proposals and available through the
  authenticated dossier download path, using the owner-approved four-page
  Skylix/Kaapora format and `pricebook/v2`.
- API + PostgreSQL + Valkey + Celery worker production topology; ID-only queue
  payloads and durable `PipelineJob` status tracking.

### Next, in this order

1. **Provision production runtime:** managed PostgreSQL, Valkey, production
   domain/TLS, R2 credentials, Vercel project mappings, monitoring and backup /
   restore drills.
2. **Run a controlled real-lead cohort:** 10–20 lawful Portugal business records;
   inspect every dossier; manually approve the first preview and outreach
   packages; capture every outcome to calibrate FitQL and messaging.
3. **Scale safely:** persist discovery queries for fully asynchronous Places
   discovery; add queue dashboard/dead-letter controls, retry alerts, and R2
   lifecycle cleanup scheduling.
4. **Improve crawl coverage:** opt-in browser fallback for JavaScript-rendered
   websites and linked stylesheet/logo color extraction, still bounded and
   evidence-first.

## 15. Roadmap / open items

- **coach-next-template** (scaffold from the Tiago design as a *copy*; drop
  hardcoded testimonials — they'd violate the no-invented-social-proof gate).
- **dental-next-template** (new; regulated vertical — extra care on treatment /
  before-after claims).
- **Brand color extraction v2**: fetch linked stylesheets + sample the logo's
  dominant color (§8 gap).
- Optional: `render_lead_preview` helper to boot the real template locally for a
  given lead so the Jinja proxy is never mistaken for the product.
