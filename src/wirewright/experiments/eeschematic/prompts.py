"""Prompt text for the VCoT loop.

Portions lifted verbatim from
https://github.com/eelab-dev/EEschematic (MIT License, Copyright (c)
2025 EElab.dev — full text at ``LICENSE_EESCHEMATIC`` in this
directory).

Local additions describe wirewright-specific conventions: the component
list is given by ref:symbol, VDD/GND are advisory, and the agent handles
all wiring post-placement.
"""

from __future__ import annotations

from wirewright.ir.model import Schematic

# Source: EEschematic ``netlist_to_schema/place_prompt.txt`` (MIT), with
# wirewright-specific amendments at the end.
PLACE_SYSTEM = """\
You are an expert for analog circuits design. Your task is to translate \
a circuit netlist into a structured JSON schema representing component \
positions on a schematic grid.

The x, y in the JSON schema represent positions on a drawable grid \
with x in [-60, 60] and y in [-60, 60]. Positive y is UP.

Return JSON with this structure:

{
  "componentInstances": [
    {
      "typeName": "<string>",
      "name": "<component ref>",
      "value": "<optional>",
      "origin": {"x": <int>, "y": <int>},
      "rotation": "0" | "90" | "180" | "270",
      "flip": "none" | "horizontal" | "vertical"
    },
    ...
  ]
}

Placement rules:
1. Identify subcircuits (current mirrors, differential pairs, cascodes).
2. VDD at top, GND at bottom (as positional guidance only — the host
   handles power/ground rails separately; you do not need to emit VDD
   or GND componentInstances).
3. Keep symmetric subcircuits side by side.
4. Minimum distance between components: 20 grid units.
5. Place sources near the components they drive, aligned horizontally.
6. Keep the schematic compact and readable.

Return ONLY valid JSON. No prose, no code fences, no explanation.
Output the token "DONE" on its own line after the JSON if you are \
satisfied the schematic is readable; otherwise keep refining in \
subsequent turns.
"""

PLACE_USER_INITIAL = """\
Netlist:
{netlist}

Components to place (ref:symbol):
{ref_symbol_list}

Nets (* = power/ground, handled by host):
{net_list}

Produce the initial componentInstances JSON for this circuit.
"""

PLACE_USER_CRITIQUE = """\
Netlist (unchanged):
{netlist}

Current placement JSON:
{current_json}

Current render is attached as an image.

Critique the placement — look at overlaps, alignment, symmetry, and \
wire routing visible in the image. Return an improved \
componentInstances JSON. If the current placement is already readable, \
output the same JSON and append "DONE" on its own line after it.
"""


def format_ref_symbol_list(sch: Schematic) -> str:
    return "\n".join(f"  {c.ref}:{c.symbol}" for c in sch.components)


def format_net_list(sch: Schematic) -> str:
    lines = []
    for n in sch.nets:
        marker = "*" if (n.is_power or n.is_ground or n.name == "0") else " "
        lines.append(f"  {marker} {n.name}")
    return "\n".join(lines)
