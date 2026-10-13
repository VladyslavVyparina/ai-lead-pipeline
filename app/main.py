"""AI Lead Pipeline — control plane API.

Deterministic orchestrator endpoints: source connectors, CSV import, generic
inbound webhook (P0 contract), qualification, website/proposal factory,
approval-gated outreach, config versioning and KPI analytics.
"""

from typing import Literal, Optional
import logging
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT, settings
from app.core.schemas import InboundLeadIn
from app.core.state_machine import InvalidTransition, LeadState
from app.database import Base, engine, get_db
from app.migrations import backfill_normalized_contacts, migrate_sqlite
from app.models import (
    AIUsageLedger,
    Artifact,
    Business,
    ContactPoint,
    Evidence,
    LeadOutcome,
    Message,
    PipelineJob,
    PreviewSubmission,
    Qualification,
    Proposal,
    SourceConnector,
    SourceRecord,
    SourceRun,
    WebsiteAudit,
    WebsiteBuild,
)
from app.adapters.csv_import import PayloadMismatch, run_import
from app.adapters.directory_seed import ensure_porto_wellness_connector
from app.services import config_loader
from app.services.analytics import kpi_snapshot
from app.services.events import record_event, transition
from app.services.ingestion import ingest_inbound
from app.services.enrichment import enrich_business, fact_status_summary
from app.services.lead_review import (
    LeadEligibilityError,
    exclusion_warnings,
    recommend_channel,
)
from app.services.outcomes import capture_outcome
from app.services.outreach import (
    OutreachBlocked,
    approve_message,
    draft_message,
    draft_personalized_message,
    mark_sent,
    suppress,
)
from app.services.pipeline import (
    approve_and_generate_preview,
    discover_places_enrich_score,
    discover_enrich_score,
    run_porto_wellness_vertical_slice,
)
from app.services.proposal import PricebookError, build_proposal
from app.services.proposal_pdf import ensure_proposal_pdf
from app.services.preview_forms import rate_limit_exceeded, valid_form_token
from app.services.scoring import assign_tiers, score_business
from app.services.site_factory import FactValidationError, build_and_deploy_preview, expire_previews
from app.services.task_queue import enqueue
from app.services.artifact_storage import ArtifactStorageError, LocalArtifactStore, get_artifact_store
import hashlib

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")

from app.ui import router as ui_router

settings.validate_runtime()
app = FastAPI(title="AI Lead Pipeline", version="0.1.0")
(PROJECT_ROOT / "artifacts").mkdir(parents=True, exist_ok=True)
app.mount("/artifacts", StaticFiles(directory=str(PROJECT_ROOT / "artifacts")), name="artifacts")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=settings.preview_origin_regex,
    allow_credentials=False,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
if settings.app_env != "production":
    Base.metadata.create_all(bind=engine)
    migrate_sqlite(engine)
    backfill_normalized_contacts(engine)
app.include_router(ui_router, prefix="/ui", include_in_schema=False)

logger = logging.getLogger("ai_lead.api")

_DEFAULT_SECRETS = {"change_this_token", "change_this_secret", ""}
if settings.admin_token in _DEFAULT_SECRETS or settings.inbound_webhook_secret in _DEFAULT_SECRETS:
    logger.warning(
        "SECURITY: ADMIN_TOKEN and/or INBOUND_WEBHOOK_SECRET still use default values. "
        "Set strong secrets in .env before exposing this service."
    )


def require_admin(x_admin_token: str = Header(default="")) -> None:
    if not secrets.compare_digest(x_admin_token, settings.admin_token):
        raise HTTPException(status_code=401, detail="invalid admin token")


def require_webhook_secret(x_webhook_secret: str = Header(default="")) -> None:
    if not secrets.compare_digest(x_webhook_secret, settings.inbound_webhook_secret):
        raise HTTPException(status_code=401, detail="invalid webhook secret")


def get_business(db: Session, business_id: int) -> Business:
    business = db.get(Business, business_id)
    if not business:
        raise HTTPException(status_code=404, detail="business not found")
    return business


@app.get("/")
def root():
    return RedirectResponse("/ui", status_code=307)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error("Database health check failed: %s", exc)
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"ok": True}


