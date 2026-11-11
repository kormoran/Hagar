"""Interprete AST per Hagar Flow."""

from __future__ import annotations

import ast
import builtins
import json
import time

from dataclasses import dataclass
from typing import Any

from core.flow.errors import FlowError, FlowRuntimeError, FlowValidationError
from core.flow.language import BUILTINS, METHODS, validate
from core.models import FlowConfig


@dataclass(slots=True)
class FlowResult:
    ok: bool
    result: Any = None
    error: dict | None = None
    steps: int = 0
    tool_calls: int = 0
    duration_ms: int = 0
    trace: list[dict] | None = None
    repair_attempts: int = 0


class _Return(Exception):

    def __init__(self, value: Any) -> None:
        self.value = value


class _Break(Exception):
    pass


class _Continue(Exception):
    pass


class _Namespace:

    def __init__(self, name: str) -> None:
        self.name = name


class FlowRunner:

    def __init__(
        self,
        registry,
        config: FlowConfig,
        primitives: set[str] | None = None,
        audit=None,
    ) -> None:

        self.registry = registry
        self.config = config
        self.audit = audit
        self.primitives = primitives or {
            tool.name
            for tool in registry.list_definitions()
            if tool.category == "flow-primitive"
        }

    def run(self, code: str) -> FlowResult:

        started = time.monotonic()

        try:
            tree = validate(
                code,
                self.primitives,
                max_source_chars=self.config.max_source_chars,
            )
        except FlowValidationError as exc:
            return FlowResult(
                ok=False,
                error=exc.as_dict(),
                duration_ms=_milliseconds(started),
            )

        self._record("flow.start", chars=len(code))

        try:
            interpreter = _Interpreter(
                tree,
                self.registry,
                self.config,
                self.primitives,
                self.audit,
            )
            value = interpreter.execute()
            encoded = json.dumps(value, ensure_ascii=False)

            if len(encoded) > self.config.max_output_chars:
                raise FlowRuntimeError(
                    "flow result is too large",
                    hint="Riduci il valore restituito.",
                )
        except FlowError as exc:
            self._record(
                "flow.error",
                kind=exc.kind,
                line=exc.line,
                message=str(exc),
            )
            return FlowResult(
                ok=False,
                error=exc.as_dict(),
                steps=getattr(interpreter, "steps", 0)
                if "interpreter" in locals()
                else 0,
                tool_calls=getattr(interpreter, "tool_calls", 0)
                if "interpreter" in locals()
                else 0,
                duration_ms=_milliseconds(started),
            )
        except Exception as exc:
            self._record(
                "flow.error",
                kind="runtime",
                message=str(exc),
            )
            return FlowResult(
                ok=False,
                error={
                    "kind": "runtime",
                    "line": None,
                    "column": None,
                    "message": str(exc),
                    "hint": None,
                },
                steps=getattr(interpreter, "steps", 0)
                if "interpreter" in locals()
                else 0,
                tool_calls=getattr(interpreter, "tool_calls", 0)
                if "interpreter" in locals()
                else 0,
                duration_ms=_milliseconds(started),
            )

        self._record(
            "flow.result",
            steps=interpreter.steps,
            tool_calls=interpreter.tool_calls,
        )
        return FlowResult(
            ok=True,
            result=value,
            steps=interpreter.steps,
            tool_calls=interpreter.tool_calls,
            duration_ms=_milliseconds(started),
            trace=interpreter.trace,
        )

    def _record(self, event: str, **fields: Any) -> None:
        if self.audit is not None:
            self.audit.record(event, **fields)

    def record(self, event: str, **fields: Any) -> None:
        self._record(event, **fields)


