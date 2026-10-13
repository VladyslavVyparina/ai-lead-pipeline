from datetime import datetime
import json

import pytest

from app.core.schemas import CleanEvidenceExcerpt
from app.models import AIUsageLedger, Business, Evidence
from app.services.ai_agent import AIResponse, record_ai_usage
from app.services.research_agent import research_business


def _business(db):
    business = Business(
        name="Calma Porto",
        category="massage_wellness",
        city="porto",
        dedupe_key="calma-porto-research",
    )
    db.add(business)
    db.commit()
    return business


def _excerpt():
    return CleanEvidenceExcerpt(
        source_url="https://calma.example/services",
        excerpt="Calma Porto oferece Massagem relaxante. Marque por WhatsApp +351 912 345 678.",
        captured_at=datetime(2026, 7, 23, 12, 0, 0),
    )


def _fact(value, excerpt):
    return {
        "value": value,
        "source_url": "https://calma.example/services",
        "evidence_excerpt": excerpt,
        "confidence": 0.91,
        "extraction_method": "llm_evidence_normalization",
        "captured_at": "2026-07-23T12:00:00",
    }


def test_research_persists_only_grounded_facts_and_usage(db, monkeypatch):
    business = _business(db)
    response = {
        "identity": _fact("Calma Porto", "Calma Porto"),
        "contacts": [{**_fact("+351 912 345 678", "WhatsApp +351 912 345 678"), "channel": "whatsapp"}],
        "services": [{**_fact("Massagem relaxante", "Massagem relaxante"), "description": ""}],
        "prices": [],
        "booking_paths": [{**_fact("WhatsApp", "Marque por WhatsApp +351 912 345 678")}],
        "website_gaps": [],
        "conflicts": [],
        "missing_fields": ["prices"],
    }
    monkeypatch.setattr(
        "app.services.research_agent.chat_json",
        lambda *args, **kwargs: AIResponse(
            content=json.dumps(response),
            model="gpt-4o-mini",
            provider_request_id="req_research_1",
            input_tokens=100,
            output_tokens=50,
            latency_ms=23,
            usage_raw={"prompt_tokens": 100, "completion_tokens": 50},
        ),
    )

    output = research_business(db, business, [_excerpt()])
    db.commit()

    assert output.status == "needs_review"
    assert [fact.fact_value for fact in db.query(Evidence).all()] == [
        "Calma Porto",
        "+351 912 345 678",
        "Massagem relaxante",
        "WhatsApp",
    ]
    ledger = db.query(AIUsageLedger).one()
    assert ledger.provider_request_id == "req_research_1"
    assert ledger.input_tokens == 100
    assert ledger.output_tokens == 50
    assert ledger.estimated_cost_usd == pytest.approx(0.000045)


def test_research_drops_unsupported_claims_and_falls_back(db, monkeypatch):
    business = _business(db)
    unsupported = {
        "identity": _fact("Invented Spa", "this sentence is not present"),
        "contacts": [], "services": [], "prices": [], "booking_paths": [],
        "website_gaps": [], "conflicts": [], "missing_fields": [],
    }
    monkeypatch.setattr(
        "app.services.research_agent.chat_json",
        lambda *args, **kwargs: AIResponse(content=json.dumps(unsupported), model="gpt-4o-mini", usage_raw={}),
    )

    output = research_business(db, business, [_excerpt()])
    assert output.identity is None
    assert "identity" in output.missing_fields
    assert db.query(Evidence).count() == 0


def test_clean_evidence_rejects_raw_html():
    with pytest.raises(ValueError, match="cleaned text"):
        CleanEvidenceExcerpt(source_url="https://example.test", excerpt="<html><script>x</script>")


def test_usage_ledger_records_deterministic_fallback(db):
    business = _business(db)
    record_ai_usage(
        db,
        AIResponse(content=None, model="gpt-4o-mini", error="no API key", usage_raw={}),
        operation="research",
        business_id=business.id,
    )
    db.commit()
    row = db.query(AIUsageLedger).one()
    assert row.status == "fallback"
    assert row.provider == "deterministic"
    assert row.total_tokens == 0
