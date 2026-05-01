"""Internal representation: the stable contract between modules.

Every module that crosses a boundary speaks IR. See docs/specs/ir.md.
"""

from wirewright.ir.model import (
    Component,
    Flag,
    Net,
    Orientation,
    Pin,
    Schematic,
    Wire,
)
from wirewright.ir.validate import (
    ValidationError,
    validate,
    validate_placed,
)

__all__ = [
    "Component",
    "Flag",
    "Net",
    "Orientation",
    "Pin",
    "Schematic",
    "ValidationError",
    "Wire",
    "validate",
    "validate_placed",
]
