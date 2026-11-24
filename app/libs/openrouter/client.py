from typing import Any

import httpx

from app.config.settings import settings


class OpenRouterError(Exception):
    """Raised when OpenRouter can't be reached or returns an unusable reply."""


class OpenRouterNotConfiguredError(OpenRouterError):
    """Raised when no OpenRouter API key is configured."""


class OpenRouterClient:
    """Minimal async client for OpenRouter's chat-completions endpoint."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.api_key = settings.openrouter_api_key if api_key is None else api_key
        self.base_url = (base_url or settings.openrouter_base_url).rstrip("/")
        self.model = model or settings.openrouter_model
        self.timeout = timeout or settings.openrouter_timeout_seconds

    async def complete_json(
        self,
        messages: list[dict[str, Any]],
        *,
        plugins: list[dict[str, Any]] | None = None,
        max_tokens: int = 16000,
    ) -> str:
        """
        Run a chat completion that is expected to answer with a JSON object.

        :param messages: OpenAI-style chat messages; content parts may carry
            ``image_url`` or ``file`` inputs.
        :param plugins: OpenRouter plugins, e.g. the PDF ``file-parser``.
        :param max_tokens: cap on the reply length.
        :raises OpenRouterNotConfiguredError: if there's no API key.
        :raises OpenRouterError: on transport errors, non-2xx replies, or a
            reply without message content.
        :return: the raw text of the model's reply.
        """
        if not self.api_key:
            raise OpenRouterNotConfiguredError(
                "Receipt/statement recognition is not configured (no OpenRouter key)."
            )
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        if plugins:
            payload["plugins"] = plugins
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as http:
                response = await http.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise OpenRouterError(str(exc)) from exc
        if not isinstance(content, str) or not content.strip():
            raise OpenRouterError("Empty reply from OpenRouter.")
        return content
