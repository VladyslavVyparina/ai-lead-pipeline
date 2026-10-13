# massage-spa-template (pipeline copy)

Self-contained Next.js template for the AI Lead pipeline's **massage / spa /
cosmetology** niches. This is a **copy** derived from the Kaapora design — it is
independent of the client's production repo, which is never modified by the
pipeline.

## SITE_CONFIG contract

When deployed as a per-lead preview, the pipeline injects a `SITE_CONFIG`
environment variable (JSON — see backend `app/core/schemas.py` → `SiteConfig`,
with the `ContentPack` under `content`). The adapter that consumes it lives in:

- `src/lib/preview-config.ts` — parses `SITE_CONFIG` into a typed `LeadOverlay`
  (business name, hero copy, services + prices, contacts, address, hours, brand
  colors + logo + hero image, disclaimer). Read once at module load (each lead
  is its own deployment). Returns `null` when `SITE_CONFIG` is absent, so the
  template renders its built-in defaults unchanged.
- `src/lib/dictionaries.ts` — overlays lead data onto the copy as `dict.lead`,
  passed to client components via props (avoids server-env-in-client issues).
- `app/[lang]/layout.tsx` — injects the lead's brand palette into the
  `hsl(var(--token))` design system, renders the unofficial-preview banner, and
  sets `noindex`.
- `HeroSection`, `PricingClient`, `LocationClient`, `NavbarClient`, `StickyCTA`,
  `page.tsx` — prefer lead data when a preview overlay is present.

## Deploy wiring

Registered in `config/templates/v2.yaml` as `massage-spa-template`
(deploy_key `massage_spa`). To route leads here on Vercel, create the project
from this directory and set:

```
VERCEL_TEMPLATE_PROJECTS={"massage_spa":{"project_id":"prj_xxx","github_repo_id":"<id>","git_ref":"main"}}
```

## Local check

```
npm install
npm run typecheck
SITE_CONFIG='{...lead json...}' npm run dev
```
