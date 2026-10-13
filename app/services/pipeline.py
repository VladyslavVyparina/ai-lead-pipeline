"""End-to-end automation agent: connector → enrich → FitQL → shortlist → (human) → preview → outreach draft.

Human gates only:
1. Approve lead for preview generation (after seeing FitQL/reasons)
2. Approve outreach draft before real send
"""

from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from app.adapters.directory_seed import ensure_porto_wellness_connector, run_directory
from app.adapters.google_places import run_google_places
from app.core.state_machine import LeadState
from app.models import (
    Business,
    Evidence,
    PipelineJob,
    Proposal,
    Qualification,
    SourceConnector,
    SourceRun,
    WebsiteBuild,
)
from app.services.enrichment import enrich_business
from app.services.events import record_event, transition
from app.services.jobs import get_or_create_job, mark_failed, mark_running, mark_succeeded
from app.services.lead_review import assert_preview_eligible
from app.services.outreach import draft_personalized_message
from app.services.proposal import build_proposal
from app.services.proposal_pdf import ensure_proposal_pdf
from app.services.research_agent import evidence_excerpts_for_business, research_business
from app.services.scoring import assign_tiers, score_business
from app.services.site_factory import FactValidationError, run_preview_pipeline
from app.services.artifact_storage import persist_artifact


def run_connector(
    db: Session,
    connector: SourceConnector,
    *,
    limit: Optional[int] = None,
) -> SourceRun:
    if connector.adapter == "directory_seed":
        return run_directory(db, connector, limit=limit)
    raise ValueError(f"unsupported automated adapter: {connector.adapter}")


def discover_enrich_score(
    db: Session,
    connector: SourceConnector,
    *,
    limit: Optional[int] = 20,
    top_review: int = 5,
) -> dict:
    """Pipeline 1–3: discovery → enrichment → FitQL → shortlist top N for human review."""
    job, created = get_or_create_job(
        db,
        job_type="vertical_slice_discovery",
        idempotency_key=f"slice:discover:{connector.id}:{connector.cursor or '0'}:{limit}",
        connector_id=connector.id,
        input_payload={"limit": limit, "top_review": top_review},
    )
    if not created and job.status == "succeeded":
        return {"job_id": job.id, "reused": True, **(job.result or {})}

    mark_running(db, job, stage="discovery")
    try:
        run = run_connector(db, connector, limit=limit)
        job.source_run_id = run.id

        # Businesses touched by this run
        from app.models import SourceRecord

        business_ids = [
            r.business_id
            for r in db.query(SourceRecord).filter(SourceRecord.source_run_id == run.id).all()
            if r.business_id
        ]
        business_ids = list(dict.fromkeys(business_ids))

        mark_running(db, job, stage="enrichment")
        enriched = []
        for bid in business_ids:
            business = db.get(Business, bid)
            if not business:
                continue
            summary = enrich_business(db, business)
            # Keep CSV/manual and official-provider discovery on the same
            # evidence-first qualification path.  The research agent degrades
            # safely to a reviewable fallback when no AI provider is enabled.
            research = research_business(
                db,
                business,
                evidence_excerpts_for_business(db, business),
            )
            if LeadState(business.state) == LeadState.NEW:
                transition(db, business, LeadState.VALIDATED, actor="system:pipeline", reason="enriched")
            enriched.append(
                {
                    "business_id": bid,
                    **summary,
                    "research_status": research.status,
                    "research_missing": research.missing_fields,
                }
            )

        mark_running(db, job, stage="qualification")
        scored = []
        for bid in business_ids:
            business = db.get(Business, bid)
            if not business:
                continue
            q = score_business(db, business)
            if LeadState(business.state) == LeadState.VALIDATED:
                target = LeadState.FITQL if q.routing != "reject" else LeadState.REJECTED
                transition(
                    db,
                    business,
                    target,
                    actor="system:pipeline",
                    reason=f"total={q.total}; reasons={', '.join(q.reasons or [])}",
                )
            scored.append(
                {
                    "business_id": bid,
                    "total": q.total,
                    "routing": q.routing,
                    "breakdown": q.breakdown,
                    "reasons": q.reasons,
                }
            )

        tiers = assign_tiers(db)
        # Shortlist top N from THIS run only (ignore already-advanced leads in a dirty DB)
        run_set = set(business_ids)
        scored_by_total = sorted(
            (
                s
                for s in scored
                if s["business_id"] in run_set and s["routing"] == "priority_review"
            ),
            key=lambda s: s["total"],
            reverse=True,
        )
        # Prefer Tier A ordering when available
        tier_a_order = [bid for bid in tiers.get("A", []) if bid in run_set]
        ordered_ids: list[int] = []
        for bid in tier_a_order + [s["business_id"] for s in scored_by_total]:
            if bid not in ordered_ids:
                ordered_ids.append(bid)

        review_queue: list[int] = []
        for bid in ordered_ids:
            if len(review_queue) >= top_review:
                break
            business = db.get(Business, bid)
            if not business:
                continue
            state = LeadState(business.state)
            if state == LeadState.FITQL:
                transition(
                    db,
                    business,
                    LeadState.SHORTLISTED,
                    actor="system:pipeline",
                    reason=f"top {top_review} for preview approval",
                )
                review_queue.append(bid)
            elif state == LeadState.SHORTLISTED:
                review_queue.append(bid)

        result = {
            "run_id": run.id,
            "ingested": run.records_ingested,
            "skipped": run.records_skipped,
            "enriched": len(enriched),
            "research": [
                {
                    "business_id": item["business_id"],
                    "status": item["research_status"],
                    "missing": item["research_missing"],
                }
                for item in enriched
            ],
            "scored": len(scored),
            "tiers": {k: len(v) for k, v in tiers.items()},
            "review_queue": review_queue,
            "scores": scored,
        }
        mark_succeeded(db, job, result=result, stage="awaiting_preview_approval")
        db.commit()
        return {"job_id": job.id, "reused": False, **result}
    except Exception as exc:
        mark_failed(db, job, str(exc), stage=job.stage)
        db.commit()
        raise


