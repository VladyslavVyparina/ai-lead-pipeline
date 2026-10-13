"""Lead dossier, exclusion warnings, and deterministic channel selection."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Business, ContactPoint, Evidence, SourceRecord, Suppression


class LeadEligibilityError(ValueError):
    def __init__(self, warnings: list[str]):
        self.warnings = warnings
        super().__init__("lead is not eligible for preview: " + "; ".join(warnings))


def recommend_channel(db: Session, business: Business) -> dict:
    contacts = (
        db.query(ContactPoint)
        .filter(
            ContactPoint.business_id == business.id,
            ContactPoint.is_business_contact.is_(True),
        )
        .order_by(ContactPoint.verified.desc(), ContactPoint.id.asc())
        .all()
    )
    verified = [contact for contact in contacts if contact.verified]
    for channel in ("email",):
        match = next((contact for contact in verified if contact.channel == channel), None)
        if match:
            return {
                "channel": channel,
                "recipient": match.value,
                "reason": "Verified public business email found on the official website/provider source.",
                "contact_id": match.id,
            }

    form = (
        db.query(Evidence)
        .filter(
            Evidence.business_id == business.id,
            Evidence.fact_key == "contact_form_url",
            Evidence.status == "confirmed",
            Evidence.confidence >= 0.8,
        )
        .order_by(Evidence.captured_at.desc())
        .first()
    )
    if form:
        return {
            "channel": "contact_form",
            "recipient": str(form.fact_value),
            "reason": "Verified public contact form found on the official website.",
            "evidence_id": form.id,
        }

    instagram = next(
        (contact for contact in verified if contact.channel == "instagram"), None
    )
    if instagram:
        return {
            "channel": "instagram",
            "recipient": instagram.value,
            "reason": "Verified Instagram link found on the official business website.",
            "contact_id": instagram.id,
        }

    phone = next((contact for contact in verified if contact.channel == "phone"), None)
    if phone:
        return {
            "channel": "phone_call",
            "recipient": phone.value,
            "reason": "Only a verified public business phone is available; prepare a manual call.",
            "contact_id": phone.id,
        }

    return {
        "channel": "",
        "recipient": "",
        "reason": "No verified public business contact path is available.",
    }


def exclusion_warnings(db: Session, business: Business) -> list[str]:
    warnings: list[str] = []
    if db.query(Suppression).filter(Suppression.business_id == business.id).first():
        warnings.append("Business is suppressed.")

    latest_source = (
        db.query(SourceRecord)
        .filter(SourceRecord.business_id == business.id)
        .order_by(SourceRecord.created_at.desc())
        .first()
    )
    if latest_source:
        status = ((latest_source.raw or {}).get("extra") or {}).get("business_status", "")
        if status == "CLOSED_PERMANENTLY":
            warnings.append("Provider reports the business as permanently closed.")

    channel = recommend_channel(db, business)
    if not channel["channel"]:
        warnings.append("No usable verified public contact path.")

    conflicting = (
        db.query(Evidence)
        .filter(
            Evidence.business_id == business.id,
            Evidence.status.in_(["conflicting", "stale"]),
        )
        .count()
    )
    if conflicting:
        warnings.append(f"{conflicting} evidence item(s) are conflicting or stale.")
    low_confidence = (
        db.query(Evidence)
        .filter(
            Evidence.business_id == business.id,
            Evidence.status != "missing",
            Evidence.confidence < 0.7,
        )
        .count()
    )
    if low_confidence:
        warnings.append(f"{low_confidence} evidence item(s) require confidence review.")
    return warnings


def assert_preview_eligible(db: Session, business: Business) -> dict:
    channel = recommend_channel(db, business)
    fatal = []
    warnings = exclusion_warnings(db, business)
    if not channel["channel"]:
        fatal.append("No usable verified public contact path.")
    if any("suppressed" in warning.lower() for warning in warnings):
        fatal.append("Business is suppressed.")
    if any("permanently closed" in warning.lower() for warning in warnings):
        fatal.append("Business is permanently closed.")
    if fatal:
        raise LeadEligibilityError(list(dict.fromkeys(fatal)))
    return channel
