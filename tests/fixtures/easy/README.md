# Easy fixture: simple op-amp filter

Drop in this directory:

- `circuit.net` - the SPICE netlist
- `circuit.asc` - your hand-drawn LTspice schematic (the visual reference)
- `description.md` - what the circuit does, what makes it "easy"

Suggested circuit: single-stage Sallen-Key low-pass filter or similar
under 10 components. No discrete transistors, just resistors, capacitors,
and one op-amp subcircuit.

The easy fixture is the smoke test. If a placer can't render this readably,
something is fundamentally wrong.