@app.get("/private-artifacts/{artifact_id}/download", dependencies=[Depends(require_admin)])
def download_private_artifact(artifact_id: int, db: Session = Depends(get_db)):
    """Serve a local dev artifact or issue a short-lived R2 download URL."""
    artifact = db.get(Artifact, artifact_id)
    if not artifact or artifact.deleted_at is not None:
        raise HTTPException(status_code=404, detail="artifact not found")
    try:
        store = get_artifact_store()
        if artifact.storage_backend == "r2":
            return RedirectResponse(store.signed_download_url(artifact.object_key, expires_seconds=300))
        if isinstance(store, LocalArtifactStore):
            path = store.path_for(artifact.object_key)
            if not path.is_file():
                raise HTTPException(status_code=404, detail="artifact bytes not found")
            return FileResponse(path, media_type=artifact.content_type, filename=path.name)
    except ArtifactStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    raise HTTPException(status_code=409, detail="artifact backend does not match configured storage")


# --- Source connectors and ingestion -----------------------------------------


class ConnectorIn(BaseModel):
    name: str
    adapter: str  # csv_import | inbound_webhook | directory_seed
    owner: str
    permitted_use: str
    field_mapping: dict = {}
    cities: list[str] = []
    category: str = ""
    catalog_ref: str = ""
    quota_per_run: int = 500
    retention_days: int = 180


@app.post("/connectors", dependencies=[Depends(require_admin)])
def create_connector(payload: ConnectorIn, db: Session = Depends(get_db)):
    connector = SourceConnector(**payload.model_dump())
    db.add(connector)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"connector name already exists: {payload.name}")
    db.refresh(connector)
    return {"id": connector.id, "name": connector.name}


@app.get("/connectors", dependencies=[Depends(require_admin)])
def list_connectors(db: Session = Depends(get_db)):
    return [
        {
            "id": c.id,
            "name": c.name,
            "adapter": c.adapter,
            "active": c.is_active,
            "city": (c.cities or [None])[0],
            "category": c.category,
            "record_count": c.record_count,
            "error_count": c.error_count,
            "last_run_at": c.last_run_at.isoformat() if c.last_run_at else None,
            "next_run_at": c.next_run_at.isoformat() if c.next_run_at else None,
            "cursor": c.cursor,
        }
        for c in db.query(SourceConnector).all()
    ]


@app.post("/connectors/porto-wellness/ensure", dependencies=[Depends(require_admin)])
def ensure_porto_connector(db: Session = Depends(get_db)):
    connector = ensure_porto_wellness_connector(db)
    return {"id": connector.id, "name": connector.name, "adapter": connector.adapter}


@app.post("/connectors/{connector_id}/run", dependencies=[Depends(require_admin)])
def run_connector_pipeline(
    connector_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    top_review: int = Query(default=5, ge=1, le=15),
    db: Session = Depends(get_db),
):
    """Run discovery → enrich → FitQL → shortlist top N for preview approval."""
    connector = db.get(SourceConnector, connector_id)
    if not connector or not connector.is_active:
        raise HTTPException(status_code=404, detail="connector not found or inactive")
    if connector.adapter != "directory_seed":
        raise HTTPException(status_code=400, detail="only directory_seed supports /run automation")
    try:
        result = discover_enrich_score(db, connector, limit=limit, top_review=top_review)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return result


class PlacesDiscoveryIn(BaseModel):
    query: str = Field(min_length=3, max_length=200)
    city: str = Field(default="porto", min_length=2, max_length=64)
    category: str = Field(default="massage_wellness", min_length=2, max_length=128)
    limit: int = Field(default=20, ge=1, le=60)
    top_review: int = Field(default=5, ge=1, le=15)


