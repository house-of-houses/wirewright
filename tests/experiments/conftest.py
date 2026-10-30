"""Double-gated skip for live-LLM experiment tests.

Live tests run only when BOTH env vars are set:

- ``OPENAI_API_KEY`` — the API key itself.
- ``WIREWRIGHT_RUN_LIVE_LLM=1`` — an explicit opt-in that keeps ``uv run pytest``
  silent-safe (CI never sets this).
"""

from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    del config  # pytest hook signature; unused
    live_ok = os.environ.get("OPENAI_API_KEY") and os.environ.get(
        "WIREWRIGHT_RUN_LIVE_LLM"
    ) == "1"
    if live_ok:
        return
    skip_live = pytest.mark.skip(
        reason="live LLM test skipped (needs OPENAI_API_KEY and WIREWRIGHT_RUN_LIVE_LLM=1)"
    )
    for item in items:
        if "openai_live" in item.keywords:
            item.add_marker(skip_live)
