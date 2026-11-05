"""Data corrente nel calendario giuliano o islamico.

Le conversioni sono aritmetiche e prolepticiche. Il calendario islamico
usato è quello tabellare (Kuwaiti algorithm): può differire di un giorno
dai calendari basati sull'osservazione o su Umm al-Qura.
"""

from __future__ import annotations

from datetime import date as _date
from datetime import datetime


JULIAN_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

ISLAMIC_MONTHS = (
    "Muharram",
    "Safar",
    "Rabi' al-awwal",
    "Rabi' al-thani",
    "Jumada al-awwal",
    "Jumada al-thani",
    "Rajab",
    "Sha'ban",
    "Ramadan",
    "Shawwal",
    "Dhu al-Qi'dah",
    "Dhu al-Hijjah",
)

WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


class Calendar:

    ALIASES = {
        "julian": "julian",
        "giuliano": "julian",
        "islamic": "islamic",
        "islamico": "islamic",
        "hijri": "islamic",
        "hijriah": "islamic",
        "muslim": "islamic",
    }

    def convert(
        self,
        calendar: str,
        date: str = "",
    ) -> dict:
        """Converte la data gregoriana nel calendario richiesto."""

        name = (
            calendar.strip().lower()
            if isinstance(calendar, str)
            else ""
        )

        target = self.ALIASES.get(name)

        if target is None:

            return {
                "success": False,
                "error": (
                    "calendar must be 'julian' or 'islamic'"
                ),
            }

        try:

            gregorian = self._parse_date(date)

        except ValueError as exc:

            return {
                "success": False,
                "error": str(exc),
            }

        jdn = self._gregorian_to_jdn(gregorian)

        if target == "julian":

            year, month, day = self._julian_from_jdn(jdn)
            month_name = JULIAN_MONTHS[month - 1]
            method = "proleptic Julian calendar"

        else:

            year, month, day = self._islamic_from_jdn(jdn)
            month_name = ISLAMIC_MONTHS[month - 1]
            method = "tabular Islamic calendar (Kuwaiti algorithm)"

        return {
            "success": True,
            "calendar": target,
            "gregorian": gregorian.isoformat(),
            "day": day,
            "month": month,
            "year": year,
            "month_name": month_name,
            "weekday": WEEKDAYS[gregorian.weekday()],
            "method": method,
        }

    @staticmethod
    def _parse_date(
        value: str,
    ) -> _date:

        if not value or not str(value).strip():
            return datetime.now().astimezone().date()

        return _date.fromisoformat(str(value).strip())

    @staticmethod
    def _gregorian_to_jdn(
        value: _date,
    ) -> int:
        """Julian Day Number dal calendario gregoriano."""

        a = (14 - value.month) // 12
        y = value.year + 4800 - a
        m = value.month + 12 * a - 3

        return (
            value.day
            + (153 * m + 2) // 5
            + 365 * y
            + y // 4
            - y // 100
            + y // 400
            - 32045
        )

    @staticmethod
    def _julian_from_jdn(
        jdn: int,
    ) -> tuple[int, int, int]:
        """Data del calendario giuliano da un JDN."""

        c = jdn + 32082
        d = (4 * c + 3) // 1461
        e = c - (1461 * d) // 4
        m = (5 * e + 2) // 153

        day = e - (153 * m + 2) // 5 + 1
        month = m + 3 - 12 * (m // 10)
        year = d - 4800 + (m // 10)

        return year, month, day

    @staticmethod
    def _islamic_from_jdn(
        jdn: int,
    ) -> tuple[int, int, int]:
        """Data islamica tabellare da un JDN."""

        l = jdn - 1948440 + 10632
        n = (l - 1) // 10631
        l = l - 10631 * n + 354

        j = (
            ((10985 - l) // 5316)
            * ((50 * l) // 17719)
            + (l // 5670)
            * ((43 * l) // 15238)
        )

        l = (
            l
            - ((30 - j) // 15)
            * ((17719 * j) // 50)
            - (j // 16)
            * ((15238 * j) // 43)
            + 29
        )

        month = (24 * l) // 709
        day = l - (709 * month) // 24
        year = 30 * n + j - 30

        return year, month, day