@app.post("/connectors/{connector_id}/discover", dependencies=[Depends(require_admin)])
def discover_real_businesses(
    connector_id: int,
    payload: PlacesDiscoveryIn,
    db: Session = Depends(get_db),
):
    """Official Places API -> live website enrichment -> FitQL -> review queue."""
    connector = db.get(SourceConnector, connector_id)
    if not connector or not connector.is_active:
        raise HTTPException(status_code=404, detail="connector not found or inactive")
    if connector.adapter != "google_places":
        raise HTTPException(status_code=400, detail="connector adapter must be google_places")
    try:
        return discover_places_enrich_score(
            db,
            connector,
            query=payload.query,
            city=payload.city,
            category=payload.category,
            limit=payload.limit,
            top_review=payload.top_review,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/pipeline/porto-wellness", dependencies=[Depends(require_admin)])
def porto_wellness_slice(
    limit: int = Query(default=20, ge=1, le=100),
    top_review: int = Query(default=5, ge=1, le=15),
    db: Session = Depends(get_db),
):
    """One-shot vertical slice for the Porto massage/wellness pilot."""
    try:
        return run_porto_wellness_vertical_slice(db, limit=limit, top_review=top_review)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/pipeline/jobs", dependencies=[Depends(require_admin)])
def pipeline_jobs(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    jobs = db.query(PipelineJob).order_by(PipelineJob.id.desc()).limit(limit).all()
    return [
        {
            "id": j.id,
            "job_type": j.job_type,
            "status": j.status,
            "stage": j.stage,
            "business_id": j.business_id,
            "attempts": j.attempts,
            "cost_units": j.cost_units,
            "error": j.error,
            "result": j.result,
        }
        for j in jobs
    ]


@app.post("/businesses/{business_id}/research-async", dependencies=[Depends(require_admin)])
def enqueue_business_research(business_id: int, db: Session = Depends(get_db)):
    get_business(db, business_id)
    return enqueue("lead.crawl_research", business_id=business_id).to_dict()


@app.post("/businesses/{business_id}/approve-preview-async", dependencies=[Depends(require_admin)])
def enqueue_approved_preview(business_id: int, db: Session = Depends(get_db)):
    business = get_business(db, business_id)
    assert_preview_eligible(db, business)
    return enqueue("lead.preview", business_id=business_id).to_dict()


@app.post("/website-builds/{build_id}/qa-async", dependencies=[Depends(require_admin)])
def enqueue_preview_qa(build_id: int, db: Session = Depends(get_db)):
    if not db.get(WebsiteBuild, build_id):
        raise HTTPException(status_code=404, detail="website build not found")
    return enqueue("lead.qa", build_id=build_id).to_dict()


MAX_CSV_BYTES = 20 * 1024 * 1024  # 20 MB is far beyond any pilot batch


async def _read_csv_upload(file: UploadFile) -> str:
    payload = await file.read()
    if len(payload) > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="csv file too large (max 20 MB)")
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="file is not valid UTF-8 text; export the CSV as UTF-8")


@app.post("/connectors/{connector_id}/import-csv", dependencies=[Depends(require_admin)])
async def import_csv(connector_id: int, file: UploadFile, db: Session = Depends(get_db)):
    connector = db.get(SourceConnector, connector_id)
    if not connector or not connector.is_active:
        raise HTTPException(status_code=404, detail="connector not found or inactive")
    csv_text = await _read_csv_upload(file)
    run = run_import(db, connector, csv_text)
    return {
        "run_id": run.id,
        "status": run.status,
        "ingested": run.records_ingested,
        "skipped": run.records_skipped,
        "checkpoint": run.checkpoint,
        "error": run.error,
    }


@app.post("/source-runs/{run_id}/resume", dependencies=[Depends(require_admin)])
async def resume_run(run_id: int, file: UploadFile, db: Session = Depends(get_db)):
    run = db.get(SourceRun, run_id)
    if not run or run.status != "failed":
        raise HTTPException(status_code=404, detail="failed run not found")
    connector = db.get(SourceConnector, run.connector_id)
    csv_text = await _read_csv_upload(file)
    try:
        run = run_import(db, connector, csv_text, resume_run=run)
    except PayloadMismatch:
        raise HTTPException(
            status_code=409,
            detail="uploaded file differs from the original import; resume requires the same CSV",
        )
    return {"run_id": run.id, "status": run.status, "ingested": run.records_ingested, "checkpoint": run.checkpoint}


@app.post("/webhooks/inbound", dependencies=[Depends(require_webhook_secret)])
def inbound_webhook(payload: InboundLeadIn, db: Session = Depends(get_db)):
    """Generic inbound contract (P0). Meta Lead Ads maps here in P1."""
    connector = (
        db.query(SourceConnector)
        .filter(SourceConnector.adapter == "inbound_webhook", SourceConnector.is_active.is_(True))
        .first()
    )
    if not connector:
        raise HTTPException(status_code=503, detail="no active inbound connector configured")
    business, created = ingest_inbound(db, connector, payload)
    db.commit()
    return {"ok": True, "business_id": business.id, "created": created, "state": business.state}


