#!/usr/bin/env node
// Tiny bridge: read an ELK graph JSON from stdin, run layout, write result to stdout.
// Used by src/wirewright/placers/elk.py via subprocess.
//
// Phase 3: this is the working stub. The Python adapter on the other side is
// the part that does the IR<->ELK translation work.

import ELK from 'elkjs';
import { stdin } from 'process';

const elk = new ELK();

let buf = '';
for await (const chunk of stdin) buf += chunk;

let graph;
try {
  graph = JSON.parse(buf);
} catch (e) {
  process.stderr.write(`elk-bridge: invalid JSON on stdin: ${e.message}\n`);
  process.exit(2);
}

const defaultLayoutOptions = {
  'elk.algorithm': 'layered',
  'elk.direction': 'RIGHT',
  'elk.edgeRouting': 'ORTHOGONAL',
  'elk.portConstraints': 'FIXED_SIDE',
  'elk.layered.nodePlacement.strategy': 'BRANDES_KOEPF',
  'elk.spacing.nodeNode': '40',
  'elk.layered.spacing.nodeNodeBetweenLayers': '60',
};

try {
  const result = await elk.layout(graph, {
    layoutOptions: { ...defaultLayoutOptions, ...(graph.layoutOptions || {}) },
  });
  process.stdout.write(JSON.stringify(result));
} catch (e) {
  process.stderr.write(`elk-bridge: layout failed: ${e.message}\n`);
  process.exit(3);
}
