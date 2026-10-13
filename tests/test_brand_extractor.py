"""Brand-signal extraction from a lead's own homepage HTML."""

from app.services.brand_extractor import extract_brand_signals


def test_extracts_logo_theme_color_and_hero():
    html = """
    <html><head>
      <meta name="theme-color" content="#1f6feb">
      <meta property="og:image" content="/img/hero-spa.jpg">
      <style>:root{--primary:#1f6feb;--accent:#e0a44c;} .x{color:#ffffff}</style>
    </head><body>
      <header><img src="/assets/site-logo.png" alt="Clinic Logo" class="logo"></header>
    </body></html>
    """
    signals = extract_brand_signals(html, "https://clinic.example/")
    assert signals["logo_url"] == "https://clinic.example/assets/site-logo.png"
    assert signals["logo_confidence"] == 0.9
    assert signals["theme_color"] == "#1f6feb"
    assert signals["primary_color"] == "#1f6feb"  # theme-color wins as primary
    assert signals["accent_color"] == "#e0a44c"
    assert signals["hero_image_url"] == "https://clinic.example/img/hero-spa.jpg"


def test_neutrals_are_filtered_out():
    html = "<style>body{background:#ffffff;color:#000000;border:#f2f2f2}</style>"
    signals = extract_brand_signals(html, "https://x.example/")
    # Only near-white/black/gray present -> no brand color surfaced
    assert "primary_color" not in signals


def test_favicon_is_lower_confidence_logo_fallback():
    html = '<head><link rel="icon" href="/favicon.png"></head><body></body>'
    signals = extract_brand_signals(html, "https://x.example/")
    assert signals["logo_url"] == "https://x.example/favicon.png"
    assert signals["logo_confidence"] == 0.6


def test_rgb_brand_var_is_normalized_to_hex():
    html = "<style>:root{--brand-primary: rgb(47, 111, 94);}</style>"
    signals = extract_brand_signals(html, "https://x.example/")
    assert signals["primary_color"] == "#2f6f5e"


def test_returns_empty_on_blank_html():
    assert extract_brand_signals("", "https://x.example/") == {}
