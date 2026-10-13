"""Brand-signal extraction: logo, colors and hero imagery from a lead's own site.

Evidence-grounded like the rest of enrichment: every signal is returned with a
confidence and is derived only from the page the lead published. Nothing is
invented — absent signals are simply omitted. Pure/deterministic and
dependency-light (BeautifulSoup + regex, already used by the crawler), so it
runs inside ``_enrich_live_website`` on the HTML that was already fetched.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

_HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
_RGB_RE = re.compile(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})", re.I)
# CSS custom properties that typically hold the brand color.
_BRAND_VAR_RE = re.compile(
    r"--[\w-]*(?:primary|brand|accent|main|theme|secondary)[\w-]*\s*:\s*([^;}\n]+)",
    re.I,
)
_LOGO_HINT = re.compile(r"logo|brand", re.I)
_HERO_HINT = re.compile(r"hero|banner|cover|masthead|jumbotron", re.I)


def _clean_hex(value: str) -> Optional[str]:
    value = value.strip().lower()
    if not value.startswith("#"):
        return None
    value = value[1:]
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6 or any(c not in "0123456789abcdef" for c in value):
        return None
    return f"#{value}"


def _rgb_to_hex(r: int, g: int, b: int) -> Optional[str]:
    if any(not 0 <= c <= 255 for c in (r, g, b)):
        return None
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


def _normalize_color(token: str) -> Optional[str]:
    token = (token or "").strip()
    hex_match = _HEX_RE.search(token)
    if hex_match:
        return _clean_hex(hex_match.group(0))
    rgb_match = _RGB_RE.search(token)
    if rgb_match:
        return _rgb_to_hex(*(int(g) for g in rgb_match.groups()))
    return None


def _hsl(hex_color: str) -> tuple[float, float, float]:
    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    mx, mn = max(r, g, b), min(r, g, b)
    light = (mx + mn) / 2
    if mx == mn:
        return 0.0, 0.0, light
    delta = mx - mn
    sat = delta / (2 - mx - mn) if light > 0.5 else delta / (mx + mn)
    if mx == r:
        hue = (g - b) / delta + (6 if g < b else 0)
    elif mx == g:
        hue = (b - r) / delta + 2
    else:
        hue = (r - g) / delta + 4
    return hue * 60, sat, light


def _is_vibrant(hex_color: str) -> bool:
    """Filter out near-white/black/gray so we keep an actual brand hue."""
    _, sat, light = _hsl(hex_color)
    return sat >= 0.15 and 0.12 <= light <= 0.9


def _find_logo(soup: BeautifulSoup, base_url: str) -> tuple[str, float]:
    # 1) Open Graph / explicit logo meta
    for prop in ("og:logo", "og:image:logo"):
        tag = soup.find("meta", attrs={"property": prop})
        if tag and tag.get("content"):
            return urljoin(base_url, tag["content"].strip()), 0.9

    # 2) An <img> that looks like a logo, preferring header/nav context
    candidates = soup.find_all("img")
    header = soup.find(["header", "nav"])
    ordered = (header.find_all("img") if header else []) + candidates
    for img in ordered:
        haystack = " ".join(
            str(img.get(attr, "")) for attr in ("src", "alt", "class", "id")
        )
        src = img.get("src") or img.get("data-src") or ""
        if src and _LOGO_HINT.search(haystack):
            return urljoin(base_url, src.strip()), 0.9

    # 3) apple-touch-icon / icon as a lower-confidence fallback. Prefer
    # apple-touch-icon (usually the highest-res brand mark).
    icons: dict[str, str] = {}
    for link in soup.find_all("link", href=True):
        rel = link.get("rel")
        rel_text = " ".join(rel).lower() if isinstance(rel, list) else str(rel or "").lower()
        if "icon" in rel_text:
            icons.setdefault(rel_text, link["href"].strip())
    for key in list(icons):
        if "apple-touch-icon" in key:
            return urljoin(base_url, icons[key]), 0.6
    if icons:
        return urljoin(base_url, next(iter(icons.values()))), 0.6
    return "", 0.0


def _find_hero_image(soup: BeautifulSoup, base_url: str) -> str:
    og = soup.find("meta", attrs={"property": "og:image"})
    if og and og.get("content"):
        return urljoin(base_url, og["content"].strip())
    # A large/hero-flagged image near the top of the page
    for img in soup.find_all("img"):
        hint = " ".join(str(img.get(attr, "")) for attr in ("class", "id", "alt", "src"))
        if _HERO_HINT.search(hint) and (img.get("src") or img.get("data-src")):
            return urljoin(base_url, (img.get("src") or img.get("data-src")).strip())
    return ""


def _collect_colors(soup: BeautifulSoup) -> list[str]:
    """Ordered vibrant colors: brand CSS vars first, then most-frequent hues."""
    brand: list[str] = []
    frequency: Counter[str] = Counter()
    for style in soup.find_all("style"):
        css = style.get_text() or ""
        for raw in _BRAND_VAR_RE.findall(css):
            color = _normalize_color(raw)
            if color and _is_vibrant(color) and color not in brand:
                brand.append(color)
        for match in _HEX_RE.findall(css):
            color = _clean_hex(match)
            if color and _is_vibrant(color):
                frequency[color] += 1
    # Inline style attributes are noisy; only mine explicit brand vars there.
    for node in soup.find_all(style=True):
        for raw in _BRAND_VAR_RE.findall(node.get("style", "")):
            color = _normalize_color(raw)
            if color and _is_vibrant(color) and color not in brand:
                brand.append(color)
    ordered = list(brand)
    for color, _count in frequency.most_common():
        if color not in ordered:
            ordered.append(color)
    return ordered


def _pick_accent(colors: list[str], primary: Optional[str]) -> str:
    if not primary:
        return colors[1] if len(colors) > 1 else ""
    p_hue = _hsl(primary)[0]
    for color in colors:
        if color == primary:
            continue
        if abs(_hsl(color)[0] - p_hue) > 40:  # visibly different hue
            return color
    return ""


def extract_brand_signals(html: str, base_url: str) -> dict:
    """Return brand signals derived from the lead's homepage HTML.

    Keys (all optional): ``logo_url``, ``logo_confidence``, ``theme_color``,
    ``colors`` (ordered), ``primary_color``, ``accent_color``,
    ``hero_image_url``. Never raises — returns {} on any parse failure.
    """
    try:
        soup = BeautifulSoup(html or "", "html.parser")
    except Exception:
        return {}

    signals: dict = {}

    logo_url, logo_conf = _find_logo(soup, base_url)
    if logo_url:
        signals["logo_url"] = logo_url
        signals["logo_confidence"] = logo_conf

    colors = _collect_colors(soup)
    theme_tag = soup.find("meta", attrs={"name": re.compile(r"^theme-color$", re.I)})
    theme_color = _normalize_color(theme_tag.get("content", "")) if theme_tag else None
    if theme_color:
        signals["theme_color"] = theme_color
        if theme_color in colors:
            colors.remove(theme_color)
        colors.insert(0, theme_color)  # site-declared brand color wins

    if colors:
        signals["colors"] = colors[:6]
        signals["primary_color"] = colors[0]
        accent = _pick_accent(colors, colors[0])
        if accent:
            signals["accent_color"] = accent

    hero = _find_hero_image(soup, base_url)
    if hero:
        signals["hero_image_url"] = hero

    return signals
