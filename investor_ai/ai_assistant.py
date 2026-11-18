"""Optional AI assistant for market commentary and recommendation summaries.

This module is intentionally safe-by-default: it prefers free local inference via
Ollama when available, then falls back to a cloud API only if a key is set, and
otherwise returns a helpful message instead of failing. That keeps the app useful
without recurring cost.
"""

from __future__ import annotations

import os
import re
from urllib import request, error


def _get_streamlit_secret(name: str) -> str | None:
    """Retrieve a string setting from Streamlit secrets when available."""
    try:
        import streamlit as st
        if hasattr(st, "secrets") and name in st.secrets:
            value = st.secrets[name]
            return str(value).strip() or None
    except Exception:
        pass
    return None


def _get_api_key_from_streamlit() -> str | None:
    return _get_streamlit_secret("OPENAI_API_KEY")


def _cloud_base_url() -> str | None:
    """Resolve the optional OpenAI-compatible endpoint from secrets or the environment."""
    return _get_streamlit_secret("OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL") or None


def _safe_provider_error(exc: Exception) -> str:
    """Return actionable provider context without exposing key fragments or tokens."""
    message = str(exc)
    message = re.sub(r"sk-[A-Za-z0-9_-]+", "[redacted API key]", message)
    message = re.sub(
        r"(?i)(api[ _-]?key|token)(\s*=\s*|\s*:\s*)[^,}\s]+",
        r"\1\2[redacted]",
        message,
    )
    if "401" in message or "authentication" in message.lower():
        return "The configured AI provider rejected the credentials (HTTP 401)"
    return "The AI provider request failed"


def _local_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")


def _local_model_name() -> str:
    return os.getenv("OLLAMA_MODEL", "llama3.1:8b")


def _local_server_available() -> bool:
    candidates = [
        _local_base_url().rstrip("/") + "/models",
        "http://localhost:11434/api/tags",
        "http://127.0.0.1:11434/v1/models",
    ]
    seen = set()
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        try:
            with request.urlopen(url, timeout=2) as resp:
                if getattr(resp, "status", 200) == 200:
                    return True
        except (error.URLError, error.HTTPError, TimeoutError, OSError):
            continue
    return False


def get_openai_client(api_key: str | None = None, base_url: str | None = None):
    """Return a configured OpenAI-compatible client from either cloud or local Ollama.
    
    Args:
        api_key: OpenAI API key. If not provided, will check Streamlit secrets and environment.
        base_url: Custom base URL for the API. If not provided, checks environment.
    """
    # Try provided api_key, then Streamlit secrets, then environment
    if api_key is None:
        api_key = _get_api_key_from_streamlit() or os.getenv("OPENAI_API_KEY")
    
    if api_key:
        try:
            from openai import OpenAI

            if base_url is None:
                base_url = _cloud_base_url()
            return OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
        except Exception:
            return None

    if _local_server_available():
        try:
            from openai import OpenAI

            return OpenAI(api_key="ollama", base_url=_local_base_url())
        except Exception:
            return None

    return None


def _fallback_commentary(ticker: str, purpose: str) -> str:
    return (
        f"AI assistant is not configured for {ticker}. To enable {purpose.lower()} for free, run a local "
        "model such as Ollama and start a model like `qwen2.5:14b-instruct`, or set OPENAI_API_KEY for a cloud model. "
        "The built-in rule-based signals remain active until then."
    )


def _model_name(api_key: str | None = None) -> str:
    if api_key is None:
        api_key = _get_api_key_from_streamlit() or os.getenv("OPENAI_API_KEY")
    
    # Check Streamlit secrets first, then environment, then use defaults
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "OPENAI_MODEL" in st.secrets:
            return st.secrets["OPENAI_MODEL"]
    except Exception:
        pass
    
    if api_key:
        return _get_streamlit_secret("OPENAI_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    return os.getenv("OLLAMA_MODEL", "llama3.1:8b")


def generate_market_commentary(ticker: str, market_context: str, api_key: str | None = None) -> str:
    """Generate a brief, investable commentary blurb for a ticker or market theme.
    
    Args:
        ticker: The stock ticker symbol.
        market_context: Context about the market/ticker for generating commentary.
        api_key: Optional OpenAI API key. If not provided, will check Streamlit secrets.
    """
    client = get_openai_client(api_key=api_key)
    if client is None:
        return _fallback_commentary(ticker, "market commentary")

    try:
        response = client.chat.completions.create(
            model=_model_name(api_key=api_key),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a careful market commentator for a retail investing dashboard. "
                        "Keep the answer concise, practical, and risk-aware. Do not claim to be "
                        "licensed financial advice. Use plain English and focus on trend, risk, and "
                        "decision framing."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Ticker: {ticker}\n"
                        f"Context: {market_context}\n\n"
                        "Provide a short market commentary and a recommendation stance. "
                        "Mention the key risk factors, expected direction, and a simple action plan."
                    ),
                },
            ],
            temperature=0.4,
            max_tokens=250,
        )
        content = response.choices[0].message.content
        if content:
            return content.strip()
    except Exception:
        return (
            f"AI market commentary for {ticker} could not be generated because the model call failed. "
            "Check your local Ollama server or your API configuration, then retry."
        )

    return _fallback_commentary(ticker, "market commentary")


def generate_recommendation_summary(portfolio_summary: str, api_key: str | None = None) -> str:
    """Generate a portfolio-level recommendation assistant summary.
    
    Args:
        portfolio_summary: Summary of the portfolio to analyze.
        api_key: Optional OpenAI API key. If not provided, will check Streamlit secrets.
    """
    client = get_openai_client(api_key=api_key)
    if client is None:
        return (
            "AI assistant is not configured for recommendation summaries. To use this feature for free, "
            "run Ollama locally with a small model such as `qwen2.5:14b-instruct`, or set OPENAI_API_KEY "
            "for a cloud model."
        )

    try:
        response = client.chat.completions.create(
            model=_model_name(api_key=api_key),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an investment assistant for a retail dashboard. Summarize the portfolio, "
                        "highlight concentration and risk, prioritize the strongest and weakest names, and "
                        "suggest a realistic next step. Keep the advice practical, brief, and non-diagnostic "
                        "rather than legal or tax advice."
                    ),
                },
                {
                    "role": "user",
                    "content": portfolio_summary,
                },
            ],
            temperature=0.4,
            max_tokens=250,
        )
        content = response.choices[0].message.content
        if content:
            return content.strip()
    except Exception as e:
        error_msg = _safe_provider_error(e)
        return (
            f"AI recommendation summary could not be generated: {error_msg}. "
            "Check your API configuration and retry."
        )

    return (
        "AI recommendation summary is unavailable right now. Check your API configuration and retry."
    )
