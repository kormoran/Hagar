"""Test dell'export Markdown dal database SQLite."""

from __future__ import annotations

from memory.export import MarkdownExportError
from memory.export import MarkdownExporter
from memory.import_markdown import MarkdownImporter
from memory.sqlite_projects import SqliteProjectStore
from memory.sqlite_store import SqliteMemoryStore


def make_data(tmp_path):
    memory = SqliteMemoryStore(
        session_id="s1",
        path=tmp_path / "memory.db",
    )
    memory.ensure()
    memory.append_turn("t1", "domanda", "risposta")
    memory.create_skill(
        "Nota importante",
        "contenuto della nota",
        tags=["test"],
    )
    memory.write_summary("summary della sessione")

    projects = SqliteProjectStore(memory.database)
    projects.ensure()
    project = projects.create_project("Hagar")
    projects.create_decision(
        project.id,
        "Usare SQLite",
        "SQLite è la fonte primaria.",
        rationale="transazioni",
    )

    return memory, projects


def test_export_creates_markdown_tree(tmp_path):
    memory, projects = make_data(tmp_path)
    target = tmp_path / "export"

    result = MarkdownExporter(
        memory,
        projects,
        target,
    ).export()

    base = target / "Hagar"
    assert result["files"] >= 5
    assert list((base / "chat").glob("*-s1.md"))
    assert (base / "skills" / "nota-importante.md").is_file()
    assert list((base / "summaries").glob("*-s1-*.md"))
    assert (base / "projects" / "hagar" / "index.md").is_file()
    assert list(
        (base / "projects" / "hagar" / "decisions").glob("*.md")
    )

    chat = next((base / "chat").glob("*-s1.md")).read_text(
        encoding="utf-8"
    )
    assert "session: s1" in chat
    assert "**Utente:** domanda" in chat


def test_export_refuses_non_empty_target_without_force(tmp_path):
    memory, projects = make_data(tmp_path)
    target = tmp_path / "export"
    exporter = MarkdownExporter(memory, projects, target)

    exporter.export()

    try:
        exporter.export()

    except MarkdownExportError as exc:
        assert "--force" in str(exc)

    else:
        raise AssertionError("expected non-empty target error")


def test_export_force_overwrites_generated_files(tmp_path):
    memory, projects = make_data(tmp_path)
    target = tmp_path / "export"
    exporter = MarkdownExporter(memory, projects, target)

    exporter.export()
    result = exporter.export(force=True)

    assert result["files"] >= 5


def test_import_markdown_into_sqlite(tmp_path):
    memory, projects = make_data(tmp_path)
    target = tmp_path / "export"
    MarkdownExporter(memory, projects, target).export()

    imported = SqliteMemoryStore(
        session_id="other",
        path=tmp_path / "new.db",
    )
    imported.ensure()

    counts = MarkdownImporter(
        imported.database,
        target,
    ).run()

    assert counts["turns"] == 1
    assert counts["skills"] == 1
    assert counts["projects"] == 1
    assert counts["decisions"] == 1
    assert imported.read_session("s1")[0]["question"] == "domanda"
    assert imported.list_skills()[0].id == "nota-importante"
