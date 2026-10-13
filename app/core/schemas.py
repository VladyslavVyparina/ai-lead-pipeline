"""Pydantic contracts: source records, inbound leads, SiteConfig (§2.2, §5.2)."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


class Provenance(BaseModel):
    source: str
    url: str = ""
    captured_at: datetime = Field(default_factory=datetime.utcnow)
    permitted_use: str


class SourceRecordIn(BaseModel):
    """Normalized output every source adapter must emit."""

    business_name: str
    category: str
    city: str
    address: str = ""
    website_url: str = ""
    profile_url: str = ""
    email: str = ""
    phone: str = ""
    instagram: str = ""
    provider_id: str = ""
    rating: Optional[float] = Field(default=None, ge=0.0, le=5.0)
    review_count: Optional[int] = Field(default=None, ge=0)
    captured_at: datetime = Field(default_factory=datetime.utcnow)
    extra: dict = Field(default_factory=dict)
    provenance: Provenance


class InboundLeadIn(BaseModel):
    """Generic inbound webhook/manual-import contract (P0). Meta Lead Ads maps to this in P1."""

    campaign: str
    business_name: str
    contact_name: str = ""
    email: str = ""
    phone: str = ""
    city: str = ""
    category: str = "unknown"
    message: str = ""
    consent_channel: Literal["email", "phone", "whatsapp", "form"] = "email"
    consent_basis: Literal["opt_in", "inbound_request"] = "inbound_request"
    source: str = "inbound_webhook"
    idempotency_key: str


# --- SiteConfig (§5.2) --------------------------------------------------------


class SourcedFact(BaseModel):
    """Each fact carries source and confidence; low confidence routes to review."""

    value: str
    source_url: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class ServiceItem(BaseModel):
    name: SourcedFact
    price: Optional[SourcedFact] = None  # omitted when unverified, never invented
    description: str = ""


class SiteConfig(BaseModel):
    business_name: SourcedFact
    category: str
    city: str
    address: Optional[SourcedFact] = None
    hours: Optional[SourcedFact] = None
    phone: Optional[SourcedFact] = None
    email: Optional[SourcedFact] = None
    whatsapp: Optional[SourcedFact] = None
    socials: dict[str, str] = Field(default_factory=dict)
    services: list[ServiceItem] = Field(default_factory=list)
    description: Optional[SourcedFact] = None
    team: list[SourcedFact] = Field(default_factory=list)
    logo_url: str = ""
    hero_image_url: str = ""
    primary_color: str = "#1a1a2e"
    accent_color: str = ""
    seo_title: str = ""
    seo_description: str = ""
    booking_url: str = ""  # verified existing booking link may be used in preview
    form_endpoint: str = ""  # preview: controlled operator/test endpoint
    mode: Literal["preview", "production"] = "preview"
    noindex: bool = True  # previews are unlisted and labelled

    def low_confidence_facts(self, threshold: float = 0.7) -> list[str]:
        flagged: list[str] = []
        for key in ("business_name", "address", "hours", "phone", "email", "description"):
            fact = getattr(self, key)
            if fact is not None and fact.confidence < threshold:
                flagged.append(key)
        for item in self.services:
            if item.name.confidence < threshold:
                flagged.append(f"service:{item.name.value}")
            if item.price is not None and item.price.confidence < threshold:
                flagged.append(f"price:{item.name.value}")
        return flagged


class QAResult(BaseModel):
    build_ok: bool
    links_ok: bool
    form_ok: bool
    booking_ok: bool
    responsive_ok: bool
    no_placeholders: bool = True
    brand_contacts_ok: bool = True
    unofficial_disclaimer: bool = True
    no_invented_social_proof: bool = True
    page_loaded: bool = True
    business_identity_ok: bool = True
    required_sections_ok: bool = True
    contact_links_ok: bool = True
    form_submission_ok: bool = True
    screenshot_desktop: str = ""
    screenshot_mobile: str = ""
    notes: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(
            [
                self.build_ok,
                self.links_ok,
                self.form_ok,
                self.booking_ok,
                self.responsive_ok,
                self.no_placeholders,
                self.brand_contacts_ok,
                self.unofficial_disclaimer,
                self.no_invented_social_proof,
                self.page_loaded,
                self.business_identity_ok,
                self.required_sections_ok,
                self.contact_links_ok,
                self.form_submission_ok,
            ]
        )


# --- Template-driven content (AI emits this, never React) ---------------------


class ContentHero(BaseModel):
    headline: str
    subheadline: str = ""


class ContentCTA(BaseModel):
    label: str = "Pedir marcação"
    supporting: str = ""


class ContentContact(BaseModel):
    phone: str = ""
    email: str = ""
    whatsapp: str = ""
    address: str = ""
    instagram: str = ""


class ContentPack(BaseModel):
    """Structured site copy mapped onto a niche template. No code generation."""

    hero: ContentHero
    services: list[dict] = Field(default_factory=list)
    social_proof: list[str] = Field(default_factory=list)  # only verified; empty if none
    cta: ContentCTA = Field(default_factory=ContentCTA)
    contact: ContentContact = Field(default_factory=ContentContact)
    theme: dict = Field(default_factory=dict)
    disclaimer: str = "Pré-visualização conceptual não oficial — não representa o negócio."
    seo_title: str = ""
    seo_description: str = ""


class BusinessProfile(BaseModel):
    """Normalized profile assembled from evidence before content mapping."""

    business_id: int
    name: str
    category: str
    city: str
    website_url: str = ""
    facts: dict = Field(default_factory=dict)  # fact_key -> {value, status, confidence, source_url}
    contacts: dict = Field(default_factory=dict)
    audit: dict = Field(default_factory=dict)
    gaps: list[str] = Field(default_factory=list)


# --- Evidence-only research agent -------------------------------------------


class CleanEvidenceExcerpt(BaseModel):
    """A short, already-cleaned public text fragment supplied to research.

    This is deliberately not an HTML/page contract. Callers must extract text
    before invoking an LLM so navigation markup, scripts and raw page bodies
    never enter the prompt.
    """

    source_url: str
    excerpt: str = Field(min_length=1, max_length=4000)
    captured_at: datetime = Field(default_factory=datetime.utcnow)
    extraction_method: str = "website_crawl"

    def model_post_init(self, __context) -> None:
        lowered = self.excerpt.lower()
        if "<html" in lowered or "<script" in lowered or "</body" in lowered:
            raise ValueError("Research input must be cleaned text, not raw HTML")


class ResearchFact(BaseModel):
    """A claim whose evidence can be displayed and independently checked."""

    value: str = Field(min_length=1, max_length=1000)
    source_url: str = Field(min_length=1, max_length=2048)
    evidence_excerpt: str = Field(min_length=1, max_length=1200)
    confidence: float = Field(ge=0.0, le=1.0)
    extraction_method: str = Field(min_length=1, max_length=64)
    captured_at: datetime


class ResearchContact(ResearchFact):
    channel: Literal["email", "phone", "whatsapp", "form", "instagram", "facebook", "other"]


class ResearchService(ResearchFact):
    description: str = ""


class ResearchGap(ResearchFact):
    severity: Literal["low", "medium", "high"] = "low"


class ResearchConflict(BaseModel):
    field: str = Field(min_length=1, max_length=128)
    facts: list[ResearchFact] = Field(min_length=2, max_length=8)
    reason: str = "Conflicting public evidence"


class ResearchOutput(BaseModel):
    """Validated research output. Omitted is preferable to an unsupported claim."""

    identity: Optional[ResearchFact] = None
    contacts: list[ResearchContact] = Field(default_factory=list)
    services: list[ResearchService] = Field(default_factory=list)
    prices: list[ResearchFact] = Field(default_factory=list)
    booking_paths: list[ResearchFact] = Field(default_factory=list)
    website_gaps: list[ResearchGap] = Field(default_factory=list)
    conflicts: list[ResearchConflict] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    status: Literal["complete", "needs_review", "fallback"] = "complete"
