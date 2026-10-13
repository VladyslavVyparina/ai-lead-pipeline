"""Bounded AI agent helpers.

Used only for structured outputs (content packs, personalized outreach).
Never rewrites React/templates. Supports OpenAI and OpenRouter's OpenAI-
compatible endpoint, with a deterministic fallback when no provider is set.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.core.schemas import BusinessProfile, ContentContact, ContentCTA, ContentHero, ContentPack
from app.models import AIUsageLedger

logger = logging.getLogger("ai_lead.agent")


# USD per million tokens. Keep this deliberately narrow: an unknown model is
# still metered by tokens but has no invented price estimate until rate-card
# support is explicitly added.
MODEL_RATE_CARD_USD_PER_MILLION = {
    "gpt-4o-mini": {"input": 0.15, "cached_input": 0.075, "output": 0.60},
}


@dataclass(frozen=True)
class AIResponse:
    content: Optional[str]
    model: str
    provider_request_id: str = ""
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    reported_cost_usd: Optional[float] = None
    usage_raw: dict = None  # type: ignore[assignment]
    error: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost_usd(self) -> float:
        if self.reported_cost_usd is not None:
            return round(self.reported_cost_usd, 8)
        rates = MODEL_RATE_CARD_USD_PER_MILLION.get(self.model, {})
        uncached_input_tokens = max(0, self.input_tokens - self.cached_input_tokens)
        return round(
            (
                uncached_input_tokens * rates.get("input", 0.0)
                + self.cached_input_tokens * rates.get("cached_input", 0.0)
                + self.output_tokens * rates.get("output", 0.0)
            )
            / 1_000_000,
            8,
        )


def _usage_from_payload(payload: dict) -> tuple[int, int, int]:
    usage = payload.get("usage") or {}
    prompt_details = usage.get("prompt_tokens_details") or {}
    return (
        int(usage.get("prompt_tokens") or 0),
        int(prompt_details.get("cached_tokens") or 0),
        int(usage.get("completion_tokens") or 0),
    )


def _provider_request() -> tuple[str, str, str, dict[str, str]]:
    """Resolve endpoint/key without exposing provider secrets to callers."""
    requested = settings.ai_provider
    use_openrouter = requested == "openrouter" or (
        requested == "auto" and bool(settings.openrouter_api_key)
    )
    if use_openrouter:
        headers = {"Authorization": f"Bearer {settings.openrouter_api_key}"}
        if settings.openrouter_site_url:
            headers["HTTP-Referer"] = settings.openrouter_site_url
        if settings.openrouter_app_name:
            headers["X-Title"] = settings.openrouter_app_name
        return (
            "openrouter",
            "https://openrouter.ai/api/v1/chat/completions",
            settings.openrouter_api_key,
            headers,
        )
    return (
        "openai",
        "https://api.openai.com/v1/chat/completions",
        settings.openai_api_key,
        {"Authorization": f"Bearer {settings.openai_api_key}"},
    )


def active_model() -> str:
    """Return the provider-specific model selected for this environment."""
    if _provider_request()[0] == "openrouter":
        return settings.openrouter_model
    return settings.chat_model


def record_ai_usage(
    db: Optional[Session],
    response: AIResponse,
    *,
    operation: str,
    business_id: Optional[int] = None,
    prompt_version: str = "v1",
) -> None:
    """Append an auditable usage record without committing the caller's unit of work."""
    if db is None:
        return
    status = "succeeded" if response.content else "fallback"
    db.add(
        AIUsageLedger(
            business_id=business_id,
            operation=operation,
            provider=_provider_request()[0] if response.content else "deterministic",
            model=response.model,
            provider_request_id=response.provider_request_id,
            prompt_version=prompt_version,
            input_tokens=response.input_tokens,
            cached_input_tokens=response.cached_input_tokens,
            output_tokens=response.output_tokens,
            total_tokens=response.total_tokens,
            estimated_cost_usd=response.estimated_cost_usd,
            latency_ms=response.latency_ms,
            status=status,
            error=response.error,
            usage_raw=response.usage_raw or {},
        )
    )


