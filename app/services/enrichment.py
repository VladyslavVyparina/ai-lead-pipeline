"""Enrichment: website/social-style facts → evidence with status labels.

For the pilot vertical slice, enrichment reads the seed catalog snapshot
attached on the SourceRecord (and/or reloads by business name). Live HTTP
fetch adapters plug into `fetch_website_signals` later; facts are never invented.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.adapters.directory_seed import load_catalog
from app.models import Business, ContactPoint, Evidence, SourceRecord, WebsiteAudit
from app.services import dedupe
from app.services.brand_extractor import extract_brand_signals
from app.services.events import record_event
from app.services.web_crawler import (
    BOOKING_WORDS,
    CONTACT_WORDS,
    SERVICE_WORDS,
    CrawlError,
    crawl_website,
    evidence_excerpt,
)

FACT_STATUS = ("confirmed", "inferred", "missing", "conflicting", "stale")


def _upsert_contact(
    db: Session,
    business: Business,
    channel: str,
    value: str,
    *,
    verified: bool = False,
) -> None:
    value = (value or "").strip()
    if not value:
        return
    if channel == "email":
        value = value.lower()
    if channel == "instagram" and value.startswith("@"):
        value = value  # keep handle form
    normalized = dedupe.normalize_contact(channel, value)
    existing = (
        db.query(ContactPoint)
        .filter(
            ContactPoint.business_id == business.id,
            ContactPoint.channel == channel,
            ContactPoint.normalized_value == normalized,
        )
        .first()
    )
    if existing:
        if verified and not existing.verified:
            existing.verified = True
            db.add(existing)
        return
    db.add(
        ContactPoint(
            business_id=business.id,
            channel=channel,
            value=value,
            normalized_value=normalized,
            verified=verified,
            is_business_contact=True,
        )
    )


def _store_fact(
    db: Session,
    business: Business,
    key: str,
    value,
    *,
    source_url: str = "",
    confidence: float = 1.0,
    status: str = "confirmed",
    excerpt: str = "",
    extraction_method: str = "",
) -> None:
    existing = (
        db.query(Evidence)
        .filter(Evidence.business_id == business.id, Evidence.fact_key == key)
        .order_by(Evidence.captured_at.desc())
        .first()
    )
    if existing and existing.fact_value == value and existing.status == status:
        return
    if existing and existing.fact_value != value and existing.status == "confirmed" and status == "confirmed":
        status = "conflicting"
    db.add(
        Evidence(
            business_id=business.id,
            fact_key=key,
            fact_value=value,
            source_url=source_url,
            evidence_excerpt=excerpt,
            extraction_method=extraction_method,
            confidence=confidence,
            status=status,
        )
    )


EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
PHONE_RE = re.compile(r"(?:\+351[\s().-]*)?(?:[29](?:[\s().-]*\d){8})")
SERVICE_TERMS = (
    "massagem",
    "massage",
    "terapia",
    "therapy",
    "drenagem",
    "facial",
    "tratamento",
    "treatment",
    "spa",
    "osteopatia",
    "pilates",
    "yoga",
    "reiki",
)


def _latest_source_record(db: Session, business: Business) -> Optional[SourceRecord]:
    return (
        db.query(SourceRecord)
        .filter(SourceRecord.business_id == business.id)
        .order_by(SourceRecord.created_at.desc())
        .first()
    )


def _store_provider_facts(db: Session, business: Business) -> None:
    record = _latest_source_record(db, business)
    if not record:
        return
    source_url = (record.provenance or {}).get("url", "")
    if record.provider_rating is not None:
        _store_fact(
            db,
            business,
            "rating",
            record.provider_rating,
            source_url=source_url,
            confidence=1.0,
            excerpt=f"Provider rating: {record.provider_rating}",
            extraction_method="provider_api",
        )
    if record.provider_review_count is not None:
        _store_fact(
            db,
            business,
            "review_count",
            record.provider_review_count,
            source_url=source_url,
            confidence=1.0,
            excerpt=f"Provider review count: {record.provider_review_count}",
            extraction_method="provider_api",
        )


def _candidate_services(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []
    for node in soup.find_all(["h2", "h3", "li"]):
        value = re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip(" •-|")
        lowered = value.lower()
        if 3 <= len(value) <= 80 and any(term in lowered for term in SERVICE_TERMS):
            if value not in candidates:
                candidates.append(value)
        if len(candidates) >= 12:
            break
    return candidates


def _enrich_live_website(db: Session, business: Business) -> dict:
    crawl = crawl_website(business.website_url)
    all_text = " ".join(page.text for page in crawl.pages)
    homepage = crawl.pages[0]

    emails: dict[str, tuple[str, str]] = {}
    phones: dict[str, tuple[str, str]] = {}
    instagram: dict[str, str] = {}
    booking_urls: list[tuple[str, str]] = []
    contact_form_urls: list[str] = []
    service_names: list[str] = []

    if crawl.json_ld:
        structured_excerpt = json.dumps(
            crawl.json_ld[:10],
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )[:4000]
        _store_fact(
            db,
            business,
            "website_structured_data",
            crawl.json_ld[:10],
            source_url=homepage.url,
            confidence=0.95,
            excerpt=structured_excerpt,
            extraction_method="json_ld",
        )

    for page in crawl.pages:
        for email in EMAIL_RE.findall(page.text):
            lowered = email.lower()
            if not lowered.endswith((".png", ".jpg", ".jpeg", ".webp")):
                emails[lowered] = (page.url, evidence_excerpt(page.text, email))
        for phone in PHONE_RE.findall(page.text):
            normalized = re.sub(r"[^\d+]", "", phone)
            phones[normalized] = (page.url, evidence_excerpt(page.text, phone))

        page_signal = f"{page.url} {page.title} {page.text[:500]}".lower()
        if page.has_form and any(word in page_signal for word in CONTACT_WORDS):
            contact_form_urls.append(page.url)
        for href, label in page.links:
            signal = f"{href} {label}".lower()
            if "instagram.com/" in href.lower():
                instagram[href] = page.url
            if any(word in signal for word in BOOKING_WORDS):
                booking_urls.append((href, page.url))
        if any(word in page_signal for word in SERVICE_WORDS):
            for item in _candidate_services(page.html):
                if item not in service_names:
                    service_names.append(item)

    for email, (source_url, excerpt) in list(emails.items())[:5]:
        _upsert_contact(db, business, "email", email, verified=True)
        _store_fact(
            db,
            business,
            f"contact_email:{email}",
            email,
            source_url=source_url,
            confidence=0.98,
            excerpt=excerpt,
            extraction_method="website_regex",
        )
    for phone, (source_url, excerpt) in list(phones.items())[:5]:
        _upsert_contact(db, business, "phone", phone, verified=True)
        _store_fact(
            db,
            business,
            f"contact_phone:{phone}",
            phone,
            source_url=source_url,
            confidence=0.95,
            excerpt=excerpt,
            extraction_method="website_regex",
        )
    for url, source_url in list(instagram.items())[:3]:
        _upsert_contact(db, business, "instagram", url, verified=True)
        _store_fact(
            db,
            business,
            "instagram",
            url,
            source_url=source_url,
            confidence=0.95,
            excerpt=url,
            extraction_method="website_link",
        )

    if homepage.meta_description:
        _store_fact(
            db,
            business,
            "description",
            homepage.meta_description,
            source_url=homepage.url,
            confidence=0.95,
            excerpt=homepage.meta_description,
            extraction_method="meta_description",
        )

    brand = extract_brand_signals(homepage.html, homepage.url)
    if brand.get("logo_url"):
        _store_fact(
            db,
            business,
            "logo_url",
            brand["logo_url"],
            source_url=homepage.url,
            confidence=float(brand.get("logo_confidence", 0.8)),
            excerpt=brand["logo_url"],
            extraction_method="website_brand",
            status="confirmed" if brand.get("logo_confidence", 0) >= 0.9 else "inferred",
        )
    if brand.get("primary_color"):
        _store_fact(
            db,
            business,
            "primary_color",
            brand["primary_color"],
            source_url=homepage.url,
            confidence=0.85 if brand.get("theme_color") else 0.7,
            excerpt=f"brand colors: {', '.join(brand.get('colors', []))}",
            extraction_method="website_brand",
            status="inferred",
        )
    if brand.get("accent_color"):
        _store_fact(
            db,
            business,
            "accent_color",
            brand["accent_color"],
            source_url=homepage.url,
            confidence=0.65,
            excerpt=brand["accent_color"],
            extraction_method="website_brand",
            status="inferred",
        )
    if brand.get("colors"):
        _store_fact(
            db,
            business,
            "brand_colors",
            brand["colors"],
            source_url=homepage.url,
            confidence=0.7,
            excerpt=", ".join(brand["colors"]),
            extraction_method="website_brand",
            status="inferred",
        )
    if brand.get("hero_image_url"):
        _store_fact(
            db,
            business,
            "hero_image_url",
            brand["hero_image_url"],
            source_url=homepage.url,
            confidence=0.7,
            excerpt=brand["hero_image_url"],
            extraction_method="website_brand",
            status="inferred",
        )
    if service_names:
        services = [{"name": value} for value in service_names[:12]]
        source_page = next(
            (
                page
                for page in crawl.pages
                if any(word in f"{page.url} {page.title}".lower() for word in SERVICE_WORDS)
            ),
            homepage,
        )
        _store_fact(
            db,
            business,
            "services",
            services,
            source_url=source_page.url,
            confidence=0.82,
            excerpt="; ".join(service_names[:8]),
            extraction_method="website_structure",
        )
        _store_fact(
            db,
            business,
            "service_breadth",
            len(service_names),
            source_url=source_page.url,
            confidence=0.82,
            excerpt=f"{len(service_names)} service labels found",
            extraction_method="website_structure",
            status="inferred",
        )
    else:
        _store_fact(
            db,
            business,
            "services",
            None,
            source_url=homepage.url,
            confidence=0.0,
            status="missing",
            extraction_method="website_structure",
        )

    if booking_urls:
        booking_url, found_on = booking_urls[0]
        _store_fact(
            db,
            business,
            "booking_url",
            booking_url,
            source_url=found_on,
            confidence=0.95,
            excerpt=booking_url,
            extraction_method="website_link",
        )
    if contact_form_urls:
        _store_fact(
            db,
            business,
            "contact_form_url",
            contact_form_urls[0],
            source_url=contact_form_urls[0],
            confidence=0.95,
            excerpt="Public contact form",
            extraction_method="website_form",
        )

    contact_clear = bool(emails or phones or contact_form_urls)
    notes = [
        f"crawled {len(crawl.pages)} page(s)",
        f"emails={len(emails)}",
        f"phones={len(phones)}",
        f"services={len(service_names)}",
        f"booking_links={len(booking_urls)}",
    ]
    if crawl.errors:
        notes.append(f"crawl_errors={len(crawl.errors)}")
    db.add(
        WebsiteAudit(
            business_id=business.id,
            has_website=True,
            mobile_ok=homepage.has_viewport,
            has_booking_cta=bool(booking_urls),
            services_clear=bool(service_names),
            contact_clear=contact_clear,
            notes="; ".join(notes),
        )
    )
    return {
        "pages_crawled": len(crawl.pages),
        "crawl_errors": crawl.errors,
        "extraction_status": crawl.extraction_status,
        "json_ld_items": len(crawl.json_ld),
        "public_contacts_found": len(emails) + len(phones) + len(instagram),
        "booking_url_found": bool(booking_urls),
        "contact_form_found": bool(contact_form_urls),
    }


def _seed_for_business(db: Session, business: Business) -> Optional[dict]:
    """Recover enrichment payload from the latest source record extra.seed."""
    record = (
        db.query(SourceRecord)
        .filter(SourceRecord.business_id == business.id)
        .order_by(SourceRecord.created_at.desc())
        .first()
    )
    if record and isinstance(record.raw, dict):
        extra = record.raw.get("extra") or {}
        seed = extra.get("seed")
        if isinstance(seed, dict):
            return seed
    # Fallback: match by name in default catalog
    try:
        catalog = load_catalog("porto_wellness_v1")
    except FileNotFoundError:
        return None
    for entry in catalog.get("businesses") or []:
        if entry.get("name", "").strip().lower() == business.name.strip().lower():
            return entry
    return None


def enrich_business(db: Session, business: Business, *, actor: str = "system:enrichment") -> dict:
    """Extract contacts/services/hours/audit and store evidence with status."""
    _store_provider_facts(db, business)
    seed = _seed_for_business(db, business)
    source_url = (seed or {}).get("website_url") or (seed or {}).get("profile_url") or business.website_url or ""

    live_summary: dict = {}
    placeholder = any(
        marker in (business.website_url or "").lower()
        for marker in ("example-", ".example", ".test")
    )
    if business.website_url and not placeholder:
        try:
            live_summary = _enrich_live_website(db, business)
        except CrawlError as exc:
            _store_fact(
                db,
                business,
                "website_fetch",
                str(exc),
                source_url=business.website_url,
                confidence=0.0,
                status="missing",
                excerpt=str(exc),
                extraction_method="http_crawl",
            )
            db.add(
                WebsiteAudit(
                    business_id=business.id,
                    has_website=True,
                    mobile_ok=False,
                    has_booking_cta=False,
                    services_clear=False,
                    contact_clear=False,
                    notes=f"live enrichment failed: {exc}",
                )
            )
            live_summary = {"crawl_error": str(exc)}
    elif seed:
        if seed.get("website_url") and not business.website_url:
            business.website_url = seed["website_url"]
        if seed.get("profile_url") and not business.profile_url:
            business.profile_url = seed["profile_url"]
        if seed.get("address") and not business.address:
            business.address = seed["address"]
        db.add(business)

        # Contacts from directory snapshot — phone/email treated as confirmed public listings
        _upsert_contact(db, business, "phone", seed.get("phone", ""), verified=bool(seed.get("phone")))
        _upsert_contact(db, business, "email", seed.get("email", ""), verified=bool(seed.get("email")))
        _upsert_contact(db, business, "instagram", seed.get("instagram", ""), verified=False)

        if seed.get("address"):
            _store_fact(db, business, "address", seed["address"], source_url=source_url, status="confirmed")
        if seed.get("hours"):
            _store_fact(db, business, "hours", seed["hours"], source_url=source_url, status="confirmed")
        if seed.get("services"):
            _store_fact(db, business, "services", seed["services"], source_url=source_url, confidence=0.95, status="confirmed")
        if seed.get("rating") is not None:
            _store_fact(db, business, "rating", seed["rating"], source_url=source_url, status="confirmed")
        if seed.get("review_count") is not None:
            _store_fact(db, business, "review_count", seed["review_count"], source_url=source_url, status="confirmed")

        service_count = len(seed.get("services") or [])
        _store_fact(
            db,
            business,
            "service_breadth",
            service_count,
            source_url=source_url,
            status="inferred",
            confidence=0.8,
        )
        _store_fact(db, business, "practitioners", 1 if service_count else 0, source_url=source_url, status="inferred", confidence=0.6)
        _store_fact(db, business, "locations", 1, source_url=source_url, status="inferred", confidence=0.7)

        if seed.get("notes"):
            _store_fact(db, business, "research_notes", seed["notes"], source_url=source_url, status="inferred", confidence=0.7)

        description = f"{business.name} — massagem e bem-estar em {business.city.title()}."
        _store_fact(db, business, "description", description, source_url=source_url, status="inferred", confidence=0.75)

        db.add(
            WebsiteAudit(
                business_id=business.id,
                has_website=bool(seed.get("has_website")),
                mobile_ok=bool(seed.get("mobile_ok")),
                has_booking_cta=bool(seed.get("has_booking_cta")),
                services_clear=bool(seed.get("services_clear")),
                contact_clear=bool(seed.get("contact_clear")),
                notes=seed.get("notes", ""),
            )
        )
    else:
        # Mark key commercial fields as missing so UI/scoring can show gaps
        for key in ("hours", "services", "description"):
            has = (
                db.query(Evidence)
                .filter(Evidence.business_id == business.id, Evidence.fact_key == key)
                .first()
            )
            if not has:
                _store_fact(db, business, key, None, status="missing", confidence=0.0)
        db.add(
            WebsiteAudit(
                business_id=business.id,
                has_website=bool(business.website_url),
                mobile_ok=False,
                has_booking_cta=False,
                services_clear=False,
                contact_clear=bool(
                    db.query(ContactPoint).filter(ContactPoint.business_id == business.id).first()
                ),
                notes="enrichment without seed snapshot",
            )
        )

    summary = fact_status_summary(db, business)
    summary.update(live_summary)
    record_event(
        db,
        action="business_enriched",
        actor=actor,
        business_id=business.id,
        entity="business",
        entity_id=business.id,
        payload=summary,
        idempotency_key=f"enriched:{business.id}:{business.updated_at.isoformat() if business.updated_at else business.id}",
    )
    db.flush()
    return summary


def fact_status_summary(db: Session, business: Business) -> dict:
    evidence = db.query(Evidence).filter(Evidence.business_id == business.id).all()
    by_status: dict[str, list[str]] = {s: [] for s in FACT_STATUS}
    for e in evidence:
        status = e.status if e.status in by_status else "inferred"
        by_status[status].append(e.fact_key)
    low_confidence = [
        e.fact_key
        for e in evidence
        if e.status not in {"missing"} and (e.confidence or 0.0) < 0.7
    ]
    return {
        "confirmed": by_status["confirmed"],
        "inferred": by_status["inferred"],
        "missing": by_status["missing"],
        "conflicting": by_status["conflicting"],
        "stale": by_status["stale"],
        "fact_count": len(evidence),
        "low_confidence": low_confidence,
        "review_required": bool(by_status["conflicting"] or by_status["stale"] or low_confidence),
    }