def approve_and_generate_preview(db: Session, business: Business, *, actor: str = "human:operator") -> dict:
    """Human gate -> one idempotent preview/proposal/outreach asset package."""
    job, created = get_or_create_job(
        db,
        job_type="asset_package",
        idempotency_key=f"asset-package:{business.id}:v1",
        business_id=business.id,
    )
    if not created:
        if job.status == "succeeded":
            return {"job_id": job.id, "reused": True, **(job.result or {})}
        if job.status == "running":
            return {
                "job_id": job.id,
                "reused": True,
                "status": "running",
                "pipeline_stage": job.stage,
            }

    state = LeadState(business.state)
    if state == LeadState.FITQL:
        transition(
            db,
            business,
            LeadState.SHORTLISTED,
            actor=actor,
            reason="approved for preview from fitql",
        )
        state = LeadState.SHORTLISTED
    if state not in {LeadState.SHORTLISTED, LeadState.REVISION}:
        raise ValueError(f"business must be shortlisted for preview approval, got {business.state}")

    channel_plan = assert_preview_eligible(db, business)
    mark_running(db, job, stage="approved")
    record_event(
        db,
        action="preview_approved",
        actor=actor,
        business_id=business.id,
        reason="human approved preview generation",
    )

    try:
        build = run_preview_pipeline(db, business, actor="system:pipeline")
        if build.status == "deployed" and LeadState(business.state) in {LeadState.SHORTLISTED, LeadState.REVISION}:
            transition(
                db,
                business,
                LeadState.PREVIEW_READY,
                actor="system:pipeline",
                reason=build.preview_url,
            )

        message = None
        proposal = None
        proposal_pdf = None
        if build.status == "deployed":
            mark_running(db, job, stage="proposal")
            proposal = (
                db.query(Proposal)
                .filter(
                    Proposal.business_id == business.id,
                    Proposal.offer_package == "local_pro",
                )
                .order_by(Proposal.created_at.desc())
                .first()
            )
            if not proposal:
                proposal = build_proposal(
                    db,
                    business,
                    offer_package="local_pro",
                    actor="system:pipeline",
                )
                persist_artifact(
                    db,
                    business=business,
                    kind="proposal_json",
                    payload=json.dumps(
                        proposal.content, ensure_ascii=False, sort_keys=True, default=str
                    ).encode("utf-8"),
                    filename=f"proposal-{proposal.id}.json",
                    content_type="application/json",
                )
            proposal_pdf = ensure_proposal_pdf(db, business=business, proposal=proposal)
            mark_running(db, job, stage="outreach_draft")
            message = draft_personalized_message(
                db,
                business,
                channel=channel_plan["channel"],
                touch_number=1,
                preview_url=build.preview_url,
            )

        evidence_used = [
            {
                "id": item.id,
                "fact": item.fact_key,
                "source_url": item.source_url,
                "excerpt": item.evidence_excerpt,
                "confidence": item.confidence,
                "status": item.status,
            }
            for item in db.query(Evidence)
            .filter(Evidence.business_id == business.id, Evidence.status != "missing")
            .order_by(Evidence.id.asc())
            .all()
        ]
        result = {
            "build_id": build.id,
            "status": build.status,
            "pipeline_stage": build.pipeline_stage,
            "preview_url": build.preview_url,
            "qa": build.qa_report,
            "screenshots": {
                "desktop": (build.qa_report or {}).get("screenshot_desktop", ""),
                "mobile": (build.qa_report or {}).get("screenshot_mobile", ""),
            },
            "proposal": (
                {
                    "id": proposal.id,
                    "offer_package": proposal.offer_package,
                    "pricebook_version": proposal.pricebook_version,
                    "content": proposal.content,
                    "pdf_artifact_id": proposal_pdf.id if proposal_pdf else None,
                    "pdf_download_path": f"/private-artifacts/{proposal_pdf.id}/download" if proposal_pdf else None,
                }
                if proposal
                else None
            ),
            "recommended_channel": channel_plan["channel"],
            "recipient": channel_plan["recipient"],
            "channel_reason": channel_plan["reason"],
            "message_id": message.id if message else None,
            "draft": message.body if message else "",
            "evidence_used": evidence_used,
            "cost_units": build.cost_units,
        }
        if build.status == "deployed":
            mark_succeeded(db, job, result=result, stage="preview_ready", cost_units=build.cost_units or 0)
        else:
            mark_failed(db, job, "preview QA failed", stage=build.pipeline_stage)
        db.commit()
        return {"job_id": job.id, "reused": False, **result}
    except FactValidationError as exc:
        mark_failed(db, job, str(exc), stage="content_generated")
        db.commit()
        raise
    except Exception as exc:
        mark_failed(db, job, str(exc), stage=job.stage)
        db.commit()
        raise


