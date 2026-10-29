"""The one place Tallied talks to Claude.

- `extract(schema, ...)` returns a validated Pydantic instance via structured
  outputs (`messages.parse`). No free-text JSON scraping anywhere else.
- `chat(...)` is for the import review conversation (text plus an optional
  strict tool call).
- Model ids come from settings: FINANCE_AI_MODEL_IMPORT (document extraction,
  default claude-opus-5-5) and FINANCE_AI_MODEL_FAST (receipts, chat,
  valuations, default claude-sonnet-5-5).
- Every call logs model, purpose, tokens and latency; every failure becomes an
  AIError with a user-facing message and an HTTP status for the route to use.
"""
from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger("tallied.ai")

T = TypeVar("T", bound=BaseModel)

REQUEST_TIMEOUT_SECONDS = 180.0


class AIError(Exception):
    """A Claude call failed; `status_code` is what the route should return."""

    def __init__(self, message: str, *, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class AIUnavailable(AIError):
    def __init__(self):
        super().__init__(
            "AI features need FINANCE_ANTHROPIC_API_KEY. Add it to backend/.env and restart.",
            status_code=503,
        )


def ai_available() -> bool:
    return bool(settings.anthropic_api_key.strip())


def model_for(tier: str) -> str:
    return settings.ai_model_import if tier == "import" else settings.ai_model_fast


@lru_cache(maxsize=1)
def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        timeout=REQUEST_TIMEOUT_SECONDS,
        max_retries=2,
    )


def reset_client_cache() -> None:
    get_client.cache_clear()


def _translate(exc: Exception) -> AIError:
    if isinstance(exc, anthropic.AuthenticationError):
        return AIError("Anthropic rejected the API key (FINANCE_ANTHROPIC_API_KEY).", status_code=503)
    if isinstance(exc, anthropic.RateLimitError):
        return AIError("Anthropic rate limit reached; try again in a minute.", status_code=429)
    if isinstance(exc, anthropic.BadRequestError):
        return AIError(f"Anthropic rejected the request: {exc.message}", status_code=502)
    if isinstance(exc, anthropic.APIStatusError):
        return AIError(f"Anthropic error {exc.status_code}: {exc.message}", status_code=502)
    if isinstance(exc, anthropic.APIConnectionError):
        return AIError("Could not reach Anthropic.", status_code=502)
    return AIError(f"AI call failed: {type(exc).__name__}: {exc}", status_code=502)


def _log_usage(purpose: str, model: str, response: Any, started: float) -> None:
    usage = getattr(response, "usage", None)
    logger.info(
        "ai purpose=%s model=%s input_tokens=%s output_tokens=%s stop=%s ms=%d",
        purpose,
        model,
        getattr(usage, "input_tokens", None),
        getattr(usage, "output_tokens", None),
        getattr(response, "stop_reason", None),
        int((time.monotonic() - started) * 1000),
    )


def _check_stop(response: Any, purpose: str) -> None:
    stop = getattr(response, "stop_reason", None)
    if stop == "refusal":
        raise AIError(f"Claude declined the {purpose} request.", status_code=502)
    if stop == "max_tokens":
        raise AIError(f"The {purpose} response was cut off; the document may be too large.", status_code=502)


def extract[T: BaseModel](
    schema: type[T],
    *,
    content: str | list[dict[str, Any]],
    instructions: str,
    tier: str = "fast",
    max_tokens: int = 8192,
    purpose: str = "extract",
) -> T:
    """Ask Claude for a `schema` instance describing `content`. Raises AIError."""
    if not ai_available():
        raise AIUnavailable()
    model = model_for(tier)
    client = get_client()
    started = time.monotonic()
    try:
        response = client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=instructions,
            messages=[{"role": "user", "content": content}],
            output_format=schema,
        )
    except Exception as exc:  # translated below, never swallowed
        err = _translate(exc)
        logger.warning("ai purpose=%s model=%s failed: %s", purpose, model, err)
        raise err from exc
    _log_usage(purpose, model, response, started)
    _check_stop(response, purpose)
    parsed = getattr(response, "parsed_output", None)
    if parsed is None:
        raise AIError(f"Claude returned no structured {purpose} output.", status_code=502)
    return parsed


def chat(
    *,
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    tier: str = "fast",
    max_tokens: int = 2048,
    purpose: str = "chat",
) -> Any:
    """One conversational turn; returns the SDK Message (text blocks and optional tool_use)."""
    if not ai_available():
        raise AIUnavailable()
    model = model_for(tier)
    client = get_client()
    started = time.monotonic()
    kwargs: dict[str, Any] = {"model": model, "max_tokens": max_tokens, "system": system, "messages": messages}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = {"type": "auto"}
    try:
        response = client.messages.create(**kwargs)
    except Exception as exc:
        err = _translate(exc)
        logger.warning("ai purpose=%s model=%s failed: %s", purpose, model, err)
        raise err from exc
    _log_usage(purpose, model, response, started)
    _check_stop(response, purpose)
    return response
