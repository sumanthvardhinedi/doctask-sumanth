from __future__ import annotations


class ToolFailure(Exception):
    """Machine-readable MCP/tool failure. Never used to report success."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
