"""Evidence-grounded website research.

The crawler is responsible for fetching and cleaning pages. This module never
accepts HTML or URLs to fetch: it only normalizes supplied public excerpts into
typed facts, rejects unsupported claims, and writes a reviewable evidence trail.
"""

from __future__ import annotations

import json
import re
from typing import Iterable

from sqlalchemy.orm import Session

from app.core.schemas import CleanEvidenceExcerpt, ResearchFact, ResearchOutput
from app.models import Business, Evidence
from app.services.ai_agent import AIResponse, active_model, ai_budget_available, chat_json, record_ai_usage


RESEARCH_PROMPT_VERSION = "research-evidence-v1"
_REQUIRED_MISSING_FIELDS = ("identity", "contacts", "services", "prices", "booking_paths")
MAX_RESEARCH_EXCERPTS = 12
MAX_RESEARCH_EXCERPT_CHARS = 1500


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _facts(output: ResearchOutput) -> Iterable[ResearchFact]:
    if output.identity:
        yield output.identity
    yield from output.contacts
    yield from output.services
    yield from output.prices
    yield from output.booking_paths
    yield from output.website_gaps
    for conflict in output.conflicts:
        yield from conflict.facts


def _ground_output(output: ResearchOutput, excerpts: list[CleanEvidenceExcerpt]) -> ResearchOutput:
    """Drop claims whose URL or quoted excerpt cannot be found in crawl input."""
    sources = {item.source_url: item for item in excerpts}

    def supported(fact: ResearchFact) -> bool:
        source = sources.get(fact.source_url)
        return bool(source and _normalise(fact.evidence_excerpt) in _normalise(source.excerpt))

    identity = output.identity if output.identity and supported(output.identity) else None
    contacts = [fact for fact in output.contacts if supported(fact)]
    services = [fact for fact in output.services if supported(fact)]
    prices = [fact for fact in output.prices if supported(fact)]
    booking_paths = [fact for fact in output.booking_paths if supported(fact)]
    website_gaps = [fact for fact in output.website_gaps if supported(fact)]
    conflicts = []
    for conflict in output.conflicts:
        grounded = [fact for fact in conflict.facts if supported(fact)]
        if len(grounded) >= 2:
            conflicts.append(conflict.model_copy(update={"facts": grounded}))

    missing = list(dict.fromkeys(output.missing_fields))
    present = {
        "identity": bool(identity),
        "contacts": bool(contacts),
        "services": bool(services),
        "prices": bool(prices),
        "booking_paths": bool(booking_paths),
    }
    missing.extend(key for key in _REQUIRED_MISSING_FIELDS if not present[key])
    missing = list(dict.fromkeys(missing))
    status = "needs_review" if conflicts or missing else "complete"
    return ResearchOutput(
        identity=identity,
        contacts=contacts,
        services=services,
        prices=prices,
        booking_paths=booking_paths,
        website_gaps=website_gaps,
        conflicts=conflicts,
        missing_fields=missing,
        status=status,
    )


def _fallback() -> ResearchOutput:
    return ResearchOutput(missing_fields=list(_REQUIRED_MISSING_FIELDS), status="fallback")


def _research_prompt(excerpts: list[CleanEvidenceExcerpt]) -> dict:
    return {
        "evidence": [item.model_dump(mode="json") for item in excerpts],
        "output_schema": {
            "identity": "ResearchFact | null",
            "contacts": "ResearchContact[]",
            "services": "ResearchService[]",
            "prices": "ResearchFact[]",
            "booking_paths": "ResearchFact[]",
            "website_gaps": "ResearchGap[]",
            "conflicts": "ResearchConflict[]",
            "missing_fields": "string[]",
        },
        "rules": [
            "Return JSON only.",
            "Use only evidence supplied in this request; do not browse or infer missing details.",
            "Every returned fact must quote an exact non-empty evidence_excerpt from its source_url.",
            "Copy captured_at from the corresponding evidence item and use extraction_method=llm_evidence_normalization.",
            "Omit unsupported facts. Put absent categories in missing_fields.",
            "If sources disagree, put both grounded facts in conflicts and do not select a winner.",
            "Do not include raw HTML, testimonials, awards, or personal contact data not visibly supplied.",
        ],
    }


