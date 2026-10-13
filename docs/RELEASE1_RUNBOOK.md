# Release 1: First-customer engine runbook

Last reviewed: 2026-07-25.

## What is operational

The operator can now run:

```text
official Google Places discovery or lawful CSV/manual import
-> bounded live website enrichment
-> evidence excerpts and review flags
-> deterministic FitQL scoring
-> human shortlist/approval
-> rendered preview and browser QA
-> desktop/mobile screenshots
-> versioned Local Pro proposal
-> channel and recipient recommendation
-> personalized draft
-> human outreach approval/mark-sent
-> reply, meeting, proposal, won/lost outcome capture
```

Google Maps HTML is not scraped. The live connector uses Google Places API
(New) Text Search with an explicit field mask.

## Setup

1. Install Python dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   python -m playwright install chromium
   ```

2. Set strong secrets and the public API URL in `.env`.

3. To use live discovery, set:

   ```dotenv
   GOOGLE_PLACES_API_KEY=...
   ```

4. Start the service:

   ```powershell
   python run_api.py
   ```

5. Open `http://localhost:8000/ui`.

## Live discovery

On **Sources**:

1. Create a connector with adapter `google_places`.
2. Record an accurate `permitted_use` value after reviewing the provider terms.
3. Enter a narrow query such as `massagem e bem-estar em Porto, Portugal`.
4. Start with 10-20 results and a review queue of five.

The call performs discovery, website enrichment, scoring, and shortlist creation.
The Places API can return at most 60 results for this operation, and the product
enforces that limit.

## CSV import

Use [real_leads_import_template.csv](real_leads_import_template.csv).

Required:

- `name`

Recommended:

- `category`
- `city`
- `address`
- `website`
- `profile_url`
- `provider_id`
- `rating`
- `review_count`
- `captured_at` as ISO 8601
- public business `email`, `phone`, or `instagram`

The connector record must state the source and permitted use.

## Lead review

The dossier shows:

- source/provider record and capture time;
- public contacts and verification state;
- extracted evidence, exact excerpts, URLs, confidence, and method;
- latest website audit;
- FitQL breakdown and reasons;
- conflicting, stale, or low-confidence warnings;
- deterministic recommended channel and recipient;
- previews, QA, proposals, messages, and outcomes.

Use **Run live enrichment** for a manually imported website. Then score the
record. Approve only a shortlisted lead.

Preview generation is blocked when:

- no usable verified public business contact path exists;
- the business is suppressed;
- the provider reports it permanently closed.

Low-confidence facts used in preview content continue to fail closed.

## Asset package

**Approve preview** creates one idempotent package per business:

- preview URL;
- desktop/mobile rendered QA screenshots;
- complete QA report;
- Local Pro proposal;
- recommended channel, recipient, and reason;
- personalized draft;
- evidence manifest.

A second click returns the existing completed package instead of duplicating
the preview, proposal, or draft.

When Vercel is configured, the deployment adapter waits for `READY` before
browser QA. Without Vercel, the local adapter renders a real HTML artifact and
QA runs against it; the displayed `.local.test` URL is not externally shareable.

## Rendered QA

Chromium checks:

- page load/status;
- business identity;
- hero, services, contact, and disclaimer sections;
- placeholder text;
- contact links;
- booking/contact form wiring through an intercepted QA submission;
- desktop/mobile horizontal overflow;
- screenshots at 1440px and 390px widths.

Any failed required check prevents `preview_ready`.

## Outcome capture

On the lead dossier, record:

- replied;
- positive reply;
- meeting booked;
- proposal sent;
- won;
- lost, with a required loss reason.

Attach the message and proposal versions where relevant. Outcomes update the
lead lifecycle and opportunity stage, and appear in analytics for FitQL and
messaging calibration.

## Production gates before contacting real businesses

- Review Google Maps Platform EEA terms and billing for the configured account.
- Review Portuguese data-protection and electronic-marketing requirements.
- Use only approved public business contact routes.
- Keep WhatsApp opt-in-only.
- Manually approve and send the first cohort.
- Configure Vercel and test a real deployment URL.
- Move from SQLite to managed PostgreSQL before multiple operators or concurrent runs.
