from __future__ import annotations

import math


class UnitConverter:

    _CONVERSIONS = {

        #
        # Length
        #
        "mm": 0.001,
        "cm": 0.01,
        "m": 1.0,
        "km": 1000.0,

        #
        # Weight
        #
        "mg": 0.000001,
        "g": 0.001,
        "kg": 1.0,
        "t": 1000.0,

        #
        # Time
        #
        "ms": 0.001,
        "s": 1.0,
        "min": 60.0,
        "hour": 3600.0,
        "day": 86400.0,

        #
        # Data size
        # Binary base (1024)
        #
        "b": 1.0,
        "kb": 1024.0,
        "mb": 1024.0 ** 2,
        "gb": 1024.0 ** 3,
        "tb": 1024.0 ** 4,
    }

    _DIMENSIONS = {

        #
        # Length
        #
        "mm": "length",
        "cm": "length",
        "m": "length",
        "km": "length",

        #
        # Weight
        #
        "mg": "weight",
        "g": "weight",
        "kg": "weight",
        "t": "weight",

        #
        # Time
        #
        "ms": "time",
        "s": "time",
        "min": "time",
        "hour": "time",
        "day": "time",

        #
        # Temperature
        #
        "c": "temperature",
        "f": "temperature",
        "k": "temperature",

        #
        # Angle
        #
        "deg": "angle",
        "rad": "angle",

        #
        # Data size
        #
        "b": "data_size",
        "kb": "data_size",
        "mb": "data_size",
        "gb": "data_size",
        "tb": "data_size",
    }

    _ALIASES = {

        #
        # Length
        #
        "meter": "m",
        "meters": "m",
        "metre": "m",
        "metres": "m",

        "kilometer": "km",
        "kilometers": "km",
        "kilometre": "km",
        "kilometres": "km",

        "centimeter": "cm",
        "centimeters": "cm",

        "millimeter": "mm",
        "millimeters": "mm",

        #
        # Weight
        #
        "gram": "g",
        "grams": "g",

        "kilogram": "kg",
        "kilograms": "kg",

        "milligram": "mg",
        "milligrams": "mg",

        "ton": "t",
        "tons": "t",
        "tonne": "t",
        "tonnes": "t",

        #
        # Time
        #
        "sec": "s",
        "second": "s",
        "seconds": "s",

        "minute": "min",
        "minutes": "min",

        "h": "hour",
        "hr": "hour",
        "hrs": "hour",
        "hours": "hour",

        "days": "day",

        #
        # Temperature
        #
        "celsius": "c",
        "centigrade": "c",

        "fahrenheit": "f",

        "kelvin": "k",

        #
        # Angle
        #
        "degree": "deg",
        "degrees": "deg",

        "radian": "rad",
        "radians": "rad",

        #
        # Data size
        #
        "byte": "b",
        "bytes": "b",

        "kib": "kb",
        "mib": "mb",
        "gib": "gb",
        "tib": "tb",
    }

    def _normalize_unit(
        self,
        unit: str,
    ) -> str:

        normalized = (
            unit
            .strip()
            .lower()
        )

        return self._ALIASES.get(
            normalized,
            normalized,
        )

    def _convert_linear(
        self,
        value: float,
        from_unit: str,
        to_unit: str,
    ) -> float:

        base_value = (
            value
            * self._CONVERSIONS[from_unit]
        )

        return (
            base_value
            / self._CONVERSIONS[to_unit]
        )

    def _convert_temperature(
        self,
        value: float,
        from_unit: str,
        to_unit: str,
    ) -> float:

        #
        # To Celsius
        #
        if from_unit == "c":
            celsius = value

        elif from_unit == "f":
            celsius = (
                value - 32
            ) * 5.0 / 9.0

        elif from_unit == "k":
            celsius = (
                value - 273.15
            )

        else:
            raise ValueError(
                f"Unknown temperature unit: "
                f"{from_unit}"
            )

        #
        # From Celsius
        #
        if to_unit == "c":
            return celsius

        if to_unit == "f":
            return (
                celsius * 9.0 / 5.0
            ) + 32

        if to_unit == "k":
            return (
                celsius + 273.15
            )

        raise ValueError(
            f"Unknown temperature unit: "
            f"{to_unit}"
        )

    def _convert_angle(
        self,
        value: float,
        from_unit: str,
        to_unit: str,
    ) -> float:

        if from_unit == "deg":
            radians = math.radians(
                value
            )

        elif from_unit == "rad":
            radians = value

        else:
            raise ValueError(
                f"Unknown angle unit: "
                f"{from_unit}"
            )

        if to_unit == "rad":
            return radians

        if to_unit == "deg":
            return math.degrees(
                radians
            )

        raise ValueError(
            f"Unknown angle unit: "
            f"{to_unit}"
        )

    def convert(
        self,
        value: float,
        from_unit: str,
        to_unit: str,
    ) -> dict:

        try:

            from_unit = self._normalize_unit(
                from_unit
            )

            to_unit = self._normalize_unit(
                to_unit
            )

            if from_unit not in self._DIMENSIONS:
                raise ValueError(
                    f"Unknown unit: {from_unit}"
                )

            if to_unit not in self._DIMENSIONS:
                raise ValueError(
                    f"Unknown unit: {to_unit}"
                )

            from_dimension = (
                self._DIMENSIONS[from_unit]
            )

            to_dimension = (
                self._DIMENSIONS[to_unit]
            )

            if (
                from_dimension
                != to_dimension
            ):
                raise ValueError(
                    f"Cannot convert "
                    f"{from_dimension} "
                    f"to "
                    f"{to_dimension}"
                )

            if from_dimension == "temperature":

                result = (
                    self._convert_temperature(
                        value,
                        from_unit,
                        to_unit,
                    )
                )

            elif from_dimension == "angle":

                result = (
                    self._convert_angle(
                        value,
                        from_unit,
                        to_unit,
                    )
                )

            else:

                result = (
                    self._convert_linear(
                        value,
                        from_unit,
                        to_unit,
                    )
                )

            return {
                "success": True,
                "value": value,
                "from_unit": from_unit,
                "to_unit": to_unit,
                "result": result,
            }

        except Exception as ex:

            return {
                "success": False,
                "error": str(ex),
            }