"""Analog idiom pattern matcher and template library.

See ``docs/specs/pattern-library.md`` for the grammar.
"""

from wirewright.patterns.matcher import PatternMatch, find_matches
from wirewright.patterns.template import (
    Template,
    TemplateError,
    load_default_library,
    load_template,
)

__all__ = [
    "PatternMatch",
    "Template",
    "TemplateError",
    "find_matches",
    "load_default_library",
    "load_template",
]
