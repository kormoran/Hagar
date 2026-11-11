"""Validatore del sottoinsieme Hagar Flow."""

from __future__ import annotations

import ast

from core.flow.errors import FlowValidationError


BUILTINS = {
    "len",
    "range",
    "str",
    "int",
    "float",
    "bool",
    "sorted",
    "enumerate",
    "zip",
    "min",
    "max",
    "sum",
    "any",
    "all",
    "print",
}

METHODS = {
    "str": {
        "strip",
        "lstrip",
        "rstrip",
        "lower",
        "upper",
        "startswith",
        "endswith",
        "replace",
        "split",
        "splitlines",
        "find",
        "count",
        "join",
    },
    "list": {
        "append",
        "extend",
        "insert",
        "pop",
        "sort",
        "reverse",
        "count",
        "index",
    },
    "dict": {
        "get",
        "keys",
        "values",
        "items",
        "setdefault",
        "update",
    },
}

_ALLOWED_NODES = {
    ast.Module,
    ast.Expr,
    ast.Assign,
    ast.AugAssign,
    ast.If,
    ast.For,
    ast.While,
    ast.Break,
    ast.Continue,
    ast.Return,
    ast.Pass,
    ast.Name,
    ast.Load,
    ast.Store,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.JoinedStr,
    ast.FormattedValue,
    ast.IfExp,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Subscript,
    ast.Slice,
    ast.Call,
    ast.keyword,
    ast.Attribute,
    ast.And,
    ast.Or,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
}

_DISALLOWED = {
    ast.Import: ("import is not allowed", "Usa le primitive fs/box."),
    ast.ImportFrom: ("import is not allowed", "Usa le primitive fs/box."),
    ast.ClassDef: ("class is not allowed", "Usa il codice lineare."),
    ast.FunctionDef: (
        "def is not allowed",
        "Scrivi il codice in linea, senza funzioni.",
    ),
    ast.AsyncFunctionDef: ("async is not allowed", None),
    ast.Lambda: ("lambda is not allowed", "Usa un ciclo esplicito."),
    ast.Try: ("try/except is not allowed", "Correggi il codice e riprova."),
    ast.With: ("with is not allowed", None),
    ast.AsyncWith: ("async is not allowed", None),
    ast.Await: ("await is not allowed", None),
    ast.Yield: ("yield is not allowed", None),
    ast.YieldFrom: ("yield is not allowed", None),
    ast.Global: ("global is not allowed", None),
    ast.Nonlocal: ("nonlocal is not allowed", None),
    ast.Del: ("del is not allowed", None),
    ast.Assert: ("assert is not allowed", None),
    ast.Raise: ("raise is not allowed", None),
    ast.Match: ("match is not allowed", None),
    ast.NamedExpr: ("walrus := is not allowed", None),
    ast.ListComp: ("comprehension is not allowed", "Usa un ciclo for."),
    ast.DictComp: ("comprehension is not allowed", "Usa un ciclo for."),
    ast.SetComp: ("comprehension is not allowed", "Usa un ciclo for."),
    ast.GeneratorExp: ("generator is not allowed", "Usa una lista."),
    ast.Starred: ("starred expression is not allowed", None),
    ast.Set: ("set is not allowed", "Usa una lista."),
}


LANGUAGE_CARD = """\
Hagar Flow v1 — sintassi Python ristretta, NON Python.

CONSENTITO:
- assegnazioni, if/elif/else, for, while, break, continue, return
- liste, tuple, dict, stringhe, numeri, bool, None, f-string
- metodi whitelisted su str/list/dict
- builtin: len, range, str, int, float, bool, sorted, enumerate,
  zip, min, max, sum, any, all, print

VIETATO:
- import, class, def, lambda, try, with, async, yield
- eval, exec, open, getattr, setattr, compile
- dunder, accesso a oggetti Python
- comprehension, generatori
- chiamate dinamiche

REGOLE:
- niente shell, rete o filesystem fuori dalle primitive
- il codice è lineare; non definire funzioni
- un errore interrompe il flusso: correggi e riprova
"""


def primitive_names(primitives: set[str]) -> set[str]:
    return set(primitives)


def validate(
    code: str,
    primitives: set[str] | None = None,
    *,
    max_source_chars: int = 20_000,
) -> ast.Module:

    if not isinstance(code, str):
        raise FlowValidationError("code must be a string")

    if len(code) > max_source_chars:
        raise FlowValidationError("code is too large")

    primitives = primitives or set()
    namespaces = {
        name.split(".", 1)[0]
        for name in primitives
        if "." in name
    }

    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise FlowValidationError(
            exc.msg or "invalid syntax",
            line=exc.lineno,
            column=exc.offset,
            hint="Controlla la sintassi del codice.",
        ) from exc

    _Validator(primitives, namespaces).visit(tree)
    return tree


