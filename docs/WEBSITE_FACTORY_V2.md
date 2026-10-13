# Website Factory v2: block constructor

Status: **approved architecture; implementation begins with the massage/wellness family.**

## Why v1 is being replaced

The current local renderer is a QA approximation, not a design system. It can pass technical checks while still being visually weak: tiny marks, repeated dense cards, a blank map surface offline, and copy that competes with pricing. That is not acceptable for a customer-facing preview.

## Product decision

A preview is a deterministic composition of verified facts and design blocks. It is not an LLM-generated page.

`PREVIEW_CONTENT_MODE=deterministic` is now the default. It uses no AI tokens. `PREVIEW_CONTENT_MODE=ai` is an explicit, budgeted polish mode for a human-approved lead only.

```
Evidence + approved images
          +
Niche theme tokens
          +
Block selection rules
          +
Verified interaction adapters
          =
Rendered site + screenshot QA
```

## Constructor contract

Every niche template will consume a versioned `PagePlan` derived by scripts:

| Input | Deterministic rule | Result |
|---|---|---|
| name, category, city | always required | hero identity and local SEO |
| verified logo / hero | use asset if present; otherwise typographic wordmark | hero/media variant |
| services and prices | group and display only verified values | menu, cards, or price list |
| phone / email / booking link | choose the verified preferred contact path | call / WhatsApp / booking CTA |
| address | show map link, not an iframe in local preview | location block |
| hours | show only when evidence exists | compact details block |
| audit gaps | never appear on the client website | proposal/outreach only |

The `PagePlan` must store the chosen block ids and source evidence ids so a preview can be rebuilt identically.

## Massage / wellness v2 layout

1. **Hero split** — large treatment image, readable left-aligned name and category, real logo or wordmark, one primary booking action.
2. **Trust strip** — only verified rating/review count, hours, and location; omit any missing item.
3. **Service menu** — two-column desktop / single-column mobile list. Service name and price stay on one visual row; no made-up treatment descriptions.
4. **Booking panel** — a simple native request form initially. When a verified booking provider exists, the block switches to its embed/link.
5. **Location/contact** — address and `Open in Maps` link; no empty iframe. Show all verified phone numbers, not an arbitrary last record.
6. **Footer** — social links only if verified and an unobtrusive unofficial-preview disclosure.

## Reusable block families

- `hero.split-image`, `hero.editorial`, `hero.wordmark`
- `trust.compact`
- `services.price-menu`, `services.card-grid`, `services.no-prices`
- `booking.native-form`, `booking.provider-link`, `booking.provider-embed`
- `location.map-link`, `location.contact-card`
- `gallery.verified-images`
- `faq.verified`, `social-links.verified`

Selection is a small rules engine, not an AI prompt. A business can only render blocks whose data requirements are met.

## Libraries evaluated

- **Keep:** BeautifulSoup + Pillow. They already cover bounded HTML metadata parsing and exact image crops without a new service.
- **Add later, only if needed:** `selectolax` for faster HTML parsing on large approved crawl batches; `CairoSVG` only when a verified source SVG must be rasterized for a PDF or screenshot.
- **Do not adopt for previews:** SVG-Edit is a full browser editor, not a production asset-extraction primitive. Shadcn/Flowbite are useful references for the future React operator console, but importing a generic component kit will not fix a niche website’s art direction.
- **Booking:** start with our native form and a verified external booking link. Do not self-host a calendar product until paid customers show that a real appointment calendar is required.

## Delivery order

1. Add `PagePlan` schema, deterministic planner and block-level test fixtures.
2. Replace both local Jinja renderer and deployable massage Next template with the same v2 block design.
3. Add visual-regression screenshots for desktop and mobile; technical QA alone is insufficient.
4. Add page-plan editor to the operator dossier: choose hero/layout/CTA before approval.
5. Add provider adapters (Calendly/Cal.com/SimplyBook/booking link) only after verified customer demand.

## Acceptance bar

- A human can approve the page from one mobile and one desktop screenshot without opening developer tools.
- No blank media blocks, repeated filler cards, or unsourced service descriptions.
- The same `PagePlan` produces the same page without model calls.
- Any missing data removes a block gracefully instead of showing a placeholder.
