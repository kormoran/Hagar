"""Tool di appoggio per catene di ragionamento."""

from __future__ import annotations


class Think:

    def echo(
        self,
        thought: str,
    ) -> str:
        """Restituisce esattamente il testo ricevuto."""

        if not isinstance(thought, str):

            raise ValueError(
                "thought must be a string"
            )

        return thought
