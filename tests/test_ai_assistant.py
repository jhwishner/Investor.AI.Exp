from investor_ai import ai_assistant


def test_cloud_client_uses_streamlit_base_url(monkeypatch):
    captured = {}

    class DummyOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(
        ai_assistant,
        "_get_streamlit_secret",
        lambda name: {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_BASE_URL": "https://provider.example/v1",
        }.get(name),
    )
    monkeypatch.setattr("openai.OpenAI", DummyOpenAI)

    ai_assistant.get_openai_client()

    assert captured == {
        "api_key": "test-key",
        "base_url": "https://provider.example/v1",
    }


def test_provider_error_does_not_expose_api_key():
    error = RuntimeError("401 Invalid token. Received API Key = sk-secret123")

    result = ai_assistant._safe_provider_error(error)

    assert result == "The configured AI provider rejected the credentials (HTTP 401)"
    assert "sk-secret123" not in result


def test_missing_api_key_returns_fallback_commentary(monkeypatch):
    monkeypatch.setattr(ai_assistant, "_get_streamlit_secret", lambda _name: None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(ai_assistant, "_local_server_available", lambda: False)
    result = ai_assistant.generate_market_commentary("AAPL", "Bullish momentum")
    assert "ai assistant is not configured" in result.lower()


def test_local_ollama_is_preferred_when_available(monkeypatch):
    class DummyResponse:
        class Choice:
            class Message:
                content = "Buy quality names with strong trend and disciplined risk control."

            message = Message()

        choices = [Choice()]

    class DummyClient:
        def __init__(self, api_key, base_url=None):
            self.api_key = api_key
            self.base_url = base_url

        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return DummyResponse()

    monkeypatch.setattr(ai_assistant, "_local_server_available", lambda: True)
    monkeypatch.setattr(ai_assistant, "_model_name", lambda api_key=None: "qwen2.5:14b-instruct")

    def fake_client(api_key=None):
        return DummyClient("ollama", "http://localhost:11434/v1")

    monkeypatch.setattr(ai_assistant, "get_openai_client", fake_client)
    result = ai_assistant.generate_market_commentary("MSFT", "AI demand and cash-flow support")
    assert "Buy quality names" in result
