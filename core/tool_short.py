"""Descrizioni brevi dei tool per i modelli piccoli."""

from __future__ import annotations

from typing import Any


# nome tool -> (descrizione breve, {parametro: descrizione breve})
SHORT_TOOLS: dict[str, tuple[str, dict[str, str]]] = {
    "filesystem.read_file": (
        "Read a UTF-8 file.",
        {"path": "File path."},
    ),
    "filesystem.write_file": (
        "Write an existing file after reading it.",
        {"path": "File path.", "content": "New content."},
    ),
    "filesystem.edit_file": (
        "Replace literal text in an existing file.",
        {
            "path": "File path.",
            "old_string": "Text to replace.",
            "new_string": "Replacement.",
            "replace_all": "Replace every match.",
        },
    ),
    "filesystem.create_file": (
        "Create a new file.",
        {"path": "File path.", "content": "File content."},
    ),
    "filesystem.mkdir": (
        "Create a directory.",
        {"path": "Directory path."},
    ),
    "filesystem.chdir": (
        "Change the current directory.",
        {"path": "Directory path."},
    ),
    "filesystem.list_dir": (
        "List a directory, with pagination.",
        {
            "path": "Directory path.",
            "offset": "Start offset.",
            "limit": "Maximum entries.",
        },
    ),
    "filesystem.read_chunk": (
        "Read part of a UTF-8 file.",
        {
            "path": "File path.",
            "offset": "Byte offset.",
            "limit": "Maximum bytes.",
        },
    ),
    "filesystem.rename": (
        "Rename or move a file.",
        {"source": "Source path.", "target": "Target path."},
    ),
    "filesystem.copy_file": (
        "Copy a file.",
        {"source": "Source path.", "target": "Target path."},
    ),
    "filesystem.delete_file": (
        "Delete a file.",
        {"path": "File path."},
    ),
    "filesystem.search": (
        "Search paths with a glob pattern.",
        {
            "pattern": "Glob pattern.",
            "path": "Start directory.",
            "offset": "Start offset.",
            "limit": "Maximum results.",
        },
    ),
    "filesystem.free_space": (
        "Return free disk space.",
        {"path": "Path to inspect."},
    ),
    "filesystem.stat": (
        "Return path metadata.",
        {"path": "Path to inspect."},
    ),
    "aish.exec": (
        "Run a small sandboxed command language.",
        {"script": "Command text."},
    ),
    "text.transform": (
        "Apply a read-only text operation.",
        {
            "path": "Input file.",
            "text": "Inline input.",
            "operation": "Operation name.",
            "pattern": "Pattern or search text.",
            "replacement": "Replacement text.",
        },
    ),
    "vision.open": (
        "Attach a PNG, JPEG or WebP image.",
        {"path": "Image path."},
    ),
    "clock.now": (
        "Return local date and time.",
        {},
    ),
    "calendar.date": (
        "Return the date in a calendar.",
        {"calendar": "julian or islamic."},
    ),
    "think.echo": (
        "Echo an intermediate thought.",
        {"thought": "Thought text."},
    ),
    "text.diff": (
        "Return a unified diff.",
        {"left": "Original text.", "right": "Changed text."},
    ),
    "url.parse": (
        "Split a URL into components.",
        {"url": "URL to parse."},
    ),
    "statistics.compute": (
        "Compute statistics for values.",
        {"values": "Number list."},
    ),
    "calculator.evaluate": (
        "Evaluate a math expression.",
        {"expression": "Expression."},
    ),
    "units.convert": (
        "Convert measurement units.",
        {
            "value": "Value.",
            "from_unit": "Source unit.",
            "to_unit": "Target unit.",
        },
    ),
    "feed.read": (
        "Read an RSS or Atom feed.",
        {"url": "Feed URL."},
    ),
    "sql.file.drivers": (
        "List SQL and ODBC drivers.",
        {},
    ),
    "sql.file.schema": (
        "Inspect a database schema.",
        {"path": "Database path.", "table": "Optional table."},
    ),
    "sql.file.query": (
        "Run a read-only SQL query.",
        {
            "path": "Database path.",
            "sql": "SELECT, WITH or EXPLAIN.",
            "driver": "Driver name.",
            "max_rows": "Maximum rows.",
            "timeout_seconds": "Query timeout.",
        },
    ),
    "agent.spawn": (
        "Start a read-only subagent.",
        {
            "task": "Focused task.",
            "reason": "Why a subagent.",
            "context": "Optional context.",
            "inputs": "Input files.",
        },
    ),
    "agent.status": (
        "Return subagent status.",
        {"agent_id": "Subagent id."},
    ),
    "agent.wait": (
        "Wait for a subagent.",
        {"agent_id": "Subagent id.", "timeout": "Wait seconds."},
    ),
    "agent.result": (
        "Return a subagent result.",
        {"agent_id": "Subagent id."},
    ),
    "agent.cancel": (
        "Cancel a subagent.",
        {"agent_id": "Subagent id."},
    ),
    "agent.run": (
        "Spawn and wait for a subagent.",
        {
            "task": "Focused task.",
            "reason": "Why a subagent.",
            "context": "Optional context.",
            "inputs": "Input files.",
        },
    ),
    "artifact.read": (
        "Read an artifact chunk.",
        {
            "artifact_id": "Artifact id.",
            "offset": "Start offset.",
            "limit": "Maximum bytes.",
        },
    ),
    "artifact.list": (
        "List session artifacts.",
        {},
    ),
    "artifact.save_to": (
        "Copy an artifact into the sandbox.",
        {"artifact_id": "Artifact id.", "path": "Target path."},
    ),
    "mailbox.inbox": (
        "List subagent messages.",
        {},
    ),
    "mailbox.read": (
        "Read a mailbox message.",
        {"message_id": "Message id."},
    ),
    "mailbox.ack": (
        "Acknowledge a mailbox message.",
        {"message_id": "Message id."},
    ),
    "decision.choose": (
        "Choose one label from a fixed set.",
        {
            "question": "Decision question.",
            "labels": "Allowed labels.",
            "context": "Optional context.",
        },
    ),
}


def short_description(
    name: str,
    fallback: str,
) -> str:

    item = SHORT_TOOLS.get(name)

    if item is not None:
        return item[0]

    return _first_sentence(fallback, 120)


def short_parameter(
    tool_name: str,
    parameter_name: str,
    fallback: str,
) -> str:

    item = SHORT_TOOLS.get(tool_name)

    if item is not None:
        value = item[1].get(parameter_name)

        if value:
            return value

    return _first_sentence(fallback, 60)


def _first_sentence(value: Any, limit: int) -> str:

    text = " ".join(str(value or "").split())

    if not text:
        return ""

    for mark in (". ", ".\n", ";"):
        index = text.find(mark)

        if 0 < index < limit:
            text = text[: index + 1]
            break

    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"

    return text
