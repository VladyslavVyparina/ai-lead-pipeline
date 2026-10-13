import httpx
import pytest

from app.services.web_crawler import CrawlError, crawl_website


def _response(request, status=200, body="", content_type="text/html"):
    return httpx.Response(status, text=body, headers={"content-type": content_type}, request=request)


def test_robots_is_enforced_before_a_page_is_fetched():
    requested = []

    def handler(request):
        requested.append(str(request.url))
        if request.url.path == "/robots.txt":
            return _response(request, body="User-agent: AILeadResearchBot\nDisallow: /private")
        return _response(request, body="<title>Private</title><p>nope</p>")

    with pytest.raises(CrawlError, match="disallowed by robots"):
        crawl_website("https://robots-blocks.invalid/private", allow_private_hosts=True,
                      transport=httpx.MockTransport(handler), use_cache=False, sleep_fn=lambda _: None)
    assert requested == ["https://robots-blocks.invalid/robots.txt"]


def test_retries_json_ld_duplicate_content_and_result_cache():
    calls = {"/": 0, "/robots.txt": 0}
    html = """<html><head><title>Studio</title><script type='application/ld+json'>
    {"@context":"https://schema.org","@type":"LocalBusiness","name":"Studio"}</script>
    </head><body><p>Welcome to the studio with a real business description.</p><a href='/contact'>Contact</a></body></html>"""

    def handler(request):
        calls[request.url.path] = calls.get(request.url.path, 0) + 1
        if request.url.path == "/robots.txt":
            return _response(request, body="User-agent: *\nAllow: /")
        if request.url.path == "/" and calls["/"] == 1:
            return _response(request, status=503, body="temporary")
        return _response(request, body=html)

    transport = httpx.MockTransport(handler)
    kwargs = dict(allow_private_hosts=True, transport=transport, sleep_fn=lambda _: None,
                  cache_ttl_seconds=60, max_pages=2)
    first = crawl_website("https://crawler-cache.invalid", **kwargs)
    second = crawl_website("https://crawler-cache.invalid", **kwargs)
    assert calls["/"] == 2  # one retry; the cached second crawl does not fetch
    assert len(first.pages) == 1  # /contact has duplicate content
    assert first.json_ld[0]["@type"] == "LocalBusiness"
    assert second.pages[0].url == first.pages[0].url


def test_reports_javascript_shell_without_attempting_browser_automation():
    def handler(request):
        if request.url.path == "/robots.txt":
            return _response(request, body="User-agent: *\nAllow: /")
        return _response(request, body="<html><body><div id='root'></div><script src='/app.js'></script></body></html>")

    result = crawl_website("https://js-shell.invalid", allow_private_hosts=True,
                           transport=httpx.MockTransport(handler), use_cache=False, sleep_fn=lambda _: None)
    assert result.extraction_status == "js_shell_detected"
    assert result.pages[0].extraction_status == "js_shell_detected"
