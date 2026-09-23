"""LLM provider payload tests + echo provider (no network)."""

import json

import pytest

from pr_sage.llm import (
    EchoProvider,
    LLMError,
    OllamaProvider,
    OpenAIProvider,
    get_provider,
)
from pr_sage.review import parse_review


def test_ollama_payload_shape():
    p = OllamaProvider(model="test-model", host="http://localhost:11434/")
    payload = p.build_payload("sys", "usr")
    assert payload["model"] == "test-model"
    assert payload["stream"] is False
    assert payload["format"] == "json"
    assert payload["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]
    assert p.host == "http://localhost:11434"  # trailing slash stripped


def test_openai_payload_and_headers():
    p = OpenAIProvider(model="m", api_key="sk-test", base_url="https://x.test/v1/")
    payload = p.build_payload("sys", "usr")
    assert payload["model"] == "m"
    assert payload["response_format"] == {"type": "json_object"}
    assert p.build_headers() == {"Authorization": "Bearer sk-test"}
    assert p.base_url == "https://x.test/v1"


def test_openai_headers_empty_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    p = OpenAIProvider(api_key="")
    assert p.build_headers() == {}


def test_echo_provider_returns_valid_review():
    raw = EchoProvider().complete("s", "u")
    review = parse_review(raw)
    assert review.structured is True
    assert review.verdict == "comment"
    assert "offline" in review.summary.lower()


def test_retry_wraps_failures(monkeypatch):
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise RuntimeError("connection refused")

    p = OllamaProvider()
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(LLMError):
        p._with_retry(boom)
    assert calls["n"] == 2  # one attempt + one retry


def test_get_provider_registry():
    assert isinstance(get_provider("echo"), EchoProvider)
    assert isinstance(get_provider("ollama"), OllamaProvider)
    assert isinstance(get_provider("openai"), OpenAIProvider)
    with pytest.raises(LLMError):
        get_provider("nope")
