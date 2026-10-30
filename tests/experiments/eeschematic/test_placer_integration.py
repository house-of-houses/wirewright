"""EEschematicPlacer wiring tests (no network)."""

from __future__ import annotations

import pytest

from wirewright.placers import get_placer, registry
from wirewright.placers.base import Placer


def test_registered() -> None:
    assert "eeschematic" in registry


def test_constructor_fails_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        get_placer("eeschematic")


def test_constructor_succeeds_with_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    p = get_placer("eeschematic")
    assert isinstance(p, Placer)
    assert p.name == "eeschematic"
    assert type(p).deterministic is False