class PreviewFormIn(BaseModel):
    build_id: int = Field(gt=0)
    form_token: str = Field(min_length=64, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    contact: str = Field(min_length=3, max_length=200)
    message: str = Field(default="", max_length=2000)
    utm_source: str = Field(default="", max_length=100)
    utm_medium: str = Field(default="", max_length=100)
    utm_campaign: str = Field(default="", max_length=100)


@app.post("/preview-form")
def preview_form(payload: PreviewFormIn, request: Request, db: Session = Depends(get_db)):
    """Controlled operator endpoint for preview-site booking/contact forms (§5.3).

    Public by design (forms on preview sites can't hold secrets); it only logs
    an event for the operator and never routes anything to the business.
    """
    client_key = request.client.host if request.client else "unknown"
    if rate_limit_exceeded(client_key):
        raise HTTPException(status_code=429, detail="too many form submissions")
    build = db.get(WebsiteBuild, payload.build_id)
    if not build:
        raise HTTPException(status_code=404, detail="preview build not found")
    if build.status not in {"building", "deployed"}:
        raise HTTPException(status_code=410, detail="preview is no longer active")
    if not valid_form_token(build.id, payload.form_token):
        raise HTTPException(status_code=403, detail="invalid preview form token")

    dedupe_key = hashlib.sha256(
        f"{build.id}|{payload.contact.strip().lower()}|{payload.message.strip()[:200]}".encode()
    ).hexdigest()
    existing = (
        db.query(PreviewSubmission)
        .filter(PreviewSubmission.dedupe_key == dedupe_key)
        .order_by(PreviewSubmission.created_at.desc())
        .first()
    )
    if existing:
        existing.status = "duplicate"
        db.add(existing)
        record_event(
            db,
            action="preview_form_duplicate",
            actor="system:preview_site",
            business_id=build.business_id,
            entity="preview_submission",
            entity_id=existing.id,
            payload={"build_id": build.id, "grouped_with": existing.id},
        )
        db.commit()
        return {"ok": True, "duplicate": True, "submission_id": existing.id}

    attribution = {
        "preview_version": build.id,
        "pipeline_stage": build.pipeline_stage,
        "template_id": build.template_id,
        "template_version": build.template_version,
        "utm_source": payload.utm_source,
        "utm_medium": payload.utm_medium,
        "utm_campaign": payload.utm_campaign,
    }
    submission = PreviewSubmission(
        website_build_id=build.id,
        business_id=build.business_id,
        name=payload.name,
        contact=payload.contact,
        message=payload.message,
        dedupe_key=dedupe_key,
        attribution=attribution,
    )
    db.add(submission)
    db.flush()
    business = db.get(Business, build.business_id)
    if business and LeadState(business.state) in {LeadState.PREVIEW_READY, LeadState.APPROVED, LeadState.CONTACTED}:
        # Inbound interest signal — do not auto-SQL
        record_event(
            db,
            action="preview_lead_capture",
            actor="system:preview_site",
            business_id=business.id,
            entity="preview_submission",
            entity_id=submission.id,
            payload={"build_id": build.id},
        )
    record_event(
        db,
        action="preview_form_submission",
        actor="system:preview_site",
        business_id=build.business_id,
        entity="website_build",
        entity_id=build.id,
        payload={
            "submission_id": submission.id,
            "build_id": build.id,
            "attribution": attribution,
        },
    )
    db.commit()
    return {"ok": True, "submission_id": submission.id}


# --- Verification, evidence and qualification ---------------------------------


class EvidenceIn(BaseModel):
    fact_key: str
    fact_value: object
    source_url: str = ""
    confidence: float = 1.0


@app.post("/businesses/{business_id}/enrich", dependencies=[Depends(require_admin)])
def enrich_live_business(business_id: int, db: Session = Depends(get_db)):
    business = get_business(db, business_id)
    summary = enrich_business(db, business, actor="human:operator")
    if LeadState(business.state) == LeadState.NEW:
        transition(
            db,
            business,
            LeadState.VALIDATED,
            actor="system:enrichment",
            reason="live website enrichment completed",
        )
    db.commit()
    return summary


@app.post("/businesses/{business_id}/reject", dependencies=[Depends(require_admin)])
def reject_business(business_id: int, db: Session = Depends(get_db)):
    business = get_business(db, business_id)
    try:
        transition(
            db,
            business,
            LeadState.REJECTED,
            actor="human:operator",
            reason="explicit lead rejection",
        )
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    return {"id": business.id, "state": business.state}


@app.post("/businesses/{business_id}/evidence", dependencies=[Depends(require_admin)])
def add_evidence(business_id: int, items: list[EvidenceIn], db: Session = Depends(get_db)):
    business = get_business(db, business_id)
    for item in items:
        db.add(Evidence(business_id=business.id, **item.model_dump()))
    db.commit()
    return {"ok": True, "count": len(items)}


class AuditIn(BaseModel):
    has_website: bool = False
    mobile_ok: bool = False
    has_booking_cta: bool = False
    services_clear: bool = False
    contact_clear: bool = False
    notes: str = ""


@app.post("/businesses/{business_id}/audit", dependencies=[Depends(require_admin)])
def add_audit(business_id: int, payload: AuditIn, db: Session = Depends(get_db)):
    business = get_business(db, business_id)
    db.add(WebsiteAudit(business_id=business.id, **payload.model_dump()))
    db.commit()
    return {"ok": True}


@app.post("/businesses/{business_id}/contacts/{contact_id}/verify", dependencies=[Depends(require_admin)])
def verify_contact(business_id: int, contact_id: int, db: Session = Depends(get_db)):
    """Operator confirms a contact path is real and permitted (§4.2 contactability)."""
    contact = db.get(ContactPoint, contact_id)
    if not contact or contact.business_id != business_id:
        raise HTTPException(status_code=404, detail="contact not found for this business")
    contact.verified = True
    db.add(contact)
    record_event(
        db,
        action="contact_verified",
        actor="human:operator",
        business_id=business_id,
        entity="contact_point",
        entity_id=contact.id,
        payload={"channel": contact.channel},
    )
    db.commit()
    return {"ok": True, "channel": contact.channel, "verified": True}


class TransitionIn(BaseModel):
    target: LeadState
    actor: str
    reason: str = ""


@app.post("/businesses/{business_id}/transition", dependencies=[Depends(require_admin)])
def transition_business(business_id: int, payload: TransitionIn, db: Session = Depends(get_db)):
    business = get_business(db, business_id)
    try:
        transition(db, business, payload.target, actor=payload.actor, reason=payload.reason)
    except InvalidTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    return {"ok": True, "state": business.state}


@app.post("/businesses/{business_id}/score", dependencies=[Depends(require_admin)])
def score(business_id: int, db: Session = Depends(get_db)):
    business = get_business(db, business_id)
    qualification = score_business(db, business)
    if LeadState(business.state) == LeadState.NEW:
        transition(db, business, LeadState.VALIDATED, actor="system:scoring", reason="scored")
    if LeadState(business.state) == LeadState.VALIDATED:
        target = LeadState.FITQL if qualification.routing != "reject" else LeadState.REJECTED
        transition(db, business, target, actor="system:scoring", reason=f"total={qualification.total}")
    db.commit()
    return {
        "total": qualification.total,
        "scores": qualification.scores,
        "breakdown": qualification.breakdown,
        "reasons": qualification.reasons,
        "routing": qualification.routing,
        "rubric_version": qualification.rubric_version,
        "state": business.state,
    }


@app.post("/businesses/{business_id}/approve-preview", dependencies=[Depends(require_admin)])
def approve_preview(business_id: int, db: Session = Depends(get_db)):
    """Human gate: approve shortlisted lead → template-driven preview + outreach draft."""
    business = get_business(db, business_id)
    try:
        result = approve_and_generate_preview(db, business, actor="human:operator")
    except LeadEligibilityError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "lead_not_eligible", "warnings": exc.warnings},
        )
    except FactValidationError as exc:
        raise HTTPException(status_code=422, detail={"code": "low_confidence_facts", "facts": exc.flagged})
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return result


