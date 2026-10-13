from datetime import datetime

import pytest

from app.adapters.csv_import import run_import
from app.adapters.google_places import run_google_places
from app.core.schemas import Provenance, SourceRecordIn
from app.core.state_machine import LeadState
from app.models import (
    Business,
    Artifact,
    ContactPoint,
    Evidence,
    Proposal,
    SourceConnector,
    SourceRecord,
    WebsiteBuild,
)
from app.services.enrichment import enrich_business
from app.services.ingestion import ingest_record
from app.services.lead_review import LeadEligibilityError, assert_preview_eligible
from app.services.outcomes import capture_outcome
from app.services.pipeline import approve_and_generate_preview, run_porto_wellness_vertical_slice
from app.services.web_crawler import CrawlResult, CrawledPage


def test_release1_csv_contract_persists_provider_metadata(db, connector):
    csv_text = "\n".join(
        [
            "name,category,city,address,website,profile_url,email,phone,instagram,provider_id,rating,review_count,captured_at",
            "Real Spa,massage_wellness,porto,Rua 1,https://real.example.org,https://provider.example/1,hello@real.example.org,+351912345678,@real,place-123,4.7,91,2026-07-20T10:30:00Z",
        ]
    )
    run = run_import(db, connector, csv_text)
    assert run.status == "completed"
    source = db.query(SourceRecord).one()
    assert source.provider_id == "place-123"
    assert source.provider_rating == 4.7
    assert source.provider_review_count == 91
    assert source.captured_at == datetime(2026, 7, 20, 10, 30)


def test_release1_live_enrichment_keeps_excerpts_and_verifies_contacts(
    db, connector, monkeypatch
):
    record = SourceRecordIn(
        business_name="Real Wellness",
        category="massage_wellness",
        city="porto",
        website_url="https://real-wellness.pt",
        provider_id="place-live",
        rating=4.8,
        review_count=120,
        provenance=Provenance(
            source="test_provider",
            url="https://provider.example/place-live",
            permitted_use="test",
        ),
    )
    business, _ = ingest_record(db, connector, record)
    db.flush()
    html = """
    <html><head><meta name="viewport" content="width=device-width">
    <meta name="description" content="Massagens terapêuticas no Porto"></head>
    <body><h2>Massagem terapêutica</h2>
    <p>Contacte hello@real-wellness.pt ou +351 912 345 678.</p>
    <a href="/reservas">Reservar agora</a>
    <a href="https://instagram.com/realwellness">Instagram</a>
    <form action="/contacto"><input name="name"></form></body></html>
    """
    page = CrawledPage(
        url="https://real-wellness.pt/",
        status_code=200,
        title="Contacto e serviços",
        text=(
            "Massagem terapêutica. Contacte hello@real-wellness.pt "
            "ou +351 912 345 678. Reservar agora."
        ),
        html=html,
        links=[
            ("https://real-wellness.pt/reservas", "Reservar agora"),
            ("https://instagram.com/realwellness", "Instagram"),
        ],
        meta_description="Massagens terapêuticas no Porto",
        has_viewport=True,
        has_form=True,
    )
    monkeypatch.setattr(
        "app.services.enrichment.crawl_website",
        lambda _url: CrawlResult(_url, [page], []),
    )

    summary = enrich_business(db, business)
    db.flush()
    assert summary["review_required"] is False
    email = (
        db.query(ContactPoint)
        .filter(ContactPoint.business_id == business.id, ContactPoint.channel == "email")
        .one()
    )
    assert email.verified is True
    evidence = (
        db.query(Evidence)
        .filter(Evidence.business_id == business.id, Evidence.fact_key.like("contact_email:%"))
        .one()
    )
    assert "hello@real-wellness.pt" in evidence.evidence_excerpt
    assert evidence.extraction_method == "website_regex"
    assert (
        db.query(Evidence)
        .filter(Evidence.business_id == business.id, Evidence.fact_key == "booking_url")
        .count()
        == 1
    )


