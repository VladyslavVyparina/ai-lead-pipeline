"""Multi-template routing: per-niche local renderers + Vercel project routing."""

from pathlib import Path

from app.adapters.hosting import LocalStubAdapter, VercelAdapter, _local_renderer_for
from app.services.config_loader import load


def test_registry_covers_all_target_niches():
    categories = load("templates")["categories"]
    for niche in ["massage_wellness", "spa", "cosmetology", "dental", "coach_trainer"]:
        assert niche in categories, f"missing category: {niche}"
        assert categories[niche]["id"], niche


def test_massage_category_routes_to_massage_template():
    categories = load("templates")["categories"]
    assert categories["massage_wellness"]["id"] == "massage-spa-template"
    assert categories["spa"]["id"] == "massage-spa-template"


def test_local_renderer_selects_registered_template():
    assert _local_renderer_for("massage-spa-template") == "preview_massage_spa.html"


def test_local_renderer_falls_back_for_unknown_template():
    assert _local_renderer_for("does-not-exist") == "preview_static.html"


def test_local_stub_renders_massage_specific_markup():
    adapter = LocalStubAdapter()
    result = adapter.deploy(
        template_id="massage-spa-template",
        template_version="v1",
        site_config={
            "business_name": {"value": "Kaapora"},
            "content": {
                "hero": {"headline": "Kaapora", "subheadline": "Massagem no Porto"},
                "services": [{"name": "Massagem Relaxante", "price": "€25"}],
                "cta": {"label": "Marcar agora", "supporting": ""},
                "contact": {"phone": "+351911150331", "whatsapp": "+351911150331"},
                "theme": {"primary_color": "#2f6f5e"},
                "disclaimer": "Pré-visualização não oficial.",
                "seo_title": "Kaapora",
            },
        },
    )
    html = Path(result["local_path"]).read_text(encoding="utf-8")
    # Massage/spa v2 renderer signature (not present in the generic renderer)
    assert "hero-grid" in html
    assert "booking-section" in html
    assert "data-qa=\"hero\"" in html
    assert "data-qa=\"services\"" in html
    assert "data-qa=\"contact\"" in html
    assert "data-qa=\"disclaimer\"" in html
    assert "Massagem Relaxante" in html


class _FakeResponse:
    status_code = 200
    text = ""

    def json(self):
        return {"id": "dpl_123", "url": "preview-example.vercel.app"}


def test_vercel_routes_to_per_template_project(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return _FakeResponse()

    monkeypatch.setattr("app.adapters.hosting.httpx.post", fake_post)
    adapter = VercelAdapter(
        token="t",
        project_id="prj_default",
        github_repo_id="000",
        template_projects={
            "massage-spa-template": {"project_id": "prj_massage", "github_repo_id": "111", "git_ref": "release"}
        },
    )
    adapter.deploy(
        template_id="massage-spa-template",
        template_version="v1",
        site_config={"business_name": {"value": "Spa"}},
    )
    payload = captured["json"]
    assert payload["project"] == "prj_massage"
    assert payload["gitSource"] == {"type": "github", "repoId": "111", "ref": "release"}


def test_vercel_falls_back_to_default_project_when_unmapped(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return _FakeResponse()

    monkeypatch.setattr("app.adapters.hosting.httpx.post", fake_post)
    adapter = VercelAdapter(
        token="t",
        project_id="prj_default",
        github_repo_id="000",
        template_projects={"dental": {"project_id": "prj_dental", "github_repo_id": "222"}},
    )
    adapter.deploy(
        template_id="coach-next-template",
        template_version="v1",
        site_config={"business_name": {"value": "Coach"}},
    )
    payload = captured["json"]
    assert payload["project"] == "prj_default"
    assert payload["gitSource"]["repoId"] == "000"
