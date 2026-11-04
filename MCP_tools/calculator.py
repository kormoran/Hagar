from __future__ import annotations

import ast
import math


class Calculator:

    _FUNCTIONS = {
        "abs": abs,
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "asin": math.asin,
        "acos": math.acos,
        "atan": math.atan,
        "log": math.log,
        "log10": math.log10,
        "exp": math.exp,
        "floor": math.floor,
        "ceil": math.ceil,
        "round": round,
    }

    _CONSTANTS = {
        "pi": math.pi,
        "e": math.e,
    }

    _BINARY_OPERATORS = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b,
        ast.FloorDiv: lambda a, b: a // b,
        ast.Mod: lambda a, b: a % b,
        ast.Pow: lambda a, b: a**b,
    }

    _UNARY_OPERATORS = {
        ast.UAdd: lambda x: +x,
        ast.USub: lambda x: -x,
    }

    def evaluate(
        self,
        expression: str,
    ) -> dict:

        try:

            tree = ast.parse(
                expression,
                mode="eval",
            )

            result = self._evaluate_node(
                tree.body
            )

            return {
                "success": True,
                "result": result,
            }

        except Exception as ex:

            return {
                "success": False,
                "error": str(ex),
            }

    def _evaluate_node(
        self,
        node,
    ):

        #
        # Numeri
        #
        if isinstance(
            node,
            ast.Constant,
        ):

            if not isinstance(
                node.value,
                (int, float),
            ):
                raise ValueError(
                    "Invalid constant."
                )

            return node.value

        #
        # Compatibilità Python < 3.8
        #
        if isinstance(
            node,
            ast.Num,
        ):
            return node.n

        #
        # Costanti matematiche
        #
        if isinstance(
            node,
            ast.Name,
        ):

            if node.id in self._CONSTANTS:
                return self._CONSTANTS[
                    node.id
                ]

            raise ValueError(
                f"Unknown identifier: "
                f"{node.id}"
            )

        #
        # Operatori binari
        #
        if isinstance(
            node,
            ast.BinOp,
        ):

            operator_type = type(
                node.op
            )

            if (
                operator_type
                not in self._BINARY_OPERATORS
            ):
                raise ValueError(
                    f"Operator not allowed: "
                    f"{operator_type.__name__}"
                )

            left = self._evaluate_node(
                node.left
            )

            right = self._evaluate_node(
                node.right
            )

            return (
                self._BINARY_OPERATORS[
                    operator_type
                ](
                    left,
                    right,
                )
            )

        #
        # Operatori unari
        #

        if isinstance(
            node,
            ast.UnaryOp,
        ):

            operator_type = type(
                node.op
            )

            if (
                operator_type
                not in self._UNARY_OPERATORS
            ):
                raise ValueError(
                    f"Operator not allowed: "
                    f"{operator_type.__name__}"
                )

            operand = self._evaluate_node(
                node.operand
            )

            return (
                self._UNARY_OPERATORS[
                    operator_type
                ](
                    operand
                )
            )

        #
        # Chiamate a funzione
        #

        if isinstance(
            node,
            ast.Call,
        ):

            if not isinstance(
                node.func,
                ast.Name,
            ):
                raise ValueError(
                    "Invalid function call."
                )

            function_name = (
                node.func.id
            )

            function = (
                self._FUNCTIONS.get(
                    function_name
                )
            )

            if function is None:
                raise ValueError(
                    f"Unknown function: "
                    f"{function_name}"
                )

            arguments = [
                self._evaluate_node(arg)
                for arg in node.args
            ]

            return function(
                *arguments
            )

        raise ValueError(
            f"Unsupported expression: "
            f"{type(node).__name__}"
        )