@app.post("/businesses/{business_id}/outreach-draft", dependencies=[Depends(require_admin)])
def create_personalized_draft(business_id: int, channel: str = "email", db: Session = Depends(get_db)):
    business = get_business(db, business_id)
    latest_build = (
        db.query(WebsiteBuild)
        .filter(WebsiteBuild.business_id == business.id, WebsiteBuild.status == "deployed")
        .order_by(WebsiteBuild.created_at.desc())
        .first()
    )
    message = draft_personalized_message(
        db,
        business,
        channel=channel,
        touch_number=1,
        preview_url=latest_build.preview_url if latest_build else "",
    )
    db.commit()
    return {
        "message_id": message.id,
        "status": message.status,
        "body": message.body,
        "research_snapshot": message.research_snapshot,
    }


@app.post("/qualifications/assign-tiers", dependencies=[Depends(require_admin)])
def tiers(db: Session = Depends(get_db)):
    result = assign_tiers(db)
    db.commit()
    return result


@app.get("/businesses", dependencies=[Depends(require_admin)])
def list_businesses(
    state: Optional[str] = None,
    city: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Business)
    if state:
        query = query.filter(Business.state == state)
    if city:
        query = query.filter(Business.city == city)
    total = query.count()
    items = query.order_by(Business.id).offset(offset).limit(limit).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {"id": b.id, "name": b.name, "category": b.category, "city": b.city, "state": b.state, "route": b.route}
            for b in items
        ],
    }


