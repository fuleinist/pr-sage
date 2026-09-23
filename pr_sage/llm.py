"""LLM providers: Ollama (local), OpenAI-compatible, and Echo (offline).

All providers implement `complete(system: str, user: str) -> str`.
Stdlib-only networking via urllib.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Protocol


class LLMError(RuntimeError):
    """Raised when the provider fails after one retry."""


class Provider(Protocol):
    def complete(self, system: str, user: str) -> str: ...


def _post_json(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json", **headers}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


class _RetryMixin:
    def _with_retry(self, fn):
        last: Exception | None = None
        for attempt in range(2):  # one retry per SPEC FR-3
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001 - provider errors are heterogeneous
                last = exc
                if attempt == 0:
                    time.sleep(1.0)
        raise LLMError(f"LLM provider failed after retry: {last}") from last


class OllamaProvider(_RetryMixin):
    """Local Ollama via /api/chat."""

    def __init__(
        self,
        model: str | None = None,
        host: str | None = None,
        timeout: int = 300,
    ):
        self.model = model or os.environ.get("PR_SAGE_MODEL", "qwen2.5-coder:7b")
        self.host = (host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
        self.timeout = timeout

    def build_payload(self, system: str, user: str) -> dict:
        return {
            "model": self.model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

    def complete(self, system: str, user: str) -> str:
        def call() -> str:
            resp = _post_json(f"{self.host}/api/chat", self.build_payload(system, user), {}, self.timeout)
            msg = resp.get("message") or {}
            content = msg.get("content", "")
            if not content:
                raise LLMError("Ollama returned an empty message")
            return content

        return self._with_retry(call)


class OpenAIProvider(_RetryMixin):
    """Any OpenAI-compatible /chat/completions endpoint."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: int = 300,
    ):
        self.model = model or os.environ.get("PR_SAGE_OPENAI_MODEL", "gpt-4o-mini")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.timeout = timeout

    def build_payload(self, system: str, user: str) -> dict:
        return {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }

    def build_headers(self) -> dict:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def complete(self, system: str, user: str) -> str:
        def call() -> str:
            resp = _post_json(
                f"{self.base_url}/chat/completions",
                self.build_payload(system, user),
                self.build_headers(),
                self.timeout,
            )
            choices = resp.get("choices") or []
            if not choices:
                raise LLMError("OpenAI-compatible endpoint returned no choices")
            content = (choices[0].get("message") or {}).get("content", "")
            if not content:
                raise LLMError("OpenAI-compatible endpoint returned empty content")
            return content

        return self._with_retry(call)


class EchoProvider:
    """Offline provider returning a fixed, spec-valid review (tests/demos)."""

    def complete(self, system: str, user: str) -> str:
        return json.dumps(
            {
                "summary": "Echo provider review: this PR was processed in offline mode. "
                "No LLM backend was contacted.",
                "strengths": ["The PR is well-scoped and reviewable."],
                "concerns": [
                    {
                        "severity": "nit",
                        "message": "Run with --provider ollama (or openai) for a real review.",
                    }
                ],
                "suggestions": [
                    {"file": "README.md", "body": "Document how to run the review locally."}
                ],
                "verdict": "comment",
            }
        )


def get_provider(name: str) -> Provider:
    name = name.lower()
    if name == "echo":
        return EchoProvider()
    if name == "ollama":
        return OllamaProvider()
    if name == "openai":
        return OpenAIProvider()
    raise LLMError(f"Unknown provider {name!r} (choose: ollama, openai, echo)")
