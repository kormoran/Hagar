"""Ora locale e fuso orario."""

from __future__ import annotations

from datetime import datetime


class Clock:

    def now(self) -> dict:
        """Ora locale del sistema, con offset e nome del fuso."""

        moment = datetime.now().astimezone()

        offset = moment.utcoffset()

        if offset is None:
            offset_text = ""
            offset_seconds = 0
        else:
            offset_seconds = int(offset.total_seconds())
            sign = "+" if offset_seconds >= 0 else "-"
            absolute = abs(offset_seconds)
            offset_text = (
                f"{sign}{absolute // 3600:02d}:"
                f"{(absolute % 3600) // 60:02d}"
            )

        tzinfo = moment.tzinfo
        timezone_name = moment.tzname() or ""

        if not timezone_name and tzinfo is not None:
            timezone_name = str(tzinfo)

        return {
            "iso": moment.isoformat(timespec="seconds"),
            "date": moment.date().isoformat(),
            "time": moment.strftime("%H:%M:%S"),
            "timezone": timezone_name,
            "utc_offset": offset_text,
            "utc_offset_seconds": offset_seconds,
            "epoch": int(moment.timestamp()),
        }
