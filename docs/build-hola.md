# Building hola-graph from source

For most users the [hola-graph PyPI wheel](https://pypi.org/project/hola-graph/)
covers macOS arm64 and Linux x86_64 on Python 3.9–3.14. Just:

```bash
uv add hola-graph                # or 'pip install hola-graph'
```

This installs `hola_graph`, which vendors the C++ adaptagrams stack
(libcola, libavoid, libdialect, libvpsc) and exposes them via pybind11.

## When the wheel doesn't fit

Source build is required when:

- Your platform isn't covered by an upstream wheel (Linux arm64 as of
  0.1.5, Windows, FreeBSD).
- You want to patch HOLA's C++ to fix one of the known abort cases
  (`tb303-vco-saw-cliptop`, `tb303-vco-integrated`).
- You want to build with debug symbols for HOLA development.

## Source-build steps

The upstream `shakfu/hola-graph` repository's `Makefile` does the right
thing on macOS and Linux. Prerequisites: Python ≥3.9, a C++14 compiler,
CMake ≥3.18.

```bash
git clone https://github.com/shakfu/hola-graph.git
cd hola-graph
make             # downloads adaptagrams, builds, installs to current Python
python -c "import hola_graph; print(hola_graph.__file__)"
```

The first build pulls and compiles `mjwybrow/adaptagrams` from source.
Expect ~5 minutes on Apple Silicon, ~10 minutes on a slower x86_64.

## Pinning a known-good revision

In `pyproject.toml`'s `[project.optional-dependencies]` extra:

```toml
hola = ["hola-graph >=0.1.5"]
```

The `>=0.1.5` is the floor used in v0.1. Bumping to a later release
should be safe but verify:

1. `tb303-voice-chain` still places successfully (it was the bellwether
   for subprocess-isolation behavior).
2. The 3 known abort fixtures still abort *gracefully* (i.e.
   `_run_hola_subprocess` gets a non-zero exit code with a useful stderr
   rather than a silent kill).

## Reporting upstream issues

If a future fixture exposes a new C++ abort, file at
<https://github.com/shakfu/hola-graph/issues> with:

- The fixture's parsed component+net list (use `wirewright render
  <fixture> --placer hola` and capture the subprocess stderr).
- A minimal `HolaGraph` Python script that reproduces the abort.

The upstream maintainer has historically been responsive (issues usually
closed within weeks).

## libavoid availability

`hola-graph` ships libavoid's C++ source as part of the vendored
adaptagrams stack but exposes only its **geometry primitives** (`Box`,
`Polygon`, `Edge`, `Point`, `Rectangle`) via Python — not the
`Router` / `ConnRef` machinery. As of v0.1 there is no usable Python
binding to libavoid's connector router.

If you want libavoid routing, the path is to write a pybind11 wrapper
around the C++ `Router` class yourself. wirewright v0.1 ships
obstacle-aware L-shape routing in pure Python (`routing/orthogonal.py`)
as the practical alternative.
