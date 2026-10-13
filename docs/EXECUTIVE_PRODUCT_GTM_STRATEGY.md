# Executive product and go-to-market strategy

Last reviewed: 2026-07-25.

## Decision

Release 1 is built and merged. Use it internally as an evidence-first sales
engine to win the first paid Portuguese wellness customer. Do not position this
as “an AI website builder”; the commercial offer is a **Booking Conversion
Sprint**: a clearer mobile booking/contact journey with local trust essentials,
analytics and launch support.

The product advantage is the evidence-to-outcome loop: which market segment,
observable gap, preview, offer, channel and message actually lead to replies,
meetings and wins. Generated copy and crawler technology are supporting
capabilities, not the moat.

## Current product capability

| Capability | Release 1 status |
|---|---|
| Input | Lawful CSV/manual import and official Google Places API discovery; no Google Maps HTML scraping |
| Enrichment | Bounded public-website crawl with evidence excerpts, source URL, capture time, confidence and review flags |
| Qualification | FitQL, contactability checks, exclusion warnings, approvals/rejections/suppression and immutable events |
| Asset package | Idempotent preview, browser QA screenshots, proposal JSON, recommended channel/recipient and personalized draft |
| AI | Structured research/copy with deterministic fallback, per-lead cap and usage ledger |
| Outcomes | Reply, positive reply, meeting, proposal, won/lost and loss-reason capture |
| Production shape | FastAPI + PostgreSQL + Valkey + Celery + private R2 artifacts + Vercel preview projects |

The current implementation and next technical work are authoritative in
[ARCHITECTURE.md](ARCHITECTURE.md). Execution ownership is in
[DEVELOPER_HANDOFF.md](DEVELOPER_HANDOFF.md) and
[TECHNICAL_MARKETER_HANDOFF.md](TECHNICAL_MARKETER_HANDOFF.md).

## First cohort operating plan

Run a controlled, lawful cohort of 10–20 Porto/Lisbon/Braga beauty or wellness
businesses. Prefer active businesses with a public business email or contact
form, clear services, demand signals and an observable booking/mobile gap.
Exclude closed, ambiguous, suppressed, uncontactable or out-of-market records.

For each lead: enrich → inspect evidence → score → human-review → approve a
small number of previews → inspect QA/screenshots/proposal/draft → manually
approve/send only through a permitted route → record every response and sales
outcome. Email is preferred; WhatsApp is opt-in only. Stop immediately on a
reply, bounce, opt-out or suppression.

The first message should contain one verified observation, a careful practical
consequence, one concise improvement and a low-friction question. Do not make
revenue guarantees or invent testimonials, prices, credentials or business
facts. Portuguese data-protection/electronic-marketing review is a gate before
real outreach.

## Learning targets—not promises

| Stage | Target |
|---|---:|
| Evidence-complete, contactable businesses | 20 |
| Human-approved prospects | 10 |
| QA-passed previews | 5 |
| Personalized manual first contacts | 10 |
| Qualified calls | 2 |
| Paid pilot | 1 |

Track positive-reply, meeting and win rates by segment, observed gap, channel,
template and message version. The shared north-star metric is **qualified sales
conversations per 100 human-approved, evidence-complete leads**.

## Next decisions

1. Provision production PostgreSQL, Valkey, Vercel mappings, monitoring,
   backups and R2 lifecycle cleanup.
2. Run the controlled cohort and calibrate positioning/FitQL from outcomes.
3. Generate a branded proposal PDF from the stored proposal JSON and expose
   authenticated artifact downloads in the operator UI.
4. Add asynchronous Places operations, queue/DLQ controls and alerts.
5. Only after a paid pilot, consider a second template/niche and bounded
   JavaScript-site crawl fallback.

Do not build autonomous cold outreach, a CRM rewrite, multi-tenancy, a broad
template catalogue or a Cloudflare orchestration rewrite before repeatable paid
outcomes justify them.
