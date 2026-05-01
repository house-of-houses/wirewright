"""Runtime scanner for user-installed LTspice symbol libraries.

PHASE 1. Not implemented in v0.0.1.

The plan: at startup, scan the LTspice symbol library directories
(``~/Library/Application Support/LTspice/lib/sym/`` on macOS,
``%USERPROFILE%/AppData/Local/LTspice/lib/sym/`` on Windows) for ``.asy`` files
and parse the ``PIN x y NONE n`` lines to populate a registry that overrides
or extends ``builtin._REGISTRY``.

This will let users use any symbol that exists in their LTspice install,
not just the ones we hand-curated.
"""

from __future__ import annotations


def scan_lib_directory(path: str) -> None:
    """Scan an LTspice ``lib/sym`` directory and register every found symbol.

    PHASE 1: not implemented.
    """
    raise NotImplementedError("Phase 1: see docs/specs/ir.md")
