"""Official Google Places API (New) connector.

This adapter uses Text Search over the documented JSON API. It never scrapes
Google Maps HTML. The requested field mask is deliberately narrow because
Places billing depends on the fields requested.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.core.schemas import Provenance, SourceRecordIn
from app.models import SourceConnector, SourceRun
from app.services.ingestion import ingest_record

PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACES_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.websiteUri",
        "places.googleMapsUri",
        "places.nationalPhoneNumber",
        "places.rating",
        "places.userRatingCount",
        "places.businessStatus",
        "places.types",
        "places.regularOpeningHours",
        "nextPageToken",
    ]
)


class PlacesConfigurationError(RuntimeError):
    pass


class PlacesProviderError(RuntimeError):
    pass


def _record_from_place(
    place: dict,
    connector: SourceConnector,
    *,
    city: str,
    category: str,
    captured_at: datetime,
) -> SourceRecordIn:
    name = (place.get("displayName") or {}).get("text", "").strip()
    provider_id = (place.get("id") or "").strip()
    maps_url = (place.get("googleMapsUri") or "").strip()
    return SourceRecordIn(
        business_name=name,
        category=category or connector.category or "unknown",
        city=(city or (connector.cities or ["unknown"])[0]).strip().lower(),
        address=(place.get("formattedAddress") or "").strip(),
        website_url=(place.get("websiteUri") or "").strip(),
        profile_url=maps_url,
        phone=(place.get("nationalPhoneNumber") or "").strip(),
        provider_id=provider_id,
        rating=place.get("rating"),
        review_count=place.get("userRatingCount"),
        captured_at=captured_at,
        extra={
            "provider": "google_places",
            "business_status": place.get("businessStatus", ""),
            "types": place.get("types") or [],
            "opening_hours": place.get("regularOpeningHours") or {},
        },
        provenance=Provenance(
            source="google_places_api",
            url=maps_url,
            captured_at=captured_at,
            permitted_use=connector.permitted_use,
        ),
    )


def run_google_places(
    db: Session,
    connector: SourceConnector,
    *,
    query: str,
    city: str,
    category: str,
    limit: int = 20,
    api_key: Optional[str] = None,
) -> SourceRun:
    """Discover up to 60 businesses using the official Text Search API."""
    key = api_key or settings.google_places_api_key
    if not key:
        raise PlacesConfigurationError("GOOGLE_PLACES_API_KEY is required")
    if not query.strip():
        raise ValueError("query is required")

    requested = max(1, min(limit, 60))
    run = SourceRun(connector_id=connector.id, status="running")
    db.add(run)
    db.flush()

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": PLACES_FIELD_MASK,
    }
    page_token = ""
    seen_ids: set[str] = set()
    captured_at = datetime.utcnow()

    try:
        with httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=20.0, write=10.0, pool=5.0),
            follow_redirects=True,
        ) as client:
            while run.records_ingested + run.records_skipped < requested:
                remaining = requested - run.records_ingested - run.records_skipped
                payload: dict = {
                    "textQuery": query.strip(),
                    "pageSize": min(20, remaining),
                    "languageCode": "pt-PT",
                    "regionCode": "PT",
                }
                if page_token:
                    payload["pageToken"] = page_token
                response = client.post(PLACES_TEXT_SEARCH_URL, headers=headers, json=payload)
                if response.status_code >= 400:
                    raise PlacesProviderError(
                        f"Places API returned {response.status_code}: {response.text[:500]}"
                    )
                data = response.json()
                places = data.get("places") or []
                if not places:
                    break
                for place in places:
                    if run.records_ingested + run.records_skipped >= requested:
                        break
                    provider_id = (place.get("id") or "").strip()
                    if not provider_id or provider_id in seen_ids:
                        run.records_skipped += 1
                        continue
                    seen_ids.add(provider_id)
                    if place.get("businessStatus") == "CLOSED_PERMANENTLY":
                        run.records_skipped += 1
                        continue
                    record = _record_from_place(
                        place,
                        connector,
                        city=city,
                        category=category,
                        captured_at=captured_at,
                    )
                    if not record.business_name:
                        run.records_skipped += 1
                        continue
                    _, created = ingest_record(
                        db,
                        connector,
                        record,
                        route="discovered",
                        source_run_id=run.id,
                    )
                    if created:
                        run.records_ingested += 1
                    else:
                        run.records_skipped += 1
                    run.checkpoint += 1

                page_token = data.get("nextPageToken") or ""
                run.cursor_after = page_token
                if not page_token:
                    break

        run.status = "completed"
        run.finished_at = datetime.utcnow()
        connector.last_run_at = run.finished_at
        connector.record_count = (connector.record_count or 0) + run.records_ingested
        connector.error_count = (connector.error_count or 0) + run.error_count
        connector.cursor = page_token
        db.add(connector)
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)
        run.error_count = (run.error_count or 0) + 1
        run.finished_at = datetime.utcnow()
        connector.error_count = (connector.error_count or 0) + 1
        db.add(connector)
        db.add(run)
        db.commit()
        raise

    db.add(run)
    db.commit()
    return run