@app.get("/businesses/{business_id}", dependencies=[Depends(require_admin)])
def business_detail(business_id: int, db: Session = Depends(get_db)):
    b = get_business(db, business_id)
    latest_q = (
        db.query(Qualification)
        .filter(Qualification.business_id == b.id)
        .order_by(Qualification.created_at.desc())
        .first()
    )
    latest_audit = (
        db.query(WebsiteAudit)
        .filter(WebsiteAudit.business_id == b.id)
        .order_by(WebsiteAudit.created_at.desc())
        .first()
    )
    sources = (
        db.query(SourceRecord)
        .filter(SourceRecord.business_id == b.id)
        .order_by(SourceRecord.created_at.desc())
        .all()
    )
    evidence = (
        db.query(Evidence)
        .filter(Evidence.business_id == b.id)
        .order_by(Evidence.captured_at.desc())
        .all()
    )
    builds = (
        db.query(WebsiteBuild)
        .filter(WebsiteBuild.business_id == b.id)
        .order_by(WebsiteBuild.created_at.desc())
        .all()
    )
    proposals = (
        db.query(Proposal)
        .filter(Proposal.business_id == b.id)
        .order_by(Proposal.created_at.desc())
        .all()
    )
    messages = (
        db.query(Message)
        .filter(Message.business_id == b.id)
        .order_by(Message.created_at.desc())
        .all()
    )
    outcomes = (
        db.query(LeadOutcome)
        .filter(LeadOutcome.business_id == b.id)
        .order_by(LeadOutcome.created_at.desc())
        .all()
    )
    ai_usage = (
        db.query(AIUsageLedger)
        .filter(AIUsageLedger.business_id == b.id)
        .order_by(AIUsageLedger.created_at.desc())
        .all()
    )
    return {
        "id": b.id,
        "name": b.name,
        "category": b.category,
        "city": b.city,
        "state": b.state,
        "route": b.route,
        "contacts": [
            {"id": c.id, "channel": c.channel, "value": c.value, "verified": c.verified}
            for c in db.query(ContactPoint).filter(ContactPoint.business_id == b.id)
        ],
        "sources": [
            {
                "id": source.id,
                "provider_id": source.provider_id,
                "rating": source.provider_rating,
                "review_count": source.provider_review_count,
                "captured_at": source.captured_at,
                "provenance": source.provenance,
                "raw": source.raw,
            }
            for source in sources
        ],
        "evidence": [
            {
                "id": item.id,
                "fact_key": item.fact_key,
                "fact_value": item.fact_value,
                "source_url": item.source_url,
                "evidence_excerpt": item.evidence_excerpt,
                "extraction_method": item.extraction_method,
                "confidence": item.confidence,
                "status": item.status,
                "captured_at": item.captured_at,
            }
            for item in evidence
        ],
        "latest_audit": (
            {
                "has_website": latest_audit.has_website,
                "mobile_ok": latest_audit.mobile_ok,
                "has_booking_cta": latest_audit.has_booking_cta,
                "services_clear": latest_audit.services_clear,
                "contact_clear": latest_audit.contact_clear,
                "notes": latest_audit.notes,
                "created_at": latest_audit.created_at,
            }
            if latest_audit
            else None
        ),
        "qualification": (
            {
                "total": latest_q.total,
                "routing": latest_q.routing,
                "tier": latest_q.tier,
                "breakdown": latest_q.breakdown,
                "reasons": latest_q.reasons,
                "scores": latest_q.scores,
            }
            if latest_q
            else None
        ),
        "fact_status": fact_status_summary(db, b),
        "exclusion_warnings": exclusion_warnings(db, b),
        "recommended_contact": recommend_channel(db, b),
        "builds": [
            {
                "id": build.id,
                "status": build.status,
                "stage": build.pipeline_stage,
                "preview_url": build.preview_url,
                "qa": build.qa_report,
            }
            for build in builds
        ],
        "proposals": [
            {
                "id": proposal.id,
                "offer_package": proposal.offer_package,
                "status": proposal.status,
                "content": proposal.content,
                "created_at": proposal.created_at,
            }
            for proposal in proposals
        ],
        "messages": [
            {
                "id": message.id,
                "channel": message.channel,
                "copy_version": message.copy_version,
                "status": message.status,
                "body": message.body,
                "research_snapshot": message.research_snapshot,
                "created_at": message.created_at,
            }
            for message in messages
        ],
        "outcomes": [
            {
                "id": outcome.id,
                "outcome": outcome.outcome,
                "message_id": outcome.message_id,
                "proposal_id": outcome.proposal_id,
                "loss_reason": outcome.loss_reason,
                "notes": outcome.notes,
                "actor": outcome.actor,
                "created_at": outcome.created_at,
            }
            for outcome in outcomes
        ],
        "ai_usage": [
            {
                "id": usage.id,
                "operation": usage.operation,
                "provider": usage.provider,
                "model": usage.model,
                "request_id": usage.provider_request_id,
                "input_tokens": usage.input_tokens,
                "cached_input_tokens": usage.cached_input_tokens,
                "output_tokens": usage.output_tokens,
                "total_tokens": usage.total_tokens,
                "estimated_cost_usd": usage.estimated_cost_usd,
                "latency_ms": usage.latency_ms,
                "status": usage.status,
                "created_at": usage.created_at,
            }
            for usage in ai_usage
        ],
    }


