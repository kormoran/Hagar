"""Test dell'audit log strutturato."""

from __future__ import annotations

import json

from pathlib import Path

from core.audit import (
    AuditLog,
    read_entries,
    utc_now,
    verify_chain,
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


# =====================================================
# Catena di hash
# =====================================================


def test_entries_form_a_hash_chain(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)

    log.record("a")
    log.record("b")

    entries = read_entries(path)

    assert entries[0]["prev"] is None
    assert entries[1]["prev"] == entries[0]["hash"]
    assert verify_chain(entries) is True


def test_chain_continues_across_instances(tmp_path):
    path = tmp_path / "audit.jsonl"

    AuditLog(path).record("a")
    AuditLog(path).record("b")

    entries = read_entries(path)

    assert entries[1]["prev"] == entries[0]["hash"]
    assert verify_chain(entries) is True


def test_verify_chain_detects_tampering(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)

    log.record("a")
    log.record("b")

    entries = read_entries(path)
    entries[0]["event"] = "altro"

    assert verify_chain(entries) is False


def test_verify_chain_detects_broken_link(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)

    log.record("a")
    log.record("b")

    entries = read_entries(path)
    entries[1]["prev"] = "falso"

    assert verify_chain(entries) is False


def test_disabled_log_entries_still_chain(tmp_path):
    log = AuditLog(
        tmp_path / "audit.jsonl",
        enabled=False,
    )

    first = log.record("a")
    second = log.record("b")

    assert first["hash"] != second["hash"]
    assert second["prev"] == first["hash"]


# =====================================================
# Rotazione e redazione
# =====================================================


def test_rotation_creates_single_backup(tmp_path):
    path = tmp_path / "audit.jsonl"

    log = AuditLog(path, max_bytes=1)

    log.record("a")
    log.record("b")

    backups = sorted(
        tmp_path.glob("audit.jsonl.*")
    )

    assert len(backups) == 1

    backup = backups[0]

    current = read_entries(path)
    previous = read_entries(backup)

    assert [entry["event"] for entry in current] == ["b"]
    assert [entry["event"] for entry in previous] == ["a"]

    assert current[0]["prev"] == previous[-1]["hash"]
    assert verify_chain(previous) is True
    assert verify_chain(current) is True


def test_rotation_keeps_last_files(tmp_path):
    path = tmp_path / "audit.jsonl"

    log = AuditLog(
        path,
        max_bytes=1,
        max_files=3,
    )

    for event in "abcde":
        log.record(event)

    files = sorted(
        tmp_path.glob("audit.jsonl*")
    )

    assert len(files) == 3

    events: set[str] = set()

    for file in files:
        events.update(
            entry["event"]
            for entry in read_entries(file)
        )

    assert "e" in events
    assert "c" in events
    assert "a" not in events
    assert "b" not in events


def test_chain_continues_from_backup(tmp_path):
    path = tmp_path / "audit.jsonl"

    AuditLog(path, max_bytes=1).record("a")
    AuditLog(path, max_bytes=1).record("b")

    backup = sorted(
        tmp_path.glob("audit.jsonl.*")
    )[-1]

    backup_hash = read_entries(backup)[-1]["hash"]

    path.unlink()

    restarted = AuditLog(path)

    entry = restarted.record("c")

    assert entry["prev"] == backup_hash


def test_rotation_can_be_disabled(tmp_path):
    path = tmp_path / "audit.jsonl"

    log = AuditLog(path, max_bytes=0)

    log.record("a")
    log.record("b")

    assert not list(
        tmp_path.glob("audit.jsonl.*")
    )
    assert len(read_entries(path)) == 2


def test_include_outputs_flag(tmp_path):
    log = AuditLog(
        tmp_path / "audit.jsonl",
        include_outputs=False,
    )

    assert log.include_outputs is False
