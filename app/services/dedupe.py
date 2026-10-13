"""Deduplication and identity resolution (§3.1: normalize → dedupe)."""

from typing import Optional
import re
import unicodedata
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.schemas import SourceRecordIn
from app.models import Business, ContactPoint, SourceRecord

_LEGAL_SUFFIXES = re.compile(r"\b(lda|unipessoal|sa|s\.a\.|ltd|llc)\b\.?", re.IGNORECASE)
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    text = _LEGAL_SUFFIXES.sub("", text.lower())
    text = _NON_ALNUM.sub(" ", text)
    return " ".join(text.split())


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    # Portuguese national numbers are 9 digits; keep the trailing 9 for comparison.
    return digits[-9:] if len(digits) >= 9 else digits


def normalize_domain(url: str) -> str:
    value = (url or "").strip().lower()
    if not value:
        return ""
    if "://" not in value:
        value = f"https://{value}"
    host = (urlparse(value).hostname or "").lower()
    return host.removeprefix("www.")


def dedupe_key(record: SourceRecordIn) -> str:
    return f"{normalize_name(record.business_name)}|{record.city.strip().lower()}"


def normalize_contact(channel: str, value: str) -> str:
    """Canonical form stored in ContactPoint.normalized_value for indexed lookups."""
    value = value.strip()
    if channel == "phone":
        return normalize_phone(value)
    return value.lower()


def find_existing(db: Session, record: SourceRecordIn) -> Optional[Business]:
    """Match provider ID/domain first, then name+city and normalized contacts."""
    if record.provider_id:
        source = (
            db.query(SourceRecord)
            .filter(SourceRecord.provider_id == record.provider_id)
            .order_by(SourceRecord.created_at.desc())
            .first()
        )
        if source and source.business_id:
            return db.get(Business, source.business_id)

    domain = normalize_domain(record.website_url)
    if domain:
        candidates = db.query(Business).filter(Business.website_url != "").all()
        for candidate in candidates:
            if normalize_domain(candidate.website_url) == domain:
                return candidate

    business = db.query(Business).filter(Business.dedupe_key == dedupe_key(record)).first()
    if business:
        return business

    for channel, raw in (("phone", record.phone), ("email", record.email)):
        if not raw:
            continue
        norm = normalize_contact(channel, raw)
        if not norm:
            continue
        cp = (
            db.query(ContactPoint)
            .filter(ContactPoint.channel == channel, ContactPoint.normalized_value == norm)
            .first()
        )
        if cp:
            return db.get(Business, cp.business_id)
    return None