# --- Website and proposal factory ---------------------------------------------


@app.post("/businesses/{business_id}/build-preview", dependencies=[Depends(require_admin)])
def build_preview(business_id: int, db: Session = Depends(get_db)):
    business = get_business(db, business_id)
    try:
        build = build_and_deploy_preview(db, business, actor="human:operator")
    except FactValidationError as exc:
        raise HTTPException(status_code=422, detail={"code": "low_confidence_facts", "facts": exc.flagged})
    if build.status == "deployed" and LeadState(business.state) == LeadState.SHORTLISTED:
        transition(db, business, LeadState.PREVIEW_READY, actor="system:site_factory", reason=build.preview_url)
    db.commit()
    return {
        "build_id": build.id,
        "status": build.status,
        "preview_url": build.preview_url,
        "qa": build.qa_report,
        "expires_at": build.expires_at.isoformat() if build.expires_at else None,
    }


class ProposalIn(BaseModel):
    offer_package: str  # basic | local_pro | automation_pro


@app.post("/businesses/{business_id}/proposal", dependencies=[Depends(require_admin)])
def create_proposal(business_id: int, payload: ProposalIn, db: Session = Depends(get_db)):
    business = get_business(db, business_id)
    try:
        proposal = build_proposal(db, business, offer_package=payload.offer_package, actor="human:operator")
        pdf = ensure_proposal_pdf(db, business=business, proposal=proposal)
    except PricebookError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return {
        "proposal_id": proposal.id,
        "pricebook_version": proposal.pricebook_version,
        "content": proposal.content,
        "pdf_artifact_id": pdf.id,
        "pdf_download_path": f"/private-artifacts/{pdf.id}/download",
    }


@app.post("/jobs/expire-previews", dependencies=[Depends(require_admin)])
def job_expire_previews(db: Session = Depends(get_db)):
    count = expire_previews(db)
    db.commit()
    return {"expired": count}


# --- Outreach (human-approved, guarded) ---------------------------------------


class DraftIn(BaseModel):
    channel: str
    touch_number: int = 1
    body: str
    idempotency_key: str


@app.post("/businesses/{business_id}/messages", dependencies=[Depends(require_admin)])
def create_draft(business_id: int, payload: DraftIn, db: Session = Depends(get_db)):
    business = get_business(db, business_id)
    message = draft_message(
        db,
        business,
        channel=payload.channel,
        touch_number=payload.touch_number,
        body=payload.body,
        idempotency_key=payload.idempotency_key,
    )
    db.commit()
    return {"message_id": message.id, "status": message.status}