def test_release1_preview_gate_requires_verified_public_path(db, connector):
    business = Business(
        name="No Contact Spa",
        category="massage_wellness",
        city="porto",
        dedupe_key="no-contact",
        state=LeadState.SHORTLISTED.value,
    )
    db.add(business)
    db.flush()
    with pytest.raises(LeadEligibilityError):
        assert_preview_eligible(db, business)

    db.add(
        ContactPoint(
            business_id=business.id,
            channel="email",
            value="business@example.org",
            normalized_value="business@example.org",
            verified=True,
            is_business_contact=True,
        )
    )
    db.flush()
    plan = assert_preview_eligible(db, business)
    assert plan["channel"] == "email"
    assert plan["recipient"] == "business@example.org"


def test_release1_asset_package_is_complete_and_idempotent(db):
    discovery = run_porto_wellness_vertical_slice(db, limit=20, top_review=5)
    business = db.get(Business, discovery["review_queue"][0])
    first = approve_and_generate_preview(db, business, actor="human:test")
    second = approve_and_generate_preview(db, business, actor="human:test")

    assert first["proposal"]["id"]
    assert first["recommended_channel"] in {
        "email",
        "contact_form",
        "instagram",
        "phone_call",
    }
    assert first["recipient"]
    assert first["draft"]
    assert first["screenshots"]["desktop"].endswith("desktop.png")
    assert first["screenshots"]["mobile"].endswith("mobile.png")
    assert first["evidence_used"]
    assert db.query(Artifact).filter(Artifact.business_id == business.id).count() >= 3
    assert second["reused"] is True
    assert second["build_id"] == first["build_id"]
    assert (
        db.query(WebsiteBuild).filter(WebsiteBuild.business_id == business.id).count()
        == 1
    )
    assert db.query(Proposal).filter(Proposal.business_id == business.id).count() == 1


def test_release1_outcomes_advance_state_and_keep_versions(db):
    business = Business(
        name="Outcome Spa",
        category="massage_wellness",
        city="porto",
        dedupe_key="outcome-spa",
        state=LeadState.CONTACTED.value,
    )
    db.add(business)
    db.flush()
    capture_outcome(db, business, outcome="positive_reply", actor="human:test", notes="Interested")
    assert business.state == LeadState.ENGAGED.value
    capture_outcome(db, business, outcome="meeting_booked", actor="human:test")
    assert business.state == LeadState.MEETING.value
    capture_outcome(db, business, outcome="won", actor="human:test")
    assert business.state == LeadState.WON.value


def test_release1_google_places_uses_official_json_adapter(db, monkeypatch):
    connector = SourceConnector(
        name="places-test",
        adapter="google_places",
        owner="test",
        permitted_use="provider terms reviewed",
        category="massage_wellness",
        cities=["porto"],
    )
    db.add(connector)
    db.commit()

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {
                "places": [
                    {
                        "id": "place-1",
                        "displayName": {"text": "Porto Real Spa"},
                        "formattedAddress": "Rua Real 1, Porto",
                        "websiteUri": "https://porto-real.example.org",
                        "googleMapsUri": "https://maps.google.com/?cid=1",
                        "nationalPhoneNumber": "912 345 678",
                        "rating": 4.6,
                        "userRatingCount": 80,
                        "businessStatus": "OPERATIONAL",
                        "types": ["spa"],
                    }
                ]
            }

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def post(self, url, headers, json):
            assert url.endswith("places:searchText")
            assert headers["X-Goog-Api-Key"] == "test-key"
            assert "places.id" in headers["X-Goog-FieldMask"]
            assert json["textQuery"] == "massagem em Porto"
            return FakeResponse()

    monkeypatch.setattr("app.adapters.google_places.httpx.Client", FakeClient)
    run = run_google_places(
        db,
        connector,
        query="massagem em Porto",
        city="porto",
        category="massage_wellness",
        limit=1,
        api_key="test-key",
    )
    assert run.status == "completed"
    source = db.query(SourceRecord).one()
    assert source.provider_id == "place-1"
    assert source.provider_rating == 4.6
