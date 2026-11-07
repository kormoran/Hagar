"""Test del broker di input della console."""

from __future__ import annotations

import io
import queue
import threading

from core.input_broker import ConsoleInputBroker


class Keys:

    def __init__(self):
        self.queue = queue.Queue()

    def get(self):
        return self.queue.get()

    def send(self, *keys):
        for key in keys:
            self.queue.put(key)


def start_broker():
    keys = Keys()
    broker = ConsoleInputBroker(
        stream=io.StringIO(),
        key_reader=keys.get,
    )
    return broker, keys


def test_read_line_routes_characters():
    broker, keys = start_broker()
    result = []

    thread = threading.Thread(
        target=lambda: result.append(
            broker.read_line("> ")
        )
    )
    thread.start()
    keys.send("h", "i", "\r")
    thread.join(timeout=2)

    assert result == ["hi"]
    broker.close()


def test_confirm_accepts_f5_and_f8():
    broker, keys = start_broker()
    approved = []

    thread = threading.Thread(
        target=lambda: approved.append(broker.confirm())
    )
    thread.start()
    keys.send("f5")
    thread.join(timeout=2)

    denied = []

    thread = threading.Thread(
        target=lambda: denied.append(broker.confirm())
    )
    thread.start()
    keys.send("f8")
    thread.join(timeout=2)

    assert approved == [True]
    assert denied == [False]
    broker.close()


def test_confirm_accepts_typed_yes_and_no():
    broker, keys = start_broker()
    approved = []

    thread = threading.Thread(
        target=lambda: approved.append(broker.confirm())
    )
    thread.start()
    keys.send("y")
    thread.join(timeout=2)

    denied = []

    thread = threading.Thread(
        target=lambda: denied.append(broker.confirm())
    )
    thread.start()
    keys.send("n")
    thread.join(timeout=2)

    assert approved == [True]
    assert denied == [False]
    broker.close()