class _Validator(ast.NodeVisitor):

    def __init__(
        self,
        primitives: set[str],
        namespaces: set[str],
    ) -> None:

        self.primitives = primitives
        self.namespaces = namespaces
        self.methods = {
            name
            for names in METHODS.values()
            for name in names
        }

    def _error(
        self,
        node: ast.AST,
        message: str,
        hint: str | None = None,
    ) -> None:

        raise FlowValidationError(
            message,
            line=getattr(node, "lineno", None),
            column=getattr(node, "col_offset", None),
            hint=hint,
        )

    def generic_visit(self, node: ast.AST) -> None:

        error = _DISALLOWED.get(type(node))

        if error is not None:
            message, hint = error
            self._error(node, message, hint)

        if type(node) not in _ALLOWED_NODES:
            self._error(
                node,
                f"syntax is not allowed: {type(node).__name__}",
                "Usa solo le forme elencate in flow.reference.",
            )

        super().generic_visit(node)

    # --------------------------------------------------
    # Names
    # --------------------------------------------------

    def visit_Name(self, node: ast.Name) -> None:
        self._check_name(node, node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        self._check_name(node, node.attr)

        if isinstance(node.value, ast.Name):
            if node.value.id in self.namespaces:
                full = f"{node.value.id}.{node.attr}"

                if full not in self.primitives:
                    self._error(
                        node,
                        f"unknown primitive: {full}",
                        "Usa flow.reference(section='primitives').",
                    )

                return

        if node.attr not in self.methods:
            self._error(
                node,
                f"method/attribute is not allowed: {node.attr}",
                "Usa solo i metodi elencati in flow.reference.",
            )

        self.generic_visit(node)

    def _check_name(
        self,
        node: ast.AST,
        name: str,
    ) -> None:

        if name.startswith("__") or name.endswith("__"):
            self._error(node, f"dunder name is not allowed: {name}")

        if name.startswith("_"):
            self._error(node, f"private name is not allowed: {name}")

    # --------------------------------------------------
    # Calls
    # --------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func

        if isinstance(func, ast.Name):
            if func.id not in BUILTINS:
                self._error(
                    node,
                    f"function is not allowed: {func.id}",
                    "Usa le primitive fs/box o i builtin consentiti.",
                )

        elif isinstance(func, ast.Attribute):
            if (
                isinstance(func.value, ast.Name)
                and func.value.id in self.namespaces
            ):
                full = f"{func.value.id}.{func.attr}"

                if full not in self.primitives:
                    self._error(
                        node,
                        f"unknown primitive: {full}",
                    )

            elif func.attr not in self.methods:
                self._error(
                    node,
                    f"method is not allowed: {func.attr}",
                )

        else:
            self._error(
                node,
                "dynamic call is not allowed",
                "Chiama direttamente una primitiva o un builtin.",
            )

        for keyword in node.keywords:
            if keyword.arg is None:
                self._error(node, "**kwargs is not allowed")

        self.generic_visit(node)

    # --------------------------------------------------
    # Assignment / control
    # --------------------------------------------------

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._check_target(target)

        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._check_target(node.target)
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self._check_target(node.target)
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.generic_visit(node)

    def _check_target(self, node: ast.AST) -> None:

        if isinstance(node, ast.Name):
            self._check_name(node, node.id)
            return

        if isinstance(node, ast.Subscript):
            return

        if isinstance(node, (ast.Tuple, ast.List)):
            for item in node.elts:
                self._check_target(item)
            return

        self._error(
            node,
            "assignment target is not allowed",
            "Assegna a un nome o a un elemento di lista/dict.",
        )

    # --------------------------------------------------
    # Literals / expressions
    # --------------------------------------------------

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, (bytes, complex)):
            self._error(node, "this constant type is not allowed")

    def visit_Dict(self, node: ast.Dict) -> None:
        if any(key is None for key in node.keys):
            self._error(node, "dict unpacking is not allowed")

        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        for op in node.ops:
            if type(op) not in _ALLOWED_NODES:
                self._error(node, f"comparison is not allowed: {type(op).__name__}")

        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if type(node.op) not in _ALLOWED_NODES:
            self._error(node, f"operator is not allowed: {type(node.op).__name__}")

        self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        if type(node.op) not in _ALLOWED_NODES:
            self._error(node, f"operator is not allowed: {type(node.op).__name__}")

        self.generic_visit(node)
