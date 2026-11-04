from __future__ import annotations

import statistics


class Stats_calc:

    def compute(
        self,
        operation: str,
        values: list[float],
    ) -> dict:

        try:

            if not values:
                raise ValueError(
                    "Values list cannot be empty."
                )

            operation = operation.lower()

            operations = {

                "mean":
                    statistics.mean,

                "median":
                    statistics.median,

                "stdev":
                    statistics.stdev,

                "variance":
                    statistics.variance,

                "min":
                    min,

                "max":
                    max,

                "sum":
                    sum,

                "count":
                    lambda x: len(x),
            }

            function = operations.get(
                operation
            )

            if function is None:

                raise ValueError(
                    f"Unknown operation: "
                    f"{operation}"
                )

            #
            # stdev e variance richiedono
            # almeno due campioni
            #
            if (
                operation in (
                    "stdev",
                    "variance",
                )
                and len(values) < 2
            ):
                raise ValueError(
                    f"{operation} requires "
                    f"at least two values."
                )

            result = function(values)

            return {
                "success": True,
                "operation": operation,
                "count": len(values),
                "result": result,
            }

        except Exception as ex:

            return {
                "success": False,
                "operation": operation,
                "error": str(ex),
            }