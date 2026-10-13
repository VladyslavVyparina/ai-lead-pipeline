"""Bounded, respectful crawler for public business websites.

It deliberately stays small: one origin, a small page/byte budget, robots.txt,
and no login or anti-bot bypasses.  JavaScript-only shells are reported for
human review rather than silently treated as an empty business website.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
import ipaddress
import json
import re
import socket
import time
from collections.abc import Callable
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from app.config import settings

USER_AGENT = "AILeadResearchBot/1.0 (+public business website research)"
ROBOTS_USER_AGENT = "AILeadResearchBot"
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
_CACHE_TTL_SECONDS = 600.0
_RESULT_CACHE: dict[tuple[str, int, bool], tuple[float, "CrawlResult"]] = {}
_ROBOTS_CACHE: dict[tuple[str, bool], tuple[float, RobotFileParser]] = {}
PRIORITY_PATH_WORDS = (
    "contact", "contacto", "contato", "service", "servico", "serviÃ§o",
    "treatment", "tratamento", "price", "preco", "preÃ§o", "booking",
    "book", "reserv", "marc", "agend",
)
BOOKING_WORDS = ("booking", "book now", "reserv", "marcaÃ§Ã£o", "marcacao", "agendar")
SERVICE_WORDS = ("service", "serviÃ§o", "servico", "tratamento", "massagem", "terapia")
CONTACT_WORDS = ("contact", "contacto", "contato", "fale connosco", "fale conosco")
PLACEHOLDER_DOMAINS = (".example", ".test", "maps.example")


class CrawlError(RuntimeError):
    pass


@dataclass
class CrawledPage:
    url: str
    status_code: int
    title: str
    text: str
    html: str
    links: list[tuple[str, str]] = field(default_factory=list)
    meta_description: str = ""
    has_viewport: bool = False
    has_form: bool = False
    canonical_url: str = ""
    json_ld: list[dict[str, object]] = field(default_factory=list)
    extraction_status: str = "complete"


@dataclass
class CrawlResult:
    start_url: str
    pages: list[CrawledPage]
    errors: list[str]
    json_ld: list[dict[str, object]] = field(default_factory=list)
    extraction_status: str = "complete"


def _normalized_http_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise CrawlError("website URL is empty")
    if "://" not in value:
        value = f"https://{value}"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise CrawlError("website URL must use http or https")
    if any(parsed.hostname.lower().endswith(suffix) for suffix in PLACEHOLDER_DOMAINS):
        raise CrawlError("placeholder website cannot be enriched")
    return _clean_url(value)


def _clean_url(value: str) -> str:
    parsed = urlparse(value)
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", "", parsed.query, ""))


def _assert_public_host(url: str) -> None:
    hostname = urlparse(url).hostname
    if not hostname:
        raise CrawlError("URL has no hostname")
    try:
        addresses = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise CrawlError(f"website DNS lookup failed: {hostname}") from exc
    for address in addresses:
        raw = address[4][0].split("%", 1)[0]
        ip = ipaddress.ip_address(raw)
        if any((ip.is_private, ip.is_loopback, ip.is_link_local, ip.is_multicast, ip.is_reserved, ip.is_unspecified)):
            raise CrawlError("website resolves to a non-public address")


def _flatten_json_ld(value: object) -> list[dict[str, object]]:
    if isinstance(value, list):
        return [item for child in value for item in _flatten_json_ld(child)]
    if not isinstance(value, dict):
        return []
    graph = value.get("@graph")
    return _flatten_json_ld(graph) if isinstance(graph, list) else [value]


def _parse_page(url: str, status_code: int, html: str) -> CrawledPage:
    soup = BeautifulSoup(html, "html.parser")
    json_ld: list[dict[str, object]] = []
    for script in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        try:
            json_ld.extend(_flatten_json_ld(json.loads(script.get_text(strip=True))))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
    canonical_tag = soup.find("link", attrs={"rel": lambda value: value and "canonical" in value})
    canonical_url = _clean_url(urljoin(url, canonical_tag.get("href", ""))) if canonical_tag and canonical_tag.get("href") else url
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    meta = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    description = (meta.get("content") or "").strip() if meta else ""
    viewport = bool(soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)}))
    links = [(urljoin(url, anchor.get("href", "").strip()), anchor.get_text(" ", strip=True)) for anchor in soup.find_all("a", href=True)]
    script_count = len(soup.find_all("script"))
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
    js_shell = len(text) < 120 and script_count > 0 and not json_ld
    return CrawledPage(
        url=url, status_code=status_code, title=title[:500], text=text[:100_000], html=html,
        links=links, meta_description=description[:2000], has_viewport=viewport,
        has_form=bool(soup.find("form")), canonical_url=canonical_url,
        json_ld=json_ld, extraction_status="js_shell_detected" if js_shell else "complete",
    )


def _request_with_retries(
    client: httpx.Client, url: str, *, retries: int, sleep_fn: Callable[[float], None]
) -> httpx.Response:
    for attempt in range(retries + 1):
        try:
            response = client.get(url)
            if response.status_code not in _RETRYABLE_STATUS_CODES or attempt == retries:
                return response
            response.close()
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt == retries:
                raise
        sleep_fn(min(0.25 * (2**attempt), 1.0))
    raise CrawlError("unreachable retry state")


def _robots_for(
    client: httpx.Client, start: str, *, allow_private_hosts: bool, retries: int,
    sleep_fn: Callable[[float], None], cache_ttl_seconds: float,
) -> RobotFileParser:
    parsed = urlparse(start)
    robots_url = urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
    key = (robots_url, allow_private_hosts)
    cached = _ROBOTS_CACHE.get(key)
    if cached and time.monotonic() - cached[0] < cache_ttl_seconds:
        return cached[1]
    if not allow_private_hosts:
        _assert_public_host(robots_url)
    parser = RobotFileParser(robots_url)
    response = _request_with_retries(client, robots_url, retries=retries, sleep_fn=sleep_fn)
    if response.status_code in {401, 403}:
        parser.disallow_all = True
    elif response.status_code == 404:
        parser.allow_all = True
    elif response.is_success:
        parser.parse(response.text.splitlines())
    else:
        raise CrawlError(f"robots.txt returned HTTP {response.status_code}")
    response.close()
    _ROBOTS_CACHE[key] = (time.monotonic(), parser)
    return parser


def crawl_website(
    start_url: str,
    *,
    max_pages: int | None = None,
    allow_private_hosts: bool = False,
    retry_attempts: int = 2,
    sleep_fn: Callable[[float], None] | None = None,
    cache_ttl_seconds: float = _CACHE_TTL_SECONDS,
    use_cache: bool = True,
    transport: httpx.BaseTransport | None = None,
) -> CrawlResult:
    """Crawl a public same-origin site within strict, deterministic budgets."""
    start = _normalized_http_url(start_url)
    if not allow_private_hosts:
        _assert_public_host(start)
    budget = max(1, min(max_pages or settings.crawl_max_pages, 10))
    cache_key = (start, budget, allow_private_hosts)
    cached = _RESULT_CACHE.get(cache_key)
    if use_cache and cached and time.monotonic() - cached[0] < cache_ttl_seconds:
        return deepcopy(cached[1])
    sleep = sleep_fn or time.sleep
    origin_host = (urlparse(start).hostname or "").lower()
    allowed_hosts = {origin_host}
    pending, visited, content_hashes = [start], set(), set()
    pages: list[CrawledPage] = []
    errors: list[str] = []
    timeout = httpx.Timeout(connect=min(settings.crawl_timeout_seconds, 8.0), read=settings.crawl_timeout_seconds, write=settings.crawl_timeout_seconds, pool=5.0)
    with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}, transport=transport) as client:
        try:
            robots = _robots_for(client, start, allow_private_hosts=allow_private_hosts, retries=retry_attempts, sleep_fn=sleep, cache_ttl_seconds=cache_ttl_seconds)
        except (CrawlError, httpx.HTTPError) as exc:
            raise CrawlError(f"robots.txt check failed: {exc}") from exc
        while pending and len(pages) < budget:
            url = _clean_url(pending.pop(0))
            if url in visited:
                continue
            visited.add(url)
            if not robots.can_fetch(ROBOTS_USER_AGENT, url):
                errors.append(f"{url}: disallowed by robots.txt")
                continue
            try:
                response = _request_with_retries(client, url, retries=retry_attempts, sleep_fn=sleep)
                response.raise_for_status()
                final_url = _clean_url(str(response.url))
                final_host = (urlparse(final_url).hostname or "").lower()
                if not allow_private_hosts:
                    _assert_public_host(final_url)
                if not pages:
                    allowed_hosts.add(final_host)
                elif final_host not in allowed_hosts:
                    errors.append(f"{url}: redirected outside the website origin")
                    response.close()
                    continue
                content_type = response.headers.get("content-type", "").lower()
                if "html" not in content_type:
                    errors.append(f"{url}: unsupported content type {content_type}")
                    response.close()
                    continue
                if len(response.content) > settings.crawl_max_response_bytes:
                    raise CrawlError(f"{url}: response exceeded size limit")
                html = response.content.decode(response.encoding or "utf-8", errors="replace")
                response.close()
                page = _parse_page(final_url, response.status_code, html)
                if (urlparse(page.canonical_url).hostname or "").lower() not in allowed_hosts:
                    page.canonical_url = final_url
                if page.canonical_url in visited and page.canonical_url != final_url:
                    errors.append(f"{final_url}: duplicate canonical page {page.canonical_url}")
                    continue
                visited.add(page.canonical_url)
                digest = sha256(re.sub(r"\s+", " ", page.text).encode("utf-8")).hexdigest()
                if digest in content_hashes:
                    errors.append(f"{final_url}: duplicate page content")
                    continue
                content_hashes.add(digest)
                pages.append(page)
            except (CrawlError, httpx.HTTPError, ValueError) as exc:
                errors.append(f"{url}: {exc}")
                continue
            candidates: list[tuple[int, str]] = []
            for href, label in page.links:
                parsed = urlparse(href)
                if parsed.scheme not in {"http", "https"} or (parsed.hostname or "").lower() not in allowed_hosts:
                    continue
                clean = _clean_url(href)
                if clean in visited:
                    continue
                score = sum(word in f"{parsed.path} {label}".lower() for word in PRIORITY_PATH_WORDS)
                if score:
                    candidates.append((score, clean))
            for _, candidate in sorted(candidates, key=lambda item: item[0], reverse=True):
                if candidate not in pending:
                    pending.append(candidate)
    if not pages:
        raise CrawlError(errors[0] if errors else "website returned no usable HTML pages")
    json_ld = [item for page in pages for item in page.json_ld]
    status = "js_shell_detected" if any(page.extraction_status == "js_shell_detected" for page in pages) else "complete"
    result = CrawlResult(start_url=start, pages=pages, errors=errors, json_ld=json_ld, extraction_status=status)
    if use_cache:
        _RESULT_CACHE[cache_key] = (time.monotonic(), deepcopy(result))
    return result


def evidence_excerpt(text: str, needle: str, *, radius: int = 120) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    index = compact.lower().find(needle.lower())
    return compact[: radius * 2] if index < 0 else compact[max(0, index - radius) : index + len(needle) + radius]