def ai_budget_available(db: Optional[Session], business_id: Optional[int]) -> bool:
    """Return false before a paid call when this lead exhausted its USD budget."""
    if db is None or business_id is None:
        return True
    spent = (
        db.query(AIUsageLedger.estimated_cost_usd)
        .filter(AIUsageLedger.business_id == business_id)
        .all()
    )
    total = sum(float(row[0] or 0.0) for row in spent)
    return total < settings.per_lead_token_budget


def chat_json(messages: list[dict], *, temperature: float = 0.4) -> AIResponse:
    """Call the provider once and retain provider-issued accounting metadata."""
    model = active_model()
    provider, endpoint, api_key, headers = _provider_request()
    if not api_key:
        return AIResponse(
            content=None,
            model=model,
            error=f"{provider.upper()} API key is not configured",
            usage_raw={},
        )
    started = time.monotonic()
    try:
        resp = httpx.post(
            endpoint,
            headers=headers,
            json={
                "model": model,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
                "max_tokens": settings.ai_max_output_tokens,
                "messages": messages,
            },
            timeout=getattr(settings, "ai_request_timeout_seconds", 30.0),
        )
        resp.raise_for_status()
        payload = resp.json()
        input_tokens, cached_input_tokens, output_tokens = _usage_from_payload(payload)
        usage = payload.get("usage") or {}
        reported_cost = usage.get("cost")
        return AIResponse(
            content=(payload.get("choices") or [{}])[0].get("message", {}).get("content"),
            model=payload.get("model") or model,
            provider_request_id=resp.headers.get("x-request-id", "") or payload.get("id", ""),
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            latency_ms=round((time.monotonic() - started) * 1000),
            reported_cost_usd=float(reported_cost) if reported_cost is not None else None,
            usage_raw=usage,
        )
    except Exception as exc:
        logger.warning("LLM call failed, using deterministic fallback: %s", exc)
        return AIResponse(
            content=None,
            model=model,
            latency_ms=round((time.monotonic() - started) * 1000),
            usage_raw={},
            error=str(exc),
        )


def _chat(messages: list[dict], *, temperature: float = 0.4) -> Optional[str]:
    """Backward-compatible content accessor; new callers should use chat_json."""
    return chat_json(messages, temperature=temperature).content


def generate_content_pack(
    profile: BusinessProfile,
    theme: dict,
    *,
    db: Optional[Session] = None,
) -> tuple[ContentPack, float]:
    """Return (ContentPack, cost_units). Structured copy only."""
    services = profile.facts.get("services", {}).get("value") or []
    service_names = []
    if isinstance(services, list):
        for item in services:
            if isinstance(item, dict):
                service_names.append(item.get("name", ""))
            else:
                service_names.append(str(item))
    service_names = [s for s in service_names if s]

    contacts = profile.contacts
    prompt = {
        "business": profile.name,
        "category": profile.category,
        "city": profile.city,
        "services": service_names,
        "gaps": profile.gaps,
        "rules": [
            "Return JSON with keys: hero{headline,subheadline}, services[{name,description}], cta{label,supporting}, seo_title, seo_description",
            "European Portuguese (pt-PT)",
            "Do NOT invent testimonials, certifications, prices, or awards",
            "Do NOT invent contact details",
            "Keep services list aligned to provided names only",
        ],
    }
    use_ai_preview_copy = (
        settings.preview_content_mode == "ai"
        and ai_budget_available(db, profile.business_id)
    )
    response = (
        chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "You write structured landing-page copy for wellness preview sites. "
                        "Output JSON only. Never invent social proof or prices."
                    ),
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ]
        )
        if use_ai_preview_copy
        else AIResponse(
            content=None,
            model="deterministic",
            error=(
                "preview AI copy disabled; deterministic content mode"
                if settings.preview_content_mode != "ai"
                else "per-lead AI budget exhausted"
            ),
            usage_raw={},
        )
    )
    record_ai_usage(
        db,
        response,
        operation="preview_copy",
        business_id=profile.business_id,
        prompt_version="preview-copy-v1",
    )
    raw = response.content
    cost = response.estimated_cost_usd
    data: dict = {}
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}

    hero_data = data.get("hero") or {}
    headline = hero_data.get("headline") or f"{profile.name} — bem-estar em {profile.city.title()}"
    sub = hero_data.get("subheadline") or (
        f"Massagem e cuidado personalizado no {profile.city.title()}. Pré-visualização conceptual."
    )

    mapped_services = []
    ai_services = {s.get("name"): s for s in (data.get("services") or []) if isinstance(s, dict)}
    for name in service_names:
        desc = (ai_services.get(name) or {}).get("description") or ""
        # Pull price only from evidence, never from AI
        price = None
        for item in services if isinstance(services, list) else []:
            if isinstance(item, dict) and item.get("name") == name:
                price = item.get("price")
        mapped_services.append({"name": name, "description": desc, "price": price})

    cta_data = data.get("cta") or {}
    pack = ContentPack(
        hero=ContentHero(headline=headline, subheadline=sub),
        services=mapped_services,
        social_proof=[],  # never invent
        cta=ContentCTA(
            label=cta_data.get("label") or "Pedir marcação",
            supporting=cta_data.get("supporting") or "Resposta rápida · sem compromisso",
        ),
        contact=ContentContact(
            phone=contacts.get("phone", ""),
            email=contacts.get("email", ""),
            whatsapp=contacts.get("whatsapp") or contacts.get("phone", ""),
            address=(profile.facts.get("address") or {}).get("value") or "",
            instagram=contacts.get("instagram", ""),
        ),
        theme=theme,
        seo_title=data.get("seo_title") or f"{profile.name} | {profile.city.title()}",
        seo_description=data.get("seo_description")
        or f"Pré-visualização conceptual para {profile.name} em {profile.city.title()}.",
    )
    return pack, cost


