from types import SimpleNamespace

from app.services import ai_agent


def test_openrouter_chat_uses_compatible_endpoint_and_usage_cost(monkeypatch):
    settings = SimpleNamespace(
        ai_provider="openrouter",
        openrouter_api_key="test-router-key",
        openrouter_site_url="https://example.test",
        openrouter_app_name="AI Lead Test",
        openai_api_key="",
        openrouter_model="openrouter/free",
        chat_model="openrouter/free",
        ai_max_output_tokens=600,
    )
    monkeypatch.setattr(ai_agent, "settings", settings)

    class FakeResponse:
        headers = {"x-request-id": "router-request"}

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "id": "generation-id",
                "model": "qwen/qwen3-32b",
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 6,
                    "cost": 0.00000264,
                },
            }

    captured = {}

    def fake_post(url, headers, json, timeout):
        captured.update(url=url, headers=headers, payload=json, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr(ai_agent.httpx, "post", fake_post)
    response = ai_agent.chat_json([{"role": "user", "content": "{}"}])

    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-router-key"
    assert captured["headers"]["HTTP-Referer"] == "https://example.test"
    assert captured["payload"]["model"] == "openrouter/free"
    assert response.provider_request_id == "router-request"
    assert response.estimated_cost_usd == 0.00000264