class _Interpreter:

    def __init__(
        self,
        tree: ast.Module,
        registry,
        config: FlowConfig,
        primitives: set[str],
        audit=None,
    ) -> None:

        self.tree = tree
        self.registry = registry
        self.config = config
        self.primitives = primitives
        self.audit = audit
        self.env: dict[str, Any] = {}
        self.steps = 0
        self.tool_calls = 0
        self.loop_iterations = 0
        self.trace: list[dict] = []
        self.last_value: Any = None
        self.started = time.monotonic()
        self.namespaces = {
            name.split(".", 1)[0]
            for name in primitives
            if "." in name
        }

    def execute(self) -> Any:

        try:
            for statement in self.tree.body:
                self._exec(statement)
        except _Return as signal:
            return signal.value
        except (_Break, _Continue) as exc:
            raise FlowRuntimeError(
                "break/continue outside loop"
            ) from exc

        return self.last_value

    # --------------------------------------------------
    # Statements
    # --------------------------------------------------

    def _exec(self, node: ast.stmt) -> None:

        self._tick(node)

        if isinstance(node, ast.Expr):
            self.last_value = self._eval(node.value)
            return

        if isinstance(node, ast.Assign):
            value = self._eval(node.value)

            for target in node.targets:
                self._assign(target, value)

            return

        if isinstance(node, ast.AugAssign):
            current = self._eval(_target_expr(node.target))
            value = self._apply_binop(
                type(node.op),
                current,
                self._eval(node.value),
                node,
            )
            self._assign(node.target, value)
            return

        if isinstance(node, ast.If):
            if self._truth(self._eval(node.test)):
                self._exec_block(node.body)
            else:
                self._exec_block(node.orelse)
            return

        if isinstance(node, ast.For):
            self._exec_for(node)
            return

        if isinstance(node, ast.While):
            self._exec_while(node)
            return

        if isinstance(node, ast.Break):
            raise _Break()

        if isinstance(node, ast.Continue):
            raise _Continue()

        if isinstance(node, ast.Return):
            raise _Return(
                self._eval(node.value) if node.value is not None else None
            )

        if isinstance(node, ast.Pass):
            return

        raise self._error(node, "statement is not supported")

    def _exec_block(self, statements: list[ast.stmt]) -> None:
        for statement in statements:
            self._exec(statement)

    def _exec_for(self, node: ast.For) -> None:

        iterable = self._eval(node.iter)
        values = self._iterable_values(node.iter, iterable)

        for item in values:
            self._loop(node)
            self._assign(node.target, item)

            try:
                self._exec_block(node.body)
            except _Continue:
                continue
            except _Break:
                break
        else:
            self._exec_block(node.orelse)

    def _iterable_values(
        self,
        node: ast.AST,
        iterable: Any,
    ) -> list | tuple | range:

        if isinstance(iterable, dict):
            return list(iterable)

        if isinstance(iterable, (str, list, tuple, range)):
            return iterable

        try:
            return list(iterable)
        except TypeError as exc:
            raise self._error(
                node,
                "iteration requires a list, tuple, string, dict or range",
            ) from exc

    def _eval_listcomp(self, node: ast.ListComp) -> list:

        if len(node.generators) != 1:
            raise self._error(
                node,
                "only one for is allowed in a list comprehension",
            )

        generator = node.generators[0]
        iterable = self._eval(generator.iter)
        values = self._iterable_values(generator.iter, iterable)

        outer_env = self.env
        scope = dict(outer_env)
        self.env = scope
        result = []

        try:
            for item in values:
                self._loop(node)
                self._assign(generator.target, item)

                if all(
                    self._truth(self._eval(condition))
                    for condition in generator.ifs
                ):
                    result.append(self._eval(node.elt))

                    if len(result) > self.config.max_loop_iterations:
                        raise self._error(
                            node,
                            "list comprehension result is too large",
                        )
        finally:
            self.env = outer_env

        return result

    def _exec_while(self, node: ast.While) -> None:

        while self._truth(self._eval(node.test)):
            self._loop(node)

            try:
                self._exec_block(node.body)
            except _Continue:
                continue
            except _Break:
                break
        else:
            self._exec_block(node.orelse)

    def _loop(self, node: ast.AST) -> None:

        self.loop_iterations += 1

        if self.loop_iterations > self.config.max_loop_iterations:
            raise self._error(
                node,
                "loop budget exceeded",
                "Riduci il numero di iterazioni.",
            )

        self._tick(node)

    # --------------------------------------------------
    # Assignment
    # --------------------------------------------------

    def _assign(self, target: ast.AST, value: Any) -> None:

        if isinstance(target, ast.Name):
            self.env[target.id] = value
            return

        if isinstance(target, ast.Subscript):
            container = self._eval(target.value)
            key = self._slice_key(target.slice)

            try:
                container[key] = value
            except Exception as exc:
                raise self._error(
                    target,
                    f"cannot assign subscript: {exc}",
                ) from exc

            return

        if isinstance(target, (ast.Tuple, ast.List)):
            try:
                items = list(value)
            except TypeError as exc:
                raise self._error(
                    target,
                    "unpacking requires an iterable",
                ) from exc

            if len(items) != len(target.elts):
                raise self._error(
                    target,
                    "unpacking length mismatch",
                )

            for child, item in zip(target.elts, items):
                self._assign(child, item)

            return

        raise self._error(target, "assignment target is not supported")

    # --------------------------------------------------
    # Expressions
    # --------------------------------------------------

    def _eval(self, node: ast.AST) -> Any:

        if isinstance(node, ast.Constant):
            return node.value

        if isinstance(node, ast.Name):
            if node.id in self.env:
                return self.env[node.id]

            if node.id in self.namespaces:
                return _Namespace(node.id)

            raise self._error(node, f"name is not defined: {node.id}")

        if isinstance(node, ast.List):
            return [self._eval(item) for item in node.elts]

        if isinstance(node, ast.Tuple):
            return tuple(self._eval(item) for item in node.elts)

        if isinstance(node, ast.Dict):
            return {
                self._eval(key): self._eval(value)
                for key, value in zip(node.keys, node.values)
            }

        if isinstance(node, ast.BinOp):
            return self._apply_binop(
                type(node.op),
                self._eval(node.left),
                self._eval(node.right),
                node,
            )

        if isinstance(node, ast.UnaryOp):
            value = self._eval(node.operand)

            if isinstance(node.op, ast.Not):
                return not value
            if isinstance(node.op, ast.USub):
                return -value
            if isinstance(node.op, ast.UAdd):
                return +value

            raise self._error(node, "unary operator is not supported")

        if isinstance(node, ast.BoolOp):
            values = node.values

            if isinstance(node.op, ast.And):
                result = True
                for item in values:
                    result = self._eval(item)
                    if not result:
                        return result
                return result

            result = False
            for item in values:
                result = self._eval(item)
                if result:
                    return result
            return result

        if isinstance(node, ast.Compare):
            left = self._eval(node.left)

            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval(comparator)

                if not self._compare(op, left, right):
                    return False

                left = right

            return True

        if isinstance(node, ast.Subscript):
            return self._eval(node.value)[self._slice_key(node.slice)]

        if isinstance(node, ast.ListComp):
            return self._eval_listcomp(node)

        if isinstance(node, ast.IfExp):
            return self._eval(
                node.body if self._truth(self._eval(node.test)) else node.orelse
            )

        if isinstance(node, ast.JoinedStr):
            return "".join(
                self._fstring_part(item) for item in node.values
            )

        if isinstance(node, ast.FormattedValue):
            return self._fstring_part(node)

        if isinstance(node, ast.Call):
            return self._eval_call(node)

        if isinstance(node, ast.Attribute):
            raise self._error(
                node,
                "attribute access is not allowed outside a call",
            )

        raise self._error(
            node,
            f"expression is not supported: {type(node).__name__}",
        )

    def _eval_call(self, node: ast.Call) -> Any:

        args = [self._eval(arg) for arg in node.args]
        kwargs = {
            keyword.arg: self._eval(keyword.value)
            for keyword in node.keywords
        }
        func = node.func

        if isinstance(func, ast.Name):

            if func.id not in BUILTINS:
                raise self._error(
                    node,
                    f"function is not allowed: {func.id}",
                )

            return self._builtin(func.id, args, kwargs, node)

        if isinstance(func, ast.Attribute):

            if (
                isinstance(func.value, ast.Name)
                and func.value.id in self.namespaces
            ):
                name = f"{func.value.id}.{func.attr}"
                return self._primitive(name, args, kwargs, node)

            receiver = self._eval(func.value)
            return self._method(receiver, func.attr, args, kwargs, node)

        raise self._error(node, "dynamic call is not allowed")

    # --------------------------------------------------
    # Primitive / methods
    # --------------------------------------------------

    def _primitive(
        self,
        name: str,
        args: list[Any],
        kwargs: dict[str, Any],
        node: ast.AST,
    ) -> Any:

        if name not in self.primitives:
            raise self._error(node, f"unknown primitive: {name}")

        self.tool_calls += 1

        if self.tool_calls > self.config.max_tool_calls:
            raise self._error(
                node,
                "tool call budget exceeded",
            )

        tool = self.registry.get(name)
        parameters = [parameter.name for parameter in tool.parameters]

        if len(args) > len(parameters):
            raise self._error(
                node,
                f"too many arguments for {name}",
            )

        call_args = dict(zip(parameters, args))
        call_args.update(kwargs)

        self._tick(node)
        self.trace.append(
            {
                "line": getattr(node, "lineno", None),
                "primitive": name,
            }
        )

        try:
            return self.registry.execute(name, **call_args)
        except FlowError:
            raise
        except Exception as exc:
            raise self._error(
                node,
                f"{name}: {exc}",
            ) from exc

    def _method(
        self,
        receiver: Any,
        name: str,
        args: list[Any],
        kwargs: dict[str, Any],
        node: ast.AST,
    ) -> Any:

        kind = type(receiver).__name__
        allowed = METHODS.get(kind, set())

        if name not in allowed:
            raise self._error(
                node,
                f"method is not allowed on {kind}: {name}",
            )

        try:
            return getattr(receiver, name)(*args, **kwargs)
        except Exception as exc:
            raise self._error(
                node,
                f"method {name} failed: {exc}",
            ) from exc

    def _builtin(
        self,
        name: str,
        args: list[Any],
        kwargs: dict[str, Any],
        node: ast.AST,
    ) -> Any:

        try:
            if name == "print":
                text = " ".join(str(item) for item in args)
                if len(self.trace) < 200:
                    self.trace.append({
                        "line": getattr(node, "lineno", None),
                        "print": text[:1000],
                    })
                return None

            if name == "range":
                result = range(*args, **kwargs)

                if len(result) > self.config.max_loop_iterations:
                    raise self._error(
                        node,
                        "range is too large",
                    )

                return result

            if name in {"enumerate", "zip"}:
                return list(getattr(builtins, name)(*args, **kwargs))

            return getattr(builtins, name)(*args, **kwargs)
        except FlowError:
            raise
        except Exception as exc:
            raise self._error(
                node,
                f"{name} failed: {exc}",
            ) from exc

    # --------------------------------------------------
    # Operators
    # --------------------------------------------------

    @staticmethod
    def _apply_binop(
        op: type,
        left: Any,
        right: Any,
        node: ast.AST,
    ) -> Any:

        if op is ast.Add:
            return left + right
        if op is ast.Sub:
            return left - right
        if op is ast.Mult:
            return left * right
        if op is ast.Div:
            return left / right
        if op is ast.FloorDiv:
            return left // right
        if op is ast.Mod:
            return left % right
        if op is ast.Pow:
            if isinstance(right, (int, float)) and abs(right) > 1000:
                raise FlowRuntimeError(
                    "exponent is too large",
                    line=getattr(node, "lineno", None),
                )
            return left ** right

        raise FlowRuntimeError(
            "operator is not supported",
            line=getattr(node, "lineno", None),
        )

    @staticmethod
    def _compare(op: ast.AST, left: Any, right: Any) -> bool:

        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Gt):
            return left > right
        if isinstance(op, ast.GtE):
            return left >= right
        if isinstance(op, ast.In):
            return left in right
        if isinstance(op, ast.NotIn):
            return left not in right
        if isinstance(op, ast.Is):
            return left is right
        if isinstance(op, ast.IsNot):
            return left is not right

        raise FlowRuntimeError("comparison is not supported")

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------

    def _fstring_part(self, node: ast.AST) -> str:

        if isinstance(node, ast.Constant):
            return str(node.value)

        if isinstance(node, ast.FormattedValue):
            value = self._eval(node.value)

            if node.conversion == 114:  # !r
                value = repr(value)
            elif node.conversion == 115:  # !s
                value = str(value)
            elif node.conversion == 97:  # !a
                value = ascii(value)

            spec = (
                self._eval(node.format_spec)
                if node.format_spec is not None
                else ""
            )
            return format(value, spec)

        raise self._error(node, "f-string part is not supported")

    def _slice_key(self, node: ast.AST) -> Any:

        if isinstance(node, ast.Slice):
            return slice(
                self._eval(node.lower) if node.lower else None,
                self._eval(node.upper) if node.upper else None,
                self._eval(node.step) if node.step else None,
            )

        return self._eval(node)

    @staticmethod
    def _truth(value: Any) -> bool:
        return bool(value)

    def _tick(self, node: ast.AST) -> None:

        self.steps += 1

        if self.steps > self.config.max_steps:
            raise self._error(
                node,
                "step budget exceeded",
            )

        if (
            time.monotonic() - self.started
            > self.config.timeout
        ):
            raise self._error(
                node,
                "flow timeout exceeded",
            )

    def _error(
        self,
        node: ast.AST,
        message: str,
        hint: str | None = None,
    ) -> FlowRuntimeError:

        return FlowRuntimeError(
            message,
            line=getattr(node, "lineno", None),
            column=getattr(node, "col_offset", None),
            hint=hint,
        )


def _target_expr(target: ast.AST) -> ast.AST:
    if isinstance(target, ast.Name):
        return ast.Name(id=target.id, ctx=ast.Load())
    if isinstance(target, ast.Subscript):
        return ast.Subscript(
            value=target.value,
            slice=target.slice,
            ctx=ast.Load(),
        )
    raise FlowRuntimeError("augmented assignment target is not supported")


def _milliseconds(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
