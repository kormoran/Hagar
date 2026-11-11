"""Errori del DSL Hagar Flow."""

from __future__ import annotations


class FlowError(RuntimeError):

    def __init__(
        self,
        message: str,
        *,
        kind: str = "flow",
        line: int | None = None,
        column: int | None = None,
        hint: str | None = None,
    ) -> None:

        super().__init__(message)
        self.kind = kind
        self.line = line
        self.column = column
        self.hint = hint

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "line": self.line,
            "column": self.column,
            "message": str(self),
            "hint": self.hint,
        }


class FlowValidationError(FlowError):

    def __init__(
        self,
        message: str,
        *,
        line: int | None = None,
        column: int | None = None,
        hint: str | None = None,
    ) -> None:

        super().__init__(
            message,
            kind="validation",
            line=line,
            column=column,
            hint=hint,
        )


class FlowRuntimeError(FlowError):

    def __init__(
        self,
        message: str,
        *,
        line: int | None = None,
        column: int | None = None,
        hint: str | None = None,
    ) -> None:

        super().__init__(
            message,
            kind="runtime",
            line=line,
            column=column,
            hint=hint,
        )