class ApproveIn(BaseModel):
    approver: str


@app.post("/messages/{message_id}/approve", dependencies=[Depends(require_admin)])
def approve(message_id: int, payload: ApproveIn, db: Session = Depends(get_db)):
    message = db.get(Message, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="message not found")
    try:
        approve_message(db, message, payload.approver)
    except OutreachBlocked as exc:
        raise HTTPException(status_code=409, detail=exc.code)
    db.commit()
    return {"ok": True, "status": message.status}


@app.post("/messages/{message_id}/mark-sent", dependencies=[Depends(require_admin)])
def sent(message_id: int, db: Session = Depends(get_db)):
    message = db.get(Message, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="message not found")
    try:
        mark_sent(db, message, actor="human:operator")
    except OutreachBlocked as exc:
        raise HTTPException(status_code=409, detail=exc.code)
    business = db.get(Business, message.business_id)
    if LeadState(business.state) == LeadState.APPROVED:
        transition(db, business, LeadState.CONTACTED, actor="system:outreach", reason=f"touch {message.touch_number}")
    db.commit()
    return {"ok": True, "status": message.status}


class SuppressIn(BaseModel):
    channel: Optional[str] = None
    reason: str  # opt_out | bounce | legal | manual


@app.post("/businesses/{business_id}/suppress", dependencies=[Depends(require_admin)])
def suppress_business(business_id: int, payload: SuppressIn, db: Session = Depends(get_db)):
    business = get_business(db, business_id)
    suppress(db, business, channel=payload.channel, reason=payload.reason, actor="human:operator")
    db.commit()
    return {"ok": True, "state": business.state}


class OutcomeIn(BaseModel):
    outcome: Literal[
        "replied",
        "positive_reply",
        "meeting_booked",
        "proposal_sent",
        "won",
        "lost",
    ]
    message_id: Optional[int] = None
    proposal_id: Optional[int] = None
    loss_reason: str = Field(default="", max_length=255)
    notes: str = Field(default="", max_length=2000)


@app.post("/businesses/{business_id}/outcomes", dependencies=[Depends(require_admin)])
def add_business_outcome(
    business_id: int,
    payload: OutcomeIn,
    db: Session = Depends(get_db),
):
    business = get_business(db, business_id)
    if payload.message_id:
        message = db.get(Message, payload.message_id)
        if not message or message.business_id != business.id:
            raise HTTPException(status_code=422, detail="message does not belong to business")
    if payload.proposal_id:
        proposal = db.get(Proposal, payload.proposal_id)
        if not proposal or proposal.business_id != business.id:
            raise HTTPException(status_code=422, detail="proposal does not belong to business")
    try:
        outcome = capture_outcome(
            db,
            business,
            outcome=payload.outcome,
            actor="human:operator",
            message_id=payload.message_id,
            proposal_id=payload.proposal_id,
            loss_reason=payload.loss_reason,
            notes=payload.notes,
        )
    except (ValueError, InvalidTransition) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    db.commit()
    return {"id": outcome.id, "outcome": outcome.outcome, "state": business.state}


# --- Configuration lifecycle and analytics ------------------------------------


@app.get("/config/{domain}", dependencies=[Depends(require_admin)])
def get_config(domain: str, version: Optional[str] = None):
    try:
        return {
            "active": config_loader.active_version(domain),
            "versions": config_loader.list_versions(domain),
            "config": config_loader.load(domain, version),
        }
    except config_loader.ConfigNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))


class ActivateIn(BaseModel):
    version: str


@app.post("/config/{domain}/activate", dependencies=[Depends(require_admin)])
def activate_config(domain: str, payload: ActivateIn, db: Session = Depends(get_db)):
    """Publish or rollback: point the domain at an existing immutable version."""
    try:
        config_loader.set_active(domain, payload.version)
    except config_loader.ConfigNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    record_event(
        db,
        action="config_activated",
        actor="human:operator",
        entity="config",
        payload={"domain": domain, "version": payload.version},
    )
    db.commit()
    return {"ok": True, "domain": domain, "active": payload.version}


@app.get("/analytics/kpi", dependencies=[Depends(require_admin)])
def analytics(db: Session = Depends(get_db)):
    return kpi_snapshot(db)
