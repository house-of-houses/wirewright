# ADR 0001: Python as the host language

**Status**: Accepted (ELK references in this ADR are historical — see ADR-0005)

**Date**: 2026-05-01

## Context

wirewright needs a host language. Candidates are Python, TypeScript/Node, Rust, and Java. The placement work itself happens in third-party libraries (ELK in Java/JS, HOLA in C++) so the host language is mostly glue: parser, IR, emitter, pattern matcher, CLI, fixture management.

## Decision

Python 3.11+, managed with `uv`.

## Rationale

The pattern library is the part that will grow over time, written by humans (eventually including community contributors who care about analog circuits but are not necessarily software engineers). YAML files plus a Python matcher are easier for that audience than TypeScript or Rust.

NetworkX gives us subgraph isomorphism (VF2) without C++ build pain.

The LTspice `.asy` and `.asc` formats are line-based plain-text formats. Python's text-handling story is fine for this.

The user's existing tooling (Claude Code skills, sparring framework, AWS scripts) is Python-native. Lower context-switching cost.

uv is fast enough that the install time penalty over Node is negligible.

## Consequences

- ELK is reached through a tiny Node.js subprocess (the elk-bridge in `tools/elk-bridge/`). This adds a Node dependency for users who want ELK.
- HOLA is reached through pyhola which means a C++ build the first time it is installed. Documented in `docs/build-hola.md` (Phase 4).
- Type hints are used throughout (`mypy --strict`) to compensate for Python's looseness.
