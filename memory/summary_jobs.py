"""Job durevoli per il summary delle chat archiviate."""

from __future__ import annotations

import threading

from dataclasses import dataclass
from typing import Any

from memory.database import MemoryDatabase
from memory.session import SessionSummarizer
from memory.store import _iso_timestamp


@dataclass(frozen=True, slots=True)
class SummaryJob:

    id: int
    session_id: str
    project: str | None
    status: str
    attempts: int
    error: str | None


class SummaryJobStore:
    """Coda SQLite: un job per sessione archiviata."""

    def __init__(
        self,
        database: MemoryDatabase,
    ) -> None:

        self.database = database

    def enqueue(
        self,
        session_id: str,
        project: str | None = None,
    ) -> int:

        with self.database.connection() as connection:

            connection.execute(
                """
                INSERT OR IGNORE INTO summary_jobs(
                    session_id, project, status, created_at
                ) VALUES (?, ?, 'pending', ?)
                """,
                (session_id, project, _iso_timestamp()),
            )
            row = connection.execute(
                "SELECT id FROM summary_jobs WHERE session_id = ?",
                (session_id,),
            ).fetchone()

        if row is None:
            raise RuntimeError("cannot enqueue summary job")

        return int(row["id"])

    def claim(self) -> SummaryJob | None:

        with self.database.connection() as connection:

            row = connection.execute(
                """
                SELECT * FROM summary_jobs
                WHERE status = 'pending'
                ORDER BY created_at, id
                LIMIT 1
                """
            ).fetchone()

            if row is None:
                return None

            connection.execute(
                """
                UPDATE summary_jobs
                SET status = 'running',
                    started_at = ?,
                    attempts = attempts + 1,
                    error = NULL
                WHERE id = ?
                """,
                (_iso_timestamp(), row["id"]),
            )

            current = connection.execute(
                "SELECT * FROM summary_jobs WHERE id = ?",
                (row["id"],),
            ).fetchone()

        return self._row(current) if current is not None else None

    def complete(self, job_id: int) -> None:

        with self.database.connection() as connection:

            connection.execute(
                """
                UPDATE summary_jobs
                SET status = 'done',
                    completed_at = ?,
                    error = NULL
                WHERE id = ?
                """,
                (_iso_timestamp(), job_id),
            )

    def fail(self, job_id: int, error: str) -> None:

        with self.database.connection() as connection:

            connection.execute(
                """
                UPDATE summary_jobs
                SET status = 'failed',
                    completed_at = ?,
                    error = ?
                WHERE id = ?
                """,
                (_iso_timestamp(), error[:2000], job_id),
            )

    def requeue_running(self) -> int:

        with self.database.connection() as connection:

            cursor = connection.execute(
                """
                UPDATE summary_jobs
                SET status = 'pending',
                    started_at = NULL
                WHERE status = 'running'
                """
            )

        return int(cursor.rowcount or 0)

    def list_jobs(self, limit: int = 100) -> list[SummaryJob]:

        with self.database.connection() as connection:

            rows = connection.execute(
                """
                SELECT * FROM summary_jobs
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()

        return [self._row(row) for row in rows]

    def counts(self) -> dict[str, int]:

        counts = {
            "pending": 0,
            "running": 0,
            "done": 0,
            "failed": 0,
        }

        with self.database.connection() as connection:

            rows = connection.execute(
                """
                SELECT status, COUNT(*) AS total
                FROM summary_jobs
                GROUP BY status
                """
            ).fetchall()

        for row in rows:

            if row["status"] in counts:
                counts[row["status"]] = int(row["total"])

        return counts

    @staticmethod
    def _row(row: Any) -> SummaryJob:

        return SummaryJob(
            id=int(row["id"]),
            session_id=str(row["session_id"]),
            project=(
                str(row["project"])
                if row["project"] is not None
                else None
            ),
            status=str(row["status"]),
            attempts=int(row["attempts"]),
            error=(
                str(row["error"])
                if row["error"] is not None
                else None
            ),
        )


class SummaryJobRunner:
    """Worker daemon che consuma i job di summary."""

    def __init__(
        self,
        memory: Any,
        *,
        llm: Any = None,
        projects: Any = None,
        context_window: int | None = None,
        summary_max_chars: int = 4000,
        audit: Any = None,
        poll_seconds: float = 1.0,
    ) -> None:

        self.memory = memory
        self.store = SummaryJobStore(memory.database)
        self.llm = llm
        self.projects = projects
        self.context_window = (
            int(context_window)
            if context_window
            else 8192
        )
        self.summary_max_chars = int(summary_max_chars)
        self.audit = audit
        self.poll_seconds = max(0.1, float(poll_seconds))
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:

        if self._thread is not None:
            return

        self._thread = threading.Thread(
            target=self._run,
            name="hagar-summary",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:

        self._stop.set()
        self._wake.set()

        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def enqueue(
        self,
        session_id: str,
        project: str | None = None,
    ) -> int:

        job_id = self.store.enqueue(session_id, project)
        self._wake.set()
        return job_id

    def run_once(self) -> SummaryJob | None:
        """Esegue un job; utile per test e manutenzione."""

        job = self.store.claim()

        if job is None:
            return None

        try:
            self._process(job)
            self.store.complete(job.id)

        except Exception as exc:

            self.store.fail(job.id, str(exc))

        return job

    def _run(self) -> None:

        self.store.requeue_running()

        while not self._stop.is_set():

            job = self.store.claim()

            if job is None:
                self._wake.wait(self.poll_seconds)
                self._wake.clear()
                continue

            try:
                self._process(job)
                self.store.complete(job.id)

            except Exception as exc:

                self.store.fail(job.id, str(exc))

    def _process(self, job: SummaryJob) -> None:

        summarizer = SessionSummarizer(
            self.memory,
            projects=self.projects,
            project_id=job.project,
            llm=self.llm,
            audit=self.audit,
            input_func=lambda _prompt: "",
            output_func=lambda _line: None,
            summary_max_chars=self.summary_max_chars,
            session_id=job.session_id,
            context_window=self.context_window,
        )

        summarizer.finish(archive=False)
