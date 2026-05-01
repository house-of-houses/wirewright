# elk-bridge

A 30-line Node.js wrapper around [elkjs](https://github.com/kieler/elkjs).
Reads an ELK graph as JSON on stdin, returns the laid-out graph as JSON on stdout.

Used by `src/wirewright/placers/elk.py` via subprocess so we can use ELK from
Python without dragging in a JVM or maintaining Python ELK bindings.

## Install

```bash
cd tools/elk-bridge
npm install
```

## Manual test

```bash
echo '{"id":"root","children":[{"id":"a","width":50,"height":30},{"id":"b","width":50,"height":30}],"edges":[{"id":"e1","sources":["a"],"targets":["b"]}]}' | node elk-layout.mjs
```

## Why a subprocess and not a Python port

elkjs is the canonical maintained ELK build. There is no good Python ELK
wrapper as of early 2026. Subprocess overhead for our small circuits is
negligible (tens of milliseconds per render).