def draft_personalized_outreach(
    profile: BusinessProfile,
    *,
    preview_url: str = "",
    channel: str = "email",
    db: Optional[Session] = None,
) -> tuple[str, dict, float]:
    """Personalized outreach from research gaps — not a generic blast."""
    notes = (profile.facts.get("research_notes") or {}).get("value") or ""
    gaps = profile.gaps or []
    services = profile.facts.get("services", {}).get("value") or []
    service_hint = ""
    if isinstance(services, list) and services:
        first = services[0]
        service_hint = first.get("name") if isinstance(first, dict) else str(first)

    observation = notes or (gaps[0] if gaps else "o site podia converter melhor visitas em marcações")
    research = {
        "observation": observation,
        "gaps": gaps,
        "service_hint": service_hint,
        "has_instagram": bool(profile.contacts.get("instagram")),
        "has_website": bool(profile.audit.get("has_website")),
        "preview_url": preview_url,
    }

    prompt = {
        "business_name": profile.name,
        "city": profile.city,
        "channel": channel,
        "research": research,
        "locale": "pt-PT",
        "rules": [
            "One short email/message body",
            "Reference ONE verified observation from research",
            "One clear benefit, one soft CTA",
            "No fake urgency, no invented claims",
            "If preview_url present, mention it briefly",
            "Return JSON {body: string}",
        ],
    }
    response = (
        chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "You write personalized B2B outreach for local wellness businesses in Portugal. "
                        "Ground every claim in the provided research. JSON only."
                    ),
                },
                {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
            ],
            temperature=0.5,
        )
        if ai_budget_available(db, profile.business_id)
        else AIResponse(
            content=None,
            model=active_model(),
            error="per-lead AI budget exhausted",
            usage_raw={},
        )
    )
    record_ai_usage(
        db,
        response,
        operation="outreach",
        business_id=profile.business_id,
        prompt_version="outreach-v1",
    )
    raw = response.content
    cost = response.estimated_cost_usd
    body = None
    if raw:
        try:
            body = json.loads(raw).get("body")
        except json.JSONDecodeError:
            body = None

    if not body:
        preview_line = f"\n\nPreparei uma pré-visualização: {preview_url}" if preview_url else ""
        ig = " Vi também actividade no Instagram —" if research["has_instagram"] else ""
        body = (
            f"Olá,\n\n"
            f"Reparei que {observation} —{ig} {profile.name} podia captar mais marcações "
            f"com um percurso de reserva mais claro"
            f"{f' (ex.: {service_hint})' if service_hint else ''}.{preview_line}\n\n"
            f"Posso enviar uma auditoria breve? Basta responder a esta mensagem.\n\n"
            f"Com os melhores cumprimentos"
        )
    return body.strip(), research, cost
