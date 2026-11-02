"""Test dell'audit log strutturato."""

from __future__ import annotations

import json

from pathlib import Path

from core.audit import (
    AuditLog,
    read_entries,
    utc_now,
)


def test_utc_now_is_iso8601():
    value = utc_now()

    assert "T" in value
    assert value.endswith("+00:00")


def test_record_writes_jsonl(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)

    entry = log.record(
        "turn.start",
        question="ciao",
        n=1,
    )

    lines = path.read_text(
        encoding="utf-8"
    ).splitlines()

    assert len(lines) == 1

    data = json.loads(lines[0])

    assert data["event"] == "turn.start"
    assert data["question"] == "ciao"
    assert data["n"] == 1
    assert data["session"] == log.session_id
    assert data["ts"] == entry["ts"]


def test_records_are_appended(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)

    log.record("a")
    log.record("b")

    entries = read_entries(path)

    assert [entry["event"] for entry in entries] == [
        "a",
        "b",
    ]


def test_read_missing_file_returns_empty(tmp_path):
    assert read_entries(tmp_path / "missing.jsonl") == []


def test_parent_directories_are_created(tmp_path):
    path = tmp_path / "logs" / "deep" / "audit.jsonl"

    AuditLog(path).record("start")

    assert path.exists()


def test_long_strings_are_truncated(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path, max_field_chars=10)

    log.record("event", text="x" * 50)

    text = read_entries(path)[0]["text"]

    assert text.startswith("x" * 10)
    assert "truncated 40 chars" in text


def test_nested_values_are_truncated(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path, max_field_chars=10)

    log.record(
        "event",
        payload={
            "note": "y" * 20,
            "items": ["z" * 20],
        },
    )

    payload = read_entries(path)[0]["payload"]

    assert payload["note"].startswith("y" * 10)
    assert payload["items"][0].startswith("z" * 10)


def test_values_are_made_serializable(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)

    marker = object()

    log.record(
        "event",
        path=Path("C:/tmp/file.txt"),
        args={"nested": [1, 2]},
        marker=marker,
    )

    data = read_entries(path)[0]

    assert data["path"] == str(Path("C:/tmp/file.txt"))
    assert data["args"] == {"nested": [1, 2]}
    assert data["marker"] == repr(marker)


def test_disabled_log_writes_nothing(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path, enabled=False)

    entry = log.record("event", a=1)

    assert not path.exists()
    assert entry["a"] == 1
    assert entry["event"] == "event"


def test_write_failure_is_reported_once(
    tmp_path,
    capsys,
):
    blocked = tmp_path / "blocked"
    blocked.write_text("sono un file", encoding="utf-8")

    log = AuditLog(blocked / "audit.jsonl")

    # Non deve sollevare e non deve ripetere il warning.
    log.record("a")
    log.record("b")

    stderr = capsys.readouterr().err

    assert stderr.count("Audit log write failed") == 1


def test_sessions_are_unique(tmp_path):
    first = AuditLog(tmp_path / "a.jsonl")
    second = AuditLog(tmp_path / "b.jsonl")

    assert first.session_id != second.session_id


def test_utf8_is_preserved(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)

    log.record("event", text="città àèìòù")

    raw = path.read_text(encoding="utf-8")

    assert "città àèìòù" in raw
