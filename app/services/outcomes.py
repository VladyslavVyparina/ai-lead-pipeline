"""Commercial outcome capture and safe lifecycle advancement."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.state_machine import LeadState
from app.models import Business, LeadOutcome, Opportunity, Proposal
from app.services.events import record_event, transition

OUTCOMES = {
    "replied",
    "positive_reply",
    "meeting_booked",
    "proposal_sent",
    "won",
    "lost",
}


def _advance(db: Session, business: Business, target: LeadState, actor: str, reason: str) -> None:
    if LeadState(business.state) == target:
        return
    transition(db, business, target, actor=actor, reason=reason)


def _apply_outcome_state(
    db: Session,
    business: Business,
    outcome: str,
    *,
    actor: str,
) -> None:
    state = LeadState(business.state)
    reason = f"commercial outcome: {outcome}"
    if outcome in {"replied", "positive_reply"}:
        if state in {LeadState.CONTACTED, LeadState.FOLLOW_UP}:
            _advance(db, business, LeadState.ENGAGED, actor, reason)
    elif outcome == "meeting_booked":
        if state == LeadState.CONTACTED:
            _advance(db, business, LeadState.ENGAGED, actor, reason)
            state = LeadState.ENGAGED
        if state == LeadState.FOLLOW_UP:
            _advance(db, business, LeadState.ENGAGED, actor, reason)
            state = LeadState.ENGAGED
        if state == LeadState.ENGAGED:
            _advance(db, business, LeadState.SQL, actor, reason)
            state = LeadState.SQL
        if state == LeadState.SQL:
            _advance(db, business, LeadState.MEETING, actor, reason)
    elif outcome == "won":
        if state in {LeadState.SQL, LeadState.MEETING}:
            _advance(db, business, LeadState.WON, actor, reason)
    elif outcome == "lost":
        if state == LeadState.CONTACTED:
            _advance(db, business, LeadState.FOLLOW_UP, actor, reason)
            state = LeadState.FOLLOW_UP
        if state in {
            LeadState.FOLLOW_UP,
            LeadState.ENGAGED,
            LeadState.SQL,
            LeadState.MEETING,
        }:
            _advance(db, business, LeadState.LOST, actor, reason)


def capture_outcome(
    db: Session,
    business: Business,
    *,
    outcome: str,
    actor: str,
    message_id: int | None = None,
    proposal_id: int | None = None,
    loss_reason: str = "",
    notes: str = "",
) -> LeadOutcome:
    if outcome not in OUTCOMES:
        raise ValueError(f"unsupported outcome: {outcome}")
    if outcome == "lost" and not loss_reason.strip():
        raise ValueError("loss_reason is required for a lost outcome")
    record = LeadOutcome(
        business_id=business.id,
        outcome=outcome,
        message_id=message_id,
        proposal_id=proposal_id,
        loss_reason=loss_reason.strip(),
        notes=notes.strip(),
        actor=actor,
    )
    db.add(record)
    db.flush()
    if outcome == "proposal_sent" and proposal_id:
        proposal = db.get(Proposal, proposal_id)
        if proposal:
            proposal.status = "sent"
            db.add(proposal)

    opportunity_stage = {
        "positive_reply": "qualified_conversation",
        "meeting_booked": "meeting",
        "proposal_sent": "proposal",
        "won": "won",
        "lost": "lost",
    }.get(outcome)
    if opportunity_stage:
        opportunity = (
            db.query(Opportunity)
            .filter(Opportunity.business_id == business.id)
            .order_by(Opportunity.created_at.desc())
            .first()
        )
        if not opportunity:
            opportunity = Opportunity(business_id=business.id)
        opportunity.stage = opportunity_stage
        if notes:
            opportunity.notes = notes.strip()
        db.add(opportunity)

    _apply_outcome_state(db, business, outcome, actor=actor)
    record_event(
        db,
        action="commercial_outcome",
        actor=actor,
        business_id=business.id,
        entity="lead_outcome",
        entity_id=record.id,
        reason=loss_reason,
        payload={
            "outcome": outcome,
            "message_id": message_id,
            "proposal_id": proposal_id,
            "notes": notes,
        },
    )
    return record
