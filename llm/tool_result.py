# llm/tool_result.py
#
# Alias storico: il ToolResult canonico vive in core.tool_result.
# Questo modulo resta solo per non rompere import preesistenti.

from core.tool_result import ToolResult

__all__ = ["ToolResult"]
