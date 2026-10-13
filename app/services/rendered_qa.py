"""Browser-rendered preview validation with desktop/mobile screenshots."""

from __future__ import annotations

from pathlib import Path

from app.config import PROJECT_ROOT, settings


def _artifact_url(path: Path) -> str:
    artifact_root = (PROJECT_ROOT / "artifacts").resolve()
    try:
        relative = path.resolve().relative_to(artifact_root)
    except ValueError:
        return str(path.resolve())
    return "/artifacts/" + relative.as_posix()


def _identity_matches(business_name: str, surfaces: list[str]) -> bool:
    """Check visible and accessible identity surfaces without requiring text logo markup."""
    expected = business_name.casefold()
    return any(expected in (surface or "").casefold() for surface in surfaces)

def validate_rendered_preview(
    *,
    url: str,
    business_name: str,
    build_id: int,
    expected_phone: str = "",
    expected_email: str = "",
) -> dict:
    artifact_dir = Path(settings.qa_artifact_dir).resolve() / f"build-{build_id}"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    desktop_path = artifact_dir / "desktop.png"
    mobile_path = artifact_dir / "mobile.png"
    result = {
        "page_loaded": False,
        "business_identity_ok": False,
        "required_sections_ok": False,
        "contact_links_ok": False,
        "form_submission_ok": False,
        "responsive_ok": False,
        "no_placeholders": False,
        "unofficial_disclaimer": False,
        "screenshot_desktop": "",
        "screenshot_mobile": "",
        "notes": [],
    }

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        result["notes"].append("Playwright is not installed; rendered QA failed closed")
        return result

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            desktop = browser.new_context(viewport={"width": 1440, "height": 1000})
            page = desktop.new_page()
            form_request_seen = {"value": False}

            def intercept_form(route, request):
                form_request_seen["value"] = True
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"ok":true,"qa":true}',
                    headers={"Access-Control-Allow-Origin": "*"},
                )

            page.route("**/preview-form", intercept_form)
            response = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            status_ok = response is None or response.status < 400
            result["page_loaded"] = status_ok

            body_text = page.locator("body").inner_text(timeout=5_000)
            # A branded preview may intentionally use an image-only logo in the
            # navigation.  ``inner_text`` does not include an image's alt text,
            # so checking the visible body alone produces a false QA failure for
            # otherwise correctly branded sites.  Treat the document title and
            # accessible image labels as equally valid identity surfaces.
            identity_surfaces = [body_text, page.title()]
            identity_surfaces.extend(
                page.locator("img[alt]").evaluate_all("images => images.map(image => image.alt)")
            )
            result["business_identity_ok"] = _identity_matches(business_name, identity_surfaces)
            required = ["[data-qa='hero']", "[data-qa='services']", "[data-qa='contact']", "[data-qa='disclaimer']"]
            result["required_sections_ok"] = all(page.locator(selector).count() > 0 for selector in required)
            disclaimer_text = page.locator("[data-qa='disclaimer']").inner_text().casefold()
            result["unofficial_disclaimer"] = (
                "não oficial" in disclaimer_text
                or "nao oficial" in disclaimer_text
                or "unofficial" in disclaimer_text
            )

            placeholders = ("lorem ipsum", "{{", "todo", "your business", "example business")
            result["no_placeholders"] = not any(value in body_text.casefold() for value in placeholders)

            links_ok = True
            if expected_phone:
                phone_links = page.locator("a[href^='tel:']")
                links_ok = links_ok and phone_links.count() > 0
            if expected_email:
                email_links = page.locator("a[href^='mailto:']")
                links_ok = links_ok and email_links.count() > 0
            result["contact_links_ok"] = links_ok

            form = page.locator("form[data-qa='booking-form'], form").first
            if form.count():
                name = form.locator("[name='name']")
                contact = form.locator("[name='contact']")
                if name.count() and contact.count():
                    name.fill("QA Check")
                    contact.fill("qa@example.invalid")
                    if form.get_attribute("data-qa-json") == "true":
                        form.locator("button[type='submit'], input[type='submit']").first.click()
                        page.wait_for_timeout(500)
                        result["form_submission_ok"] = form_request_seen["value"]
                    else:
                        fetch_ok = page.evaluate(
                            """async () => {
                                const form = document.querySelector("form[data-qa='booking-form'], form");
                                const response = await fetch(form.action, {
                                    method: form.method || "POST",
                                    body: new FormData(form)
                                });
                                return response.ok;
                            }"""
                        )
                        result["form_submission_ok"] = bool(
                            fetch_ok and form_request_seen["value"]
                        )

            result["responsive_ok"] = bool(
                page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 2")
            )
            page.screenshot(path=str(desktop_path), full_page=True)
            result["screenshot_desktop"] = _artifact_url(desktop_path)
            desktop.close()

            mobile = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
            mobile_page = mobile.new_page()
            mobile_page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            mobile_ok = bool(
                mobile_page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 2")
            )
            result["responsive_ok"] = result["responsive_ok"] and mobile_ok
            mobile_page.screenshot(path=str(mobile_path), full_page=True)
            result["screenshot_mobile"] = _artifact_url(mobile_path)
            mobile.close()
            browser.close()
    except Exception as exc:
        result["notes"].append(f"Rendered QA failed: {exc}")
    return result
