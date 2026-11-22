"""Shared ToolResult dataclass used by both orchestrator and specialist agents."""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass
class ToolResult:
    success: bool
    data: dict = dataclasses.field(default_factory=dict)
    error: str = ""
