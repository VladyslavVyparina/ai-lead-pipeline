# Growth, market research and technical-marketing handoff

Last reviewed: 2026-07-25. Your job is to turn verified business evidence into a
small, lawful cohort, truthful positioning and measurable outcomes. You may edit
versioned config/templates, but cannot bypass evidence, human approval, consent
or suppression guards.

## Feature completion matrix

| Feature | Done now | What you must finish / validate |
|---|---|---|
| ICP and offer | Wellness pilot: Porto/Lisbon/Braga; Booking Conversion Sprint positioning | Select one narrow first cohort and finalize included scope, fixed/ranged price and exclusions in the versioned Pricebook |
| Lead sourcing | CSV contract plus official Google Places API discovery; provider provenance fields | Obtain approved provider/API access, record permitted use, create first 10–20 real records; never use illustrative seed leads for outreach |
| Research dossier | Evidence, contacts, website audit, FitQL reasons, exclusions, QA, assets and outcomes displayed together | Review all early dossiers, flag incorrect extraction, and capture a correction reason rather than guessing facts |
| FitQL | Deterministic score/tier and review route | Define which observed gaps actually correlate with replies/meetings; change weights only in new versioned YAML after outcome review |
| Preview offer | Evidence-backed branded preview, proposal and draft with human gates | Review every initial preview for identity, services, contact/booking route, disclaimer, claims and local language before it is shared |
| Messaging | Versioned channel-aware drafts and recommendation | Create Portuguese PT/EN variants; test one meaningful variable at a time and record version/channel/gap with every outcome |
| Compliance | Suppression, consent and approval controls | Obtain Portuguese legal/commercial-marketing review before real outreach; email/contact form preferred, WhatsApp opt-in only |
| Outcome learning | Reply, positive reply, meeting, proposal, won/lost and loss reason captured | Capture 100% of first-cohort outcomes and use them in a weekly FitQL/message review |

## Run the first lawful business discovery

The application does **not** scrape Google Maps HTML. It calls Google Places API
(New) Text Search only after a `GOOGLE_PLACES_API_KEY` is set locally and its
billing/EEA/provider terms have been reviewed.

1. Add `GOOGLE_PLACES_API_KEY` to your private `.env`; do not share it in chat,
   tickets or Git.
2. Start the API: `py -3.10 run_api.py`, then open `http://127.0.0.1:8000/ui`.
3. In **Sources**, create `google_places` connector. Enter the source owner,
   category/city, and an accurate `permitted_use` record.
4. Start narrow: `massagem e bem-estar em Porto, Portugal`; limit to 10–20 and
   review five. This is discovery, not permission to contact.
5. Open every dossier after enrichment. Reject/suppress closed, ambiguous,
   uncontactable, out-of-market or weak-evidence records.
6. Only approve 2–3 packages/day after checking desktop/mobile QA screenshots,
   proposal, recipient/channel rationale, draft and evidence.

If Places access is not ready, obtain a lawful CSV export from an approved
provider and import [real_leads_import_template.csv](real_leads_import_template.csv).
Do not replace this with scraping or personal-contact collection.

## Cohort operating loop

1. Import ten records; enrich and inspect all facts.
2. Human-review the top FitQL candidates. Correct evidence, not the story.
3. Approve a small preview batch; share only after QA and review.
4. Send manually through a permitted business route after approval.
5. Stop on reply, bounce, opt-out or suppression.
6. Record outcome, objections and loss reason within the same day.
7. Weekly: compare positive reply/meeting/win rate by segment, gap, template,
   channel and message version; propose a single config experiment.

## Editable levers and coding boundaries

| Lever | Location | Rules |
|---|---|---|
| Market / ICP | `config/markets/` | New immutable `vN.yaml`; retain exclusions and lawful-use fields |
| FitQL | `config/scoring/` | Use outcomes, not intuition; preserve historical versions |
| Offer / price | `config/pricebook/` | Prices only here—never prompts or code |
| Message variants | `config/messaging/` | Cite verified observation; no revenue promises or fabricated proof |
| Template routing | `config/templates/` | Route only audited templates/categories |
| Preview templates | `site_templates/` | Preserve `SITE_CONFIG`, QA hooks, noindex, form and unofficial disclaimer |

Never add free-form AI HTML, customer credentials, personal-contact data or
secrets to a template/config. Phrase gaps as observable website behaviour, not
unproven business claims.

## Metrics and targets

The first cohort is a learning experiment: 20 evidence-complete/contactable
records, 10 approved prospects, five QA-passed previews, 10 manual first
contacts, two qualified calls and one paid pilot. The shared metric is qualified
sales conversations per 100 human-approved, evidence-complete leads.

## OpenRouter guidance for this role

OpenRouter powers bounded research/copy only; it does not browse sites or make
facts true. Start dev smoke tests with `openrouter/free`; use pinned
`qwen/qwen3-32b` when comparing prompt/message behaviour. Review the recorded
model, cost and result in the dossier/ledger. Never receive or store the team’s
raw API key—ask engineering for a separate, limited development key.
