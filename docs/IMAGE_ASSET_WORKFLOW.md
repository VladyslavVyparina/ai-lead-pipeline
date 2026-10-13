# Brand image and logo asset workflow

The preview system uses the business's real, publicly supplied brand assets whenever they are available. It does not present an AI-created mark as the business's official logo.

## What is in the repository

- `app/services/brand_extractor.py` finds public favicon, Open Graph and SVG logo signals from an approved business website crawl.
- `app/services/brand_image_assets.py` uses [Pillow](https://python-pillow.org/) to make a precise crop/resize from an operator-supplied image, and to derive a small colour palette deterministically.
- `Pillow>=10,<12` is listed in `requirements.txt` and is the required local image-processing dependency.

## Workflow for a new lead

1. Prefer a logo URL or image supplied on the verified business website.
2. If the operator supplies a screenshot/photo, crop the visible mark with `crop_image_asset`. Store the original attachment path, crop coordinates, source URL, capture time and extraction method in `Evidence`.
3. Save the resulting `logo_url`, optional `hero_image_url`, `primary_color` and optional `accent_color` as sourced Evidence. The preview only consumes those facts after normal confidence checks.
4. Label the preview as unofficial. Do not use a visible Google Maps image/HTML as an extraction target, and do not imply that a social-network page granted image rights.
5. Use a generated SVG only for a clearly labelled **unofficial concept** or decorative site icon. Never regenerate, trace or call an AI-generated mark the business's logo without written approval.

## Why Pillow, not an AI logo library

For lead previews, an exact crop keeps provenance, avoids accidental trademark misrepresentation, and is inexpensive. We can add `CairoSVG` later if a verified site serves an SVG that must be rasterized for PDF/QA; it is intentionally not a dependency until that conversion is required.

## Damrak Thai Yoga Massage example

The Damrak lead uses a logo crop from the user-supplied Facebook screenshot and a treatment-room crop from the user-supplied Maps screenshot. The record has evidence for each crop, including its original public source URL and extraction method. The website preview and proposal are review assets only; no message or outreach is sent by this flow.