def _store_fact(db: Session, business: Business, key: str, fact: ResearchFact, *, status: str) -> None:
    existing = (
        db.query(Evidence)
        .filter(
            Evidence.business_id == business.id,
            Evidence.fact_key == key,
            Evidence.source_url == fact.source_url,
            Evidence.evidence_excerpt == fact.evidence_excerpt,
            Evidence.extraction_method == "llm_evidence_normalization",
        )
        .first()
    )
    if existing:
        return
    db.add(
        Evidence(
            business_id=business.id,
            fact_key=key,
            fact_value=fact.value,
            source_url=fact.source_url,
            evidence_excerpt=fact.evidence_excerpt,
            extraction_method="llm_evidence_normalization",
            confidence=fact.confidence,
            status=status,
            captured_at=fact.captured_at,
        )
    )


def evidence_excerpts_for_business(
    db: Session,
    business: Business,
) -> list[CleanEvidenceExcerpt]:
    """Select the newest unique crawler excerpts within the research prompt budget."""
    rows = (
        db.query(Evidence)
        .filter(
            Evidence.business_id == business.id,
            Evidence.evidence_excerpt != "",
            Evidence.status != "missing",
            Evidence.extraction_method != "llm_evidence_normalization",
        )
        .order_by(Evidence.captured_at.desc(), Evidence.id.desc())
        .limit(MAX_RESEARCH_EXCERPTS * 2)
        .all()
    )
    excerpts: list[CleanEvidenceExcerpt] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        excerpt = (row.evidence_excerpt or "").strip()
        key = (row.source_url or "", excerpt)
        if not excerpt or not row.source_url or key in seen:
            continue
        seen.add(key)
        excerpts.append(
            CleanEvidenceExcerpt(
                source_url=row.source_url,
                excerpt=excerpt[:MAX_RESEARCH_EXCERPT_CHARS],
                captured_at=row.captured_at,
                extraction_method=row.extraction_method or "website_crawl",
            )
        )
        if len(excerpts) >= MAX_RESEARCH_EXCERPTS:
            break
    return excerpts


def persist_research(db: Session, business: Business, output: ResearchOutput) -> None:
    """Persist normalized claims as evidence; conflicts deliberately stay review-only."""
    if output.identity:
        _store_fact(db, business, "business_identity", output.identity, status="inferred")
    for fact in output.contacts:
        _store_fact(db, business, f"contact:{fact.channel}", fact, status="inferred")
    for fact in output.services:
        _store_fact(db, business, "service", fact, status="inferred")
    for fact in output.prices:
        _store_fact(db, business, "price", fact, status="inferred")
    for fact in output.booking_paths:
        _store_fact(db, business, "booking_path", fact, status="inferred")
    for fact in output.website_gaps:
        _store_fact(db, business, "website_gap", fact, status="inferred")
    for conflict in output.conflicts:
        for fact in conflict.facts:
            _store_fact(db, business, f"conflict:{conflict.field}", fact, status="conflicting")


def research_business(
    db: Session,
    business: Business,
    excerpts: list[CleanEvidenceExcerpt],
) -> ResearchOutput:
    """Normalize a small, cleaned evidence set and append both facts and usage."""
    excerpts = [
        item.model_copy(update={"excerpt": item.excerpt[:MAX_RESEARCH_EXCERPT_CHARS]})
        for item in excerpts[:MAX_RESEARCH_EXCERPTS]
    ]
    if not excerpts:
        output = _fallback()
        persist_research(db, business, output)
        return output

    response = (
        chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a cautious business-research normalizer. "
                        "You may only return claims directly supported by the supplied excerpts."
                    ),
                },
                {"role": "user", "content": json.dumps(_research_prompt(excerpts), ensure_ascii=False)},
            ],
            temperature=0.0,
        )
        if ai_budget_available(db, business.id)
        else AIResponse(
            content=None,
            model=active_model(),
            error="per-lead AI budget exhausted",
            usage_raw={},
        )
    )
    record_ai_usage(
        db,
        response,
        operation="research",
        business_id=business.id,
        prompt_version=RESEARCH_PROMPT_VERSION,
    )
    if not response.content:
        output = _fallback()
    else:
        try:
            output = _ground_output(ResearchOutput.model_validate_json(response.content), excerpts)
        except (ValueError, TypeError):
            output = _fallback()
    persist_research(db, business, output)
    return output
