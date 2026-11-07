"""Unico proprietario dell'input della console.

La CLI non legge più stdin direttamente: il broker serializza prompt,
conferme ASK, F5/F8 e cancellazione. Su terminali non interattivi ricade
su ``input()`` per restare compatibile con pipe e test.
"""

from __future__ import annotations

import sys
import threading

from dataclasses import dataclass, field
from typing import Any
from typing import Callable


@dataclass
class _LineRequest:
    prompt: str
    event: threading.Event = field(default_factory=threading.Event)
    buffer: list[str] = field(default_factory=list)
    result: str | None = None
    error: BaseException | None = None


@dataclass
class _ConfirmRequest:
    prompt: str
    event: threading.Event = field(default_factory=threading.Event)
    result: bool | None = None
    error: BaseException | None = None


class ConsoleInputBroker:
    """Legge la console da un solo thread e distribuisce le richieste."""

    def __init__(
        self,
        stream=None,
        key_reader: Callable[[], str] | None = None,
    ) -> None:

        self.stream = stream or sys.stdout
        self._key_reader = key_reader
        self._tty = bool(key_reader) or sys.stdin.isatty()
        self._lock = threading.Lock()
        self._request_lock = threading.Lock()
        self._request: _LineRequest | _ConfirmRequest | None = None
        self._closed = False
        self._old_title: str | None = None
        self._thread: threading.Thread | None = None

        if self._tty:
            self._thread = threading.Thread(
                target=self._run,
                name="hagar-console-input",
                daemon=True,
            )
            self._thread.start()

    # ==================================================
    # API
    # ==================================================

    def read_line(self, prompt: str = "") -> str:

        if not self._tty:
            with self._request_lock:
                return input(prompt)

        with self._request_lock:
            request = _LineRequest(prompt=prompt)
            self._submit(request, prompt)
            request.event.wait()

            if request.error is not None:
                raise request.error

            return request.result or ""

    def confirm(
        self,
        prompt: str = "Confermi? (y/N, F5=allow, F8=deny) ",
        timeout: float | None = None,
    ) -> bool:

        if not self._tty:
            with self._request_lock:
                answer = input(prompt)
                return answer.strip().lower() in {
                    "y", "yes", "s", "si", "sì",
                }

        with self._request_lock:
            request = _ConfirmRequest(prompt=prompt)
            self._submit(request, prompt, attention=True)

            if not request.event.wait(timeout):
                self.cancel()
                request.event.wait(1.0)

            if request.error is not None:
                return False

            return bool(request.result)

    def cancel(self) -> None:

        with self._lock:
            request = self._request

        if request is not None:
            request.error = KeyboardInterrupt()
            request.event.set()

        self._restore_title()

    def close(self) -> None:

        self._closed = True
        self.cancel()
        self._restore_title()

        if self._thread is not None:
            self._thread.join(timeout=0.2)

    # ==================================================
    # Reader
    # ==================================================

    def _submit(
        self,
        request: _LineRequest | _ConfirmRequest,
        prompt: str,
        attention: bool = False,
    ) -> None:

        with self._lock:
            self._request = request

        if attention:
            self._set_attention()

        self.stream.write(prompt)
        self.stream.flush()

    def _run(self) -> None:

        while not self._closed:

            try:
                key = (
                    self._key_reader()
                    if self._key_reader is not None
                    else self._read_key()
                )

            except Exception:

                key = ""

            if not key:
                continue

            with self._lock:
                request = self._request

            if request is None:
                continue

            if isinstance(request, _LineRequest):
                self._feed_line(request, key)

            else:
                self._feed_confirm(request, key)

    def _feed_line(
        self,
        request: _LineRequest,
        key: str,
    ) -> None:

        if key in {"\r", "\n"}:

            self.stream.write("\n")
            self.stream.flush()
            request.result = "".join(request.buffer)
            self._finish(request)
            return

        if key in {"\x08", "\x7f"}:

            if request.buffer:
                request.buffer.pop()
                self.stream.write("\b \b")
                self.stream.flush()

            return

        if key == "\x03":
            request.error = KeyboardInterrupt()
            self._finish(request)
            return

        if len(key) == 1 and key.isprintable():

            request.buffer.append(key)
            self.stream.write(key)
            self.stream.flush()

    def _feed_confirm(
        self,
        request: _ConfirmRequest,
        key: str,
    ) -> None:

        if key == "f5":
            request.result = True
            self.stream.write("[F5 allow]\n")
        elif key == "f8":
            request.result = False
            self.stream.write("[F8 deny]\n")
        elif key.lower() in {"y", "s"}:
            request.result = True
            self.stream.write("\n")
        elif key in {"n", "\r", "\n"}:
            request.result = False
            self.stream.write("\n")
        elif key == "\x03":
            request.error = KeyboardInterrupt()
            self.stream.write("\n")
        else:
            return

        self.stream.flush()
        self._finish(request)

    def _finish(
        self,
        request: _LineRequest | _ConfirmRequest,
    ) -> None:

        with self._lock:
            self._request = None

        self._restore_title()
        request.event.set()

    # ==================================================
    # Lettura piattaforma
    # ==================================================

    def _read_key(self) -> str:

        if sys.platform == "win32":
            return self._read_key_windows()

        return self._read_key_posix()

    @staticmethod
    def _read_key_windows() -> str:

        import msvcrt

        char = msvcrt.getwch()

        if char in {"\x00", "\xe0"}:

            code = msvcrt.getwch()

            if code == "\x3f":
                return "f5"
            if code == "\x42":
                return "f8"
            return ""

        if char == "\x1b":
            return "escape"

        return char

    @staticmethod
    def _read_key_posix() -> str:

        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)

        try:
            tty.setcbreak(fd)
            char = sys.stdin.read(1)

            if char != "\x1b":
                return char

            sequence = "\x1b"

            while select.select([fd], [], [], 0.03)[0]:

                sequence += sys.stdin.read(1)

                if sequence in {
                    "\x1b[15~",
                    "\x1b[[E",
                }:
                    return "f5"

                if sequence in {
                    "\x1b[19~",
                    "\x1b[[H",
                }:
                    return "f8"

            return "escape"

        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    # ==================================================
    # Attenzione terminale
    # ==================================================

    def _set_attention(self) -> None:

        if not self._tty:
            return

        self._set_title("Hagar — conferma richiesta (F5 allow / F8 deny)")

        if sys.platform == "win32":

            try:

                import ctypes

                kernel32 = ctypes.windll.kernel32
                user32 = ctypes.windll.user32
                window = kernel32.GetConsoleWindow()

                if window:
                    user32.FlashWindow(window, True)

            except Exception:
                pass

    def _set_title(self, title: str) -> None:

        if not self._tty:
            return

        if sys.platform == "win32":

            try:

                import ctypes

                kernel32 = ctypes.windll.kernel32
                buffer = ctypes.create_unicode_buffer(512)
                kernel32.GetConsoleTitleW(buffer, 512)

                if self._old_title is None:
                    self._old_title = buffer.value

                kernel32.SetConsoleTitleW(title)

            except Exception:
                pass

            return

        try:

            with open("/dev/tty", "w", encoding="utf-8") as tty:

                if self._old_title is None:
                    self._old_title = "Hagar"

                tty.write(f"\033]0;{title}\007")
                tty.flush()

        except OSError:
            pass

    def _restore_title(self) -> None:

        if self._old_title is None:
            return

        title = self._old_title
        self._old_title = None
        self._set_title(title)


def attention_bell() -> None:
    """Segnale di fallback per terminali che ignorano il titolo."""

    try:
        sys.stdout.write("\a")
        sys.stdout.flush()

    except Exception:
        pass
