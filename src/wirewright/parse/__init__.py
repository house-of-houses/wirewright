"""Netlist and .asc parsing into IR."""

from wirewright.parse.spice import ParseError, parse_spice_file, parse_spice_text

__all__ = ["ParseError", "parse_spice_file", "parse_spice_text"]
