"""ID-only task handlers for discovery, research, preview and rendered QA."""

from __future__ import annotations

from typing import Any

from app.database import SessionLocal
from app.models import Business, SourceConnector, WebsiteBuild
from app.services.enrichment import enrich_business
from app.services.events import transition
from app.services.jobs import get_or_create_job, mark_failed, mark_running, mark_succeeded
from app.services.pipeline import approve_and_generate_preview, discover_enrich_score
from app.services.rendered_qa import validate_rendered_preview
from app.services.research_agent import evidence_excerpts_for_business, research_business
from app.services.scoring import score_business
from app.services.task_queue import (
    CRAWL_RESEARCH_QUEUE,
    DISCOVERY_QUEUE,
    PREVIEW_QUEUE,
    QA_QUEUE,
    register_task,
)
from app.core.state_machine import LeadState

# Celery discovers these registrations when started with
# ``celery -A app.worker.celery_app worker``.  The import remains harmless in
# local/test environments where Celery is intentionally not installed.
celery_app = None


def _fail(db, job, error: Exception) -> None:
    mark_failed(db, job, str(error), stage=job.stage or "failed")
    db.commit()


@register_task("lead.discovery", DISCOVERY_QUEUE)
def discovery_task(*, connector_id: int) -> dict[str, Any]:
    """Run a configured connector. Its configuration remains the source of truth."""
    db = SessionLocal()
    try:
        connector = db.get(SourceConnector, connector_id)
        if not connector:
            raise ValueError(f"connector {connector_id} was not found")
        return discover_enrich_score(db, connector)
    finally:
        db.close()


@register_task("lead.crawl_research", CRAWL_RESEARCH_QUEUE)
def crawl_research_task(*, business_id: int) -> dict[str, Any]:
    """Crawl/enrich and score one existing lead; no raw website data in queue."""
    db = SessionLocal()
    try:
        job, created = get_or_create_job(
            db,
            job_type="crawl_research",
            idempotency_key=f"crawl-research:{business_id}:v1",
            business_id=business_id,
        )
        if not created and job.status == "succeeded":
            return {"job_id": job.id, "reused": True, **(job.result or {})}
        business = db.get(Business, business_id)
        if not business:
            raise ValueError(f"business {business_id} was not found")
        mark_running(db, job, stage="crawl_research")
        try:
            enrichment = enrich_business(db, business)
            research = research_business(
                db,
                business,
                evidence_excerpts_for_business(db, business),
            )
            if LeadState(business.state) == LeadState.NEW:
                transition(db, business, LeadState.VALIDATED, actor="system:worker", reason="enriched")
            qualification = score_business(db, business)
            if LeadState(business.state) == LeadState.VALIDATED:
                target = LeadState.FITQL if qualification.routing != "reject" else LeadState.REJECTED
                transition(db, business, target, actor="system:worker", reason=f"total={qualification.total}")
            result = {
                "business_id": business_id,
                "enrichment": enrichment,
                "research_status": research.status,
                "research_missing": research.missing_fields,
                "score": qualification.total,
                "routing": qualification.routing,
            }
            mark_succeeded(db, job, result=result, stage="qualified")
            db.commit()
            return {"job_id": job.id, "reused": False, **result}
        except Exception as exc:
            _fail(db, job, exc)
            raise
    finally:
        db.close()


@register_task("lead.preview", PREVIEW_QUEUE)
def preview_task(*, business_id: int) -> dict[str, Any]:
    db = SessionLocal()
    try:
        business = db.get(Business, business_id)
        if not business:
            raise ValueError(f"business {business_id} was not found")
        return approve_and_generate_preview(db, business, actor="system:worker")
    finally:
        db.close()


@register_task("lead.qa", QA_QUEUE)
def qa_task(*, build_id: int) -> dict[str, Any]:
    """Re-run rendered QA for one deployed preview and durably record its result."""
    db = SessionLocal()
    try:
        job, created = get_or_create_job(
            db,
            job_type="rendered_qa",
            idempotency_key=f"rendered-qa:{build_id}:v1",
        )
        if not created and job.status == "succeeded":
            return {"job_id": job.id, "reused": True, **(job.result or {})}
        build = db.get(WebsiteBuild, build_id)
        if not build or not build.preview_url:
            raise ValueError(f"deployed preview build {build_id} was not found")
        business = db.get(Business, build.business_id)
        mark_running(db, job, stage="rendered_qa")
        try:
            site_config = build.site_config or {}
            qa_url = site_config.get("_qa_url") or build.preview_url
            phone = (site_config.get("phone") or {}).get("value", "")
            email = (site_config.get("email") or {}).get("value", "")
            result = validate_rendered_preview(
                url=qa_url,
                business_name=business.name,
                build_id=build.id,
                expected_phone=phone,
                expected_email=email,
            )
            passed = all(result.get(key) for key in (
                "page_loaded", "business_identity_ok", "required_sections_ok", "contact_links_ok",
                "form_submission_ok", "responsive_ok", "no_placeholders", "unofficial_disclaimer",
            ))
            build.qa_report = result
            build.pipeline_stage = "validation_passed" if passed else "qa_failed"
            build.status = "deployed" if passed else "failed"
            if passed:
                mark_succeeded(db, job, result={"build_id": build.id, "passed": True, "qa": result}, stage="validation_passed")
            else:
                mark_failed(db, job, "rendered preview QA failed", stage="qa_failed")
            db.commit()
            return {"job_id": job.id, "reused": False, "build_id": build.id, "passed": passed, "qa": result}
        except Exception as exc:
            _fail(db, job, exc)
            raise
    finally:
        db.close()


def _register_celery_tasks() -> None:
    global celery_app
    try:
        from app.services.task_queue import TASKS, get_celery_app, retry_metadata

        celery_app = get_celery_app()
    except (ImportError, RuntimeError):
        return
    options = retry_metadata()
    for name, (_queue, handler) in TASKS.items():
        celery_app.task(
            name=name,
            autoretry_for=(Exception,),
            retry_backoff=options["backoff_seconds"],
            retry_kwargs={"max_retries": options["max_attempts"] - 1},
        )(handler)


_register_celery_tasks()
