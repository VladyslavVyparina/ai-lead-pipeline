# Proposal template policy

Last reviewed: 2026-07-25.

The canonical commercial proposal reference is
[`assets/proposal/skylix-proposal-master.pdf`](../assets/proposal/skylix-proposal-master.pdf),
supplied by the owner. It defines the four-page Skylix/Kaapora format:

1. agency banner, client title, package comparison;
2. website and Google Business Profile details;
3. booking, CRM, and AI-assistant details;
4. remaining assistant scope and optional support plans.

## Current production renderer

`app/services/proposal_pdf.py` recreates this layout using ReportLab and the
versioned `config/pricebook/v2.yaml`. This is the active proposal format for
all new leads. The pricebook owns package prices, inclusions, add-ons, and
support plans; code owns layout only.

Only verified lead data may be substituted:

- business name in the title and footer;
- verified city or location where available;
- evidence-grounded audit context, preview URL, and approved offer when those
  sections are enabled.

Never substitute invented services, prices, testimonials, addresses, results,
credentials, or contact details.

## Source-PDF overlay decision

For future pixel-for-pixel matching, use PyMuPDF or pypdf to place approved
lead fields over the canonical source PDF while retaining its static visual
design. Do not edit the supplied master in place. Generate a new private
`proposal_pdf` artifact, inspect all rendered pages, and retain the existing
ReportLab renderer as the safe fallback for text that must reflow.

This overlay path is documented architecture work, not the active renderer
yet. It must preserve the same evidence, pricebook, artifact, retention, and
idempotency controls as the current renderer.
