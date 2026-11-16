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
1. You MUST emit one componentInstance for every ref in the "Components
   to place" list below — including voltage sources named VDD, VSS,
   VCC, etc. The host does NOT invent components. If a ref is in the
   list, place it, even if its name resembles a power rail.
2. Separately, do NOT invent standalone VDD/GND decoration instances
   that are not in the ref list — the host renders power/ground rails
   from net metadata, so free-floating VDD/GND placeholders only clutter
   the schematic.
3. Identify subcircuits (current mirrors, differential pairs, cascodes).
4. Put refs that act as positive supplies near the top and refs that
   act as negative supplies / ground near the bottom.
5. Keep symmetric subcircuits side by side.
6. Minimum distance between components: 20 grid units.
7. Place current/voltage sources near the components they drive,
   aligned horizontally.
8. Keep the schematic compact and readable.

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
