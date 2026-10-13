"""CSV/manual import adapter — real P0 connector (§2.2).

Resumable: a failed run keeps its checkpoint and `resume` continues from the
next unprocessed row without duplicating earlier ones (§3.4).
"""

from typing import Optional
import csv
import hashlib
import io
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.schemas import Provenance, SourceRecordIn
from app.models import SourceConnector, SourceRun
from app.services.ingestion import ingest_record

class PayloadMismatch(Exception):
    """Resume was attempted with a different file than the original run."""


DEFAULT_MAPPING = {
    "business_name": "name",
    "category": "category",
    "city": "city",
    "address": "address",
    "website_url": "website",
    "profile_url": "profile_url",
    "email": "email",
    "phone": "phone",
    "instagram": "instagram",
    "provider_id": "provider_id",
    "rating": "rating",
    "review_count": "review_count",
    "captured_at": "captured_at",
}


def _row_to_record(row: dict, mapping: dict, connector: SourceConnector) -> SourceRecordIn:
    def get(field: str) -> str:
        column = mapping.get(field, "")
        return (row.get(column) or "").strip()

    captured_raw = get("captured_at")
    try:
        if captured_raw:
            parsed = datetime.fromisoformat(captured_raw.replace("Z", "+00:00"))
            captured_at = (
                parsed.astimezone(timezone.utc).replace(tzinfo=None)
                if parsed.tzinfo
                else parsed
            )
        else:
            captured_at = datetime.utcnow()
    except ValueError as exc:
        raise ValueError(f"invalid captured_at value: {captured_raw}") from exc

    rating_raw = get("rating")
    reviews_raw = get("review_count")
    return SourceRecordIn(
        business_name=get("business_name"),
        category=get("category") or "unknown",
        city=get("city") or "unknown",
        address=get("address"),
        website_url=get("website_url"),
        profile_url=get("profile_url"),
        email=get("email"),
        phone=get("phone"),
        instagram=get("instagram"),
        provider_id=get("provider_id"),
        rating=float(rating_raw) if rating_raw else None,
        review_count=int(reviews_raw) if reviews_raw else None,
        captured_at=captured_at,
        provenance=Provenance(
            source=connector.name,
            url=get("profile_url"),
            captured_at=captured_at,
            permitted_use=connector.permitted_use,
        ),
    )


def run_import(
    db: Session,
    connector: SourceConnector,
    csv_text: str,
    *,
    resume_run: Optional[SourceRun] = None,
) -> SourceRun:
    mapping = {**DEFAULT_MAPPING, **(connector.field_mapping or {})}
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    payload_hash = hashlib.sha256(csv_text.encode()).hexdigest()

    run = resume_run or SourceRun(connector_id=connector.id, status="running", payload_sha256=payload_hash)
    if resume_run:
        # The checkpoint is a row index into the original file; a different file
        # would silently misalign it and corrupt the import.
        if resume_run.payload_sha256 and resume_run.payload_sha256 != payload_hash:
            raise PayloadMismatch(resume_run.payload_sha256)
        run.status = "running"
        run.error = None
    db.add(run)
    db.flush()

    start_index = run.checkpoint
    quota = connector.quota_per_run or len(rows)

    try:
        for index in range(start_index, min(len(rows), start_index + quota)):
            row = rows[index]
            try:
                record = _row_to_record(row, mapping, connector)
            except Exception:
                run.records_skipped += 1
                run.checkpoint = index + 1
                continue
            if not record.business_name:
                run.records_skipped += 1
                run.checkpoint = index + 1
                continue
            ingest_record(db, connector, record, route="discovered", source_run_id=run.id)
            run.records_ingested += 1
            run.checkpoint = index + 1
        run.status = "completed"
        run.finished_at = datetime.utcnow()
    except Exception as exc:
        # Checkpoint already points at the failed row; resume continues there
        # without blocking other runs or duplicating processed rows.
        run.status = "failed"
        run.error = str(exc)
    db.add(run)
    db.commit()
    return run
