"""Test di artifact store e mailbox interni."""

from __future__ import annotations

from core.agent_data import ArtifactStore
from core.agent_data import Mailbox
from core.filesystem import DirectoryPermissions
from core.filesystem import FileSystemSandbox


def test_text_artifact_read_is_bounded():
    store = ArtifactStore()

    try:
        ref = store.put_text(
            "contenuto",
            owner="a-1",
        )
        result = store.read(
            ref.artifact_id,
            offset=0,
            length=4,
        )

        assert result["text"] == "cont"
        assert result["truncated"] is True
        assert result["sha256"] == ref.sha256

    finally:
        store.cleanup()


def test_binary_artifact_is_base64():
    store = ArtifactStore()

    try:
        ref = store._put_bytes(
            b"\x00\x01\x02",
            kind="binary",
            mime_type="application/octet-stream",
            owner="a-1",
        )
        result = store.read(ref.artifact_id)

        assert result["encoding"] == "base64"
        assert result["data_b64"] == "AAEC"

    finally:
        store.cleanup()


def test_mailbox_inbox_and_ack():
    mailbox = Mailbox()

    message = mailbox.send(
        sender="a-1",
        recipient="parent",
        text="risultato",
        artifacts=["art-1"],
    )

    inbox = mailbox.inbox("parent")

    assert len(inbox) == 1
    assert inbox[0].message_id == message.message_id
    assert inbox[0].artifacts == ("art-1",)
    assert mailbox.ack("parent", message.message_id) is True
    assert mailbox.inbox("parent")[0].acked is True


def test_mailbox_is_per_recipient():
    mailbox = Mailbox()

    mailbox.send(
        sender="a-1",
        recipient="parent",
        text="per il padre",
    )

    assert mailbox.inbox("parent")
    assert mailbox.inbox("a-2") == []


def test_artifact_save_to_writes_whole_file(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    filesystem = FileSystemSandbox(
        roots={
            root: DirectoryPermissions(
                read=True,
                write=True,
                create=True,
            )
        },
        current_directory=root,
        aliases={"workspace": root},
    )
    store = ArtifactStore()

    try:
        ref = store.put_text(
            "contenuto completo",
            owner="a-1",
        )
        result = store.save_to(
            ref.artifact_id,
            filesystem,
            "/home/ai/workspace/report.txt",
        )

        assert result["size"] == ref.size
        assert (root / "report.txt").read_text(
            encoding="utf-8"
        ) == "contenuto completo"

        try:
            store.save_to(
                ref.artifact_id,
                filesystem,
                "/home/ai/workspace/report.txt",
            )

        except FileExistsError:
            pass

        else:
            raise AssertionError("overwrite should be refused")

    finally:
        store.cleanup()
