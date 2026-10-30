"""Thin OpenAI wrapper for the VCoT loop.

Three guarantees:

1. All ``openai.*`` exceptions are re-raised as
   :class:`wirewright.placers.base.PlacerEngineError` with the original
   as ``__cause__``. The ``AutoPlacer`` fallback chain and other callers
   only need to know about one exception type.
2. Exponential backoff on ``429`` / 5xx only; auth / bad-request / content
   filter are terminal.
3. Every call is logged (model, prompt chars, completion chars, cost
   estimate) to a per-fixture ``calls.jsonl``.

See ``docs/plans/eeschematic-experiment.md`` for the per-fixture $20
budget cap enforced in :mod:`.agent`.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from wirewright.placers.base import PlacerEngineError

logger = logging.getLogger(__name__)

#: Approximate per-million-token prices in USD. Published OpenAI pricing
#: moves; these are a rough-order budget guard, not a billing source.
#: Override by setting WIREWRIGHT_LLM_PRICE_IN / WIREWRIGHT_LLM_PRICE_OUT.
_DEFAULT_PRICE_IN_PER_MTOK = 1.25
_DEFAULT_PRICE_OUT_PER_MTOK = 10.0

_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 1.0


@dataclass(frozen=True)
class CallResult:
    """Outcome of one vision call."""

    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    finish_reason: str


def _price_in() -> float:
    return float(os.environ.get("WIREWRIGHT_LLM_PRICE_IN", _DEFAULT_PRICE_IN_PER_MTOK))


def _price_out() -> float:
    return float(os.environ.get("WIREWRIGHT_LLM_PRICE_OUT", _DEFAULT_PRICE_OUT_PER_MTOK))


def _estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    return (prompt_tokens * _price_in() + completion_tokens * _price_out()) / 1_000_000


def _image_data_url(image_path: Path) -> str:
    data = image_path.read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _log_call(log_path: Path | None, record: dict[str, Any]) -> None:
    if log_path is None:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def vision_call(
    *,
    system: str,
    user_text: str,
    image_paths: list[Path],
    model: str = "gpt-5",
    log_path: Path | None = None,
) -> CallResult:
    """One MLLM call with text + attached PNG images.

    Raises :class:`PlacerEngineError` on any API failure after retries.
    """
    try:
        import openai
    except ImportError as e:
        raise PlacerEngineError(
            "openai SDK not installed; run `uv sync --extra experiments`"
        ) from e

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise PlacerEngineError("OPENAI_API_KEY is not set")

    content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
    for p in image_paths:
        content.append({"type": "image_url", "image_url": {"url": _image_data_url(p)}})

    messages: list[Any] = [
        {"role": "system", "content": system},
        {"role": "user", "content": content},
    ]

    client = openai.OpenAI(api_key=api_key)

    retryable_exc = (
        openai.APITimeoutError,
        openai.APIConnectionError,
        openai.RateLimitError,
        openai.InternalServerError,
    )
    terminal_exc = (
        openai.AuthenticationError,
        openai.PermissionDeniedError,
        openai.NotFoundError,
        openai.BadRequestError,
        openai.UnprocessableEntityError,
    )

    last_err: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = client.chat.completions.create(model=model, messages=messages)
        except terminal_exc as e:
            raise PlacerEngineError(f"OpenAI terminal error: {e!s}") from e
        except retryable_exc as e:
            last_err = e
            if attempt == _MAX_RETRIES - 1:
                raise PlacerEngineError(
                    f"OpenAI retries exhausted after {_MAX_RETRIES} attempts: {e!s}"
                ) from e
            delay = _BACKOFF_BASE_SECONDS * (2**attempt)
            logger.warning(
                "OpenAI retryable error (attempt %d/%d, sleeping %.1fs): %s",
                attempt + 1,
                _MAX_RETRIES,
                delay,
                e,
            )
            time.sleep(delay)
            continue
        except openai.APIError as e:  # catch-all for anything else
            raise PlacerEngineError(f"OpenAI APIError: {e!s}") from e
        else:
            break
    else:  # pragma: no cover — loop always breaks or raises
        raise PlacerEngineError(f"OpenAI unknown failure: {last_err!s}")

    choice = response.choices[0]
    text = choice.message.content or ""
    finish = choice.finish_reason or "unknown"
    if finish == "content_filter":
        raise PlacerEngineError("OpenAI finish_reason=content_filter")

    usage = response.usage
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0
    cost = _estimate_cost(prompt_tokens, completion_tokens)

    _log_call(
        log_path,
        {
            "model": model,
            "finish_reason": finish,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost_usd": cost,
            "image_count": len(image_paths),
            "user_text_chars": len(user_text),
            "response_chars": len(text),
        },
    )

    return CallResult(
        text=text,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost,
        finish_reason=finish,
    )
