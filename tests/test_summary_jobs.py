"""Test dei job di summary e del chunking."""

from __future__ import annotations

import json

from memory.session import SessionSummarizer
from memory.sqlite_store import SqliteMemoryStore
from memory.summary_jobs import SummaryJobRunner
from memory.summary_jobs import SummaryJobStore


class FakeSummaryLLM:
    def __init__(self):
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        return json.dumps({
            "summary": "riassunto parziale",
            "decisions": [],
        })


def make_memory(tmp_path) -> SqliteMemoryStore:

    memory = SqliteMemoryStore(
        session_id="old-session",
        path=tmp_path / "memory.db",
        max_skill_chars=10000,
    )
    memory.ensure()
    return memory


def add_turns(memory, count=8):
    for index in range(count):
        turn = f"t{index}"
        memory.begin_turn(turn)
        memory.append_turn(
            turn,
            f"Domanda {index} " + ("dettaglio " * 30),
            f"Risposta {index} " + ("contenuto " * 40),
        )
        memory.end_turn()


def test_long_session_is_chunked(tmp_path):

    memory = make_memory(tmp_path)
    add_turns(memory, 8)
    llm = FakeSummaryLLM()

    result = SessionSummarizer(
        memory,
        llm=llm,
        context_window=512,
    ).finish(archive=False)

    assert result["summary"]
    assert len(llm.calls) > 1
    assert result["archived"] == []


def test_summary_job_runner_completes(tmp_path):

    memory = make_memory(tmp_path)
    add_turns(memory, 4)
    memory.archive_session()

    store = SummaryJobStore(memory.database)
    job_id = store.enqueue("old-session", project=None)

    runner = SummaryJobRunner(
        memory,
        llm=FakeSummaryLLM(),
        context_window=512,
    )

    job = runner.run_once()

    assert job is not None
    assert job.id == job_id
    jobs = store.list_jobs()
    assert jobs[0].status == "done"
    assert jobs[0].error is None
    assert store.counts()["done"] == 1
    assert memory.list_summaries()
