"""Unit tests for the OpenAI client wrapper.

The real SDK is mocked; no network calls occur. These tests enforce the
error-mapping contract: every ``openai.*`` failure must surface as a
:class:`PlacerEngineError`.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from wirewright.placers.base import PlacerEngineError

openai = pytest.importorskip("openai")

from wirewright.experiments.eeschematic.openai_client import vision_call  # noqa: E402


def _png_bytes() -> bytes:
    # 1x1 red PNG (precomputed)
    import base64

    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
    )


@pytest.fixture
def img(tmp_path: Path) -> Path:
    p = tmp_path / "x.png"
    p.write_bytes(_png_bytes())
    return p


def _mock_response(text: str = "ok", finish: str = "stop") -> MagicMock:
    r = MagicMock()
    r.choices = [MagicMock()]
    r.choices[0].message.content = text
    r.choices[0].finish_reason = finish
    r.usage.prompt_tokens = 10
    r.usage.completion_tokens = 5
    return r


def test_success_logs_call(img: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    log = tmp_path / "calls.jsonl"
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_response("hello")
    with patch("openai.OpenAI", return_value=mock_client):
        result = vision_call(
            system="sys",
            user_text="hi",
            image_paths=[img],
            model="gpt-5",
            log_path=log,
        )
    assert result.text == "hello"
    assert result.prompt_tokens == 10
    assert result.cost_usd > 0
    assert log.exists()
    record = json.loads(log.read_text().strip())
    assert record["model"] == "gpt-5"
    assert record["image_count"] == 1


def test_missing_api_key_raises_engine_error(img: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(PlacerEngineError, match="OPENAI_API_KEY"):
        vision_call(system="s", user_text="u", image_paths=[img])


def test_bad_request_is_terminal(img: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    err = openai.BadRequestError("bad", response=MagicMock(), body=None)
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = err
    with (
        patch("openai.OpenAI", return_value=mock_client),
        pytest.raises(PlacerEngineError, match="terminal"),
    ):
        vision_call(system="s", user_text="u", image_paths=[img])
    assert mock_client.chat.completions.create.call_count == 1  # no retry


def test_rate_limit_retries_then_exhausts(
    img: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        "wirewright.experiments.eeschematic.openai_client._BACKOFF_BASE_SECONDS", 0.0
    )
    err = openai.RateLimitError("slow down", response=MagicMock(), body=None)
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = err
    with (
        patch("openai.OpenAI", return_value=mock_client),
        pytest.raises(PlacerEngineError, match="retries exhausted"),
    ):
        vision_call(system="s", user_text="u", image_paths=[img])
    assert mock_client.chat.completions.create.call_count == 3


def test_rate_limit_then_success(img: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        "wirewright.experiments.eeschematic.openai_client._BACKOFF_BASE_SECONDS", 0.0
    )
    err = openai.RateLimitError("slow down", response=MagicMock(), body=None)
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [err, _mock_response("ok")]
    with patch("openai.OpenAI", return_value=mock_client):
        result = vision_call(system="s", user_text="u", image_paths=[img])
    assert result.text == "ok"


def test_content_filter_finish_reason_is_terminal(
    img: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_response(
        "", finish="content_filter"
    )
    with (
        patch("openai.OpenAI", return_value=mock_client),
        pytest.raises(PlacerEngineError, match="content_filter"),
    ):
        vision_call(system="s", user_text="u", image_paths=[img])