def run_porto_wellness_vertical_slice(db: Session, *, limit: int = 20, top_review: int = 5) -> dict:
    """One-button pilot: ensure connector, run discovery→score, return review queue."""
    connector = ensure_porto_wellness_connector(db)
    return discover_enrich_score(db, connector, limit=limit, top_review=top_review)


def discover_places_enrich_score(
    db: Session,
    connector: SourceConnector,
    *,
    query: str,
    city: str,
    category: str,
    limit: int = 20,
    top_review: int = 5,
) -> dict:
    """Official Places discovery -> live enrichment -> FitQL -> review queue."""
    normalized_query = " ".join(query.strip().lower().split())
    job, created = get_or_create_job(
        db,
        job_type="google_places_vertical_slice",
        idempotency_key=(
            f"places:{connector.id}:{normalized_query}:{city.lower()}:{category}:{limit}"
        ),
        connector_id=connector.id,
        input_payload={
            "query": query,
            "city": city,
            "category": category,
            "limit": limit,
            "top_review": top_review,
        },
    )
    if not created and job.status == "succeeded":
        return {"job_id": job.id, "reused": True, **(job.result or {})}

    mark_running(db, job, stage="discovery")
    try:
        run = run_google_places(
            db,
            connector,
            query=query,
            city=city,
            category=category,
            limit=limit,
        )
        job.source_run_id = run.id
        from app.models import SourceRecord

        business_ids = list(
            dict.fromkeys(
                record.business_id
                for record in db.query(SourceRecord)
                .filter(SourceRecord.source_run_id == run.id)
                .all()
                if record.business_id
            )
        )

        mark_running(db, job, stage="enrichment")
        summaries = []
        for business_id in business_ids:
            business = db.get(Business, business_id)
            if not business:
                continue
            summary = enrich_business(db, business)
            research = research_business(
                db,
                business,
                evidence_excerpts_for_business(db, business),
            )
            if LeadState(business.state) == LeadState.NEW:
                transition(
                    db,
                    business,
                    LeadState.VALIDATED,
                    actor="system:pipeline",
                    reason="live website enrichment completed",
                )
            summaries.append(
                {
                    "business_id": business_id,
                    **summary,
                    "research_status": research.status,
                    "research_missing": research.missing_fields,
                }
            )

        mark_running(db, job, stage="qualification")
        scores = []
        for business_id in business_ids:
            business = db.get(Business, business_id)
            if not business:
                continue
            qualification = score_business(db, business)
            if LeadState(business.state) == LeadState.VALIDATED:
                target = (
                    LeadState.FITQL
                    if qualification.routing != "reject"
                    else LeadState.REJECTED
                )
                transition(
                    db,
                    business,
                    target,
                    actor="system:pipeline",
                    reason=f"total={qualification.total}",
                )
            scores.append(
                {
                    "business_id": business_id,
                    "total": qualification.total,
                    "routing": qualification.routing,
                    "reasons": qualification.reasons,
                    "breakdown": qualification.breakdown,
                }
            )

        assign_tiers(db)
        review_queue: list[int] = []
        ordered = sorted(
            (item for item in scores if item["routing"] == "priority_review"),
            key=lambda item: item["total"],
            reverse=True,
        )
        for item in ordered:
            if len(review_queue) >= top_review:
                break
            business = db.get(Business, item["business_id"])
            if business and LeadState(business.state) == LeadState.FITQL:
                transition(
                    db,
                    business,
                    LeadState.SHORTLISTED,
                    actor="system:pipeline",
                    reason=f"top {top_review} from live Places run",
                )
                review_queue.append(business.id)

        result = {
            "run_id": run.id,
            "ingested": run.records_ingested,
            "skipped": run.records_skipped,
            "enriched": len(summaries),
            "scored": len(scores),
            "review_queue": review_queue,
            "scores": scores,
        }
        mark_succeeded(db, job, result=result, stage="awaiting_preview_approval")
        db.commit()
        return {"job_id": job.id, "reused": False, **result}
    except Exception as exc:
        mark_failed(db, job, str(exc), stage=job.stage)
        db.commit()
        raise


def list_jobs(db: Session, *, limit: int = 50) -> list[PipelineJob]:
    return db.query(PipelineJob).order_by(PipelineJob.id.desc()).limit(limit).all()
