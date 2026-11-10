"""Loader e schema delle ricette dev.run."""

from __future__ import annotations

import hashlib
import re

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


SUPPORTED_VERSION = 1
MAX_RECIPES = 200
MAX_ARGV = 100
MAX_TIMEOUT = 3600
MAX_ENV = 64
MAX_PARAMETERS = 32

_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_FORBIDDEN_SHELLS = {
    "bash", "sh", "zsh", "fish", "cmd", "cmd.exe",
    "powershell", "powershell.exe", "pwsh", "pwsh.exe",
}
_FORBIDDEN_INLINE = {"-c", "--eval", "-e", "-Command", "-EncodedCommand"}


class DevRecipeError(RuntimeError):
    pass


@dataclass(frozen=True)
class RecipeParameter:
    name: str
    kind: str
    required: bool = True
    default: Any = None
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class DevRecipe:
    name: str
    description: str
    argv: tuple[str, ...]
    cwd: str = "."
    timeout: float = 120.0
    env: dict[str, str] = field(default_factory=dict)
    parameters: dict[str, RecipeParameter] = field(default_factory=dict)
    success_codes: tuple[int, ...] = (0,)
    stdin_file: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "argv": list(self.argv),
            "cwd": self.cwd,
            "timeout": self.timeout,
            "env_keys": sorted(self.env),
            "parameters": {
                key: {
                    "type": parameter.kind,
                    "required": parameter.required,
                    "default": parameter.default,
                    "choices": list(parameter.choices),
                }
                for key, parameter in self.parameters.items()
            },
            "success_codes": list(self.success_codes),
            "stdin_file": self.stdin_file,
        }


@dataclass(frozen=True)
class RecipeBook:
    version: int
    recipes: dict[str, DevRecipe]
    path: Path
    sha256: str


class DevRecipeLoader:

    def load(self, path: str | Path) -> RecipeBook:

        recipe_path = Path(path)

        if not recipe_path.is_file():
            raise DevRecipeError(f"recipes file not found: {recipe_path}")

        raw = recipe_path.read_bytes()

        try:
            data = yaml.safe_load(raw.decode("utf-8"))
        except (UnicodeDecodeError, yaml.YAMLError) as exc:
            raise DevRecipeError(f"invalid recipes YAML: {exc}") from exc

        if not isinstance(data, dict):
            raise DevRecipeError("recipes root must be a mapping")

        allowed_root = {"version", "recipes"}
        unknown = set(data) - allowed_root

        if unknown:
            raise DevRecipeError(
                "unknown recipes keys: " + ", ".join(sorted(unknown))
            )

        version = data.get("version")

        if version != SUPPORTED_VERSION:
            raise DevRecipeError(
                f"unsupported recipes version: {version!r}"
            )

        raw_recipes = data.get("recipes")

        if not isinstance(raw_recipes, dict) or not raw_recipes:
            raise DevRecipeError("recipes must be a non-empty mapping")

        if len(raw_recipes) > MAX_RECIPES:
            raise DevRecipeError("too many recipes")

        recipes: dict[str, DevRecipe] = {}

        for name, entry in raw_recipes.items():
            recipe = self._parse_recipe(str(name), entry)
            recipes[recipe.name] = recipe

        return RecipeBook(
            version=version,
            recipes=recipes,
            path=recipe_path.resolve(),
            sha256=hashlib.sha256(raw).hexdigest(),
        )

    def _parse_recipe(self, name: str, entry: Any) -> DevRecipe:

        if not _NAME_RE.fullmatch(name):
            raise DevRecipeError(f"invalid recipe name: {name!r}")

        if not isinstance(entry, dict):
            raise DevRecipeError(f"recipe {name} must be a mapping")

        allowed = {
            "description",
            "argv",
            "cwd",
            "timeout",
            "env",
            "parameters",
            "success_codes",
            "stdin_file",
        }
        unknown = set(entry) - allowed

        if unknown:
            raise DevRecipeError(
                f"recipe {name}: unknown keys: "
                + ", ".join(sorted(unknown))
            )

        argv = self._argv(name, entry.get("argv"))
        self._reject_shell(name, argv)

        description = entry.get("description", "")
        if not isinstance(description, str):
            raise DevRecipeError(f"recipe {name}: description must be a string")

        cwd = entry.get("cwd", ".")
        if not isinstance(cwd, str) or not cwd.strip():
            raise DevRecipeError(f"recipe {name}: cwd must be a string")

        timeout = entry.get("timeout", 120)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise DevRecipeError(f"recipe {name}: timeout must be a number")
        if not 0 < float(timeout) <= MAX_TIMEOUT:
            raise DevRecipeError(f"recipe {name}: invalid timeout")
        timeout = float(timeout)

        env = self._env(name, entry.get("env", {}))

        raw_parameters = entry.get("parameters", {})
        if not isinstance(raw_parameters, dict):
            raise DevRecipeError(f"recipe {name}: parameters must be a mapping")
        if len(raw_parameters) > MAX_PARAMETERS:
            raise DevRecipeError(f"recipe {name}: too many parameters")

        parameters = {
            key: self._parameter(name, key, value)
            for key, value in raw_parameters.items()
        }
        self._check_placeholders(name, argv, parameters)

        raw_codes = entry.get("success_codes", [0])
        if not isinstance(raw_codes, list) or not raw_codes:
            raise DevRecipeError(f"recipe {name}: success_codes must be a list")
        success_codes = []
        for code in raw_codes:
            if isinstance(code, bool) or not isinstance(code, int):
                raise DevRecipeError(
                    f"recipe {name}: success_codes must be integers"
                )
            success_codes.append(code)

        stdin_file = entry.get("stdin_file")
        if stdin_file is not None and not isinstance(stdin_file, str):
            raise DevRecipeError(f"recipe {name}: stdin_file must be a string")

        return DevRecipe(
            name=name,
            description=description,
            argv=argv,
            cwd=cwd,
            timeout=timeout,
            env=env,
            parameters=parameters,
            success_codes=tuple(success_codes),
            stdin_file=stdin_file,
        )

    @staticmethod
    def _argv(name: str, value: Any) -> tuple[str, ...]:

        if not isinstance(value, list) or not value:
            raise DevRecipeError(f"recipe {name}: argv must be a non-empty list")
        if len(value) > MAX_ARGV:
            raise DevRecipeError(f"recipe {name}: argv is too long")

        result = []
        for item in value:
            if not isinstance(item, str) or not item:
                raise DevRecipeError(
                    f"recipe {name}: argv items must be non-empty strings"
                )
            if "\x00" in item:
                raise DevRecipeError(f"recipe {name}: invalid NUL in argv")
            result.append(item)

        return tuple(result)

    @staticmethod
    def _reject_shell(name: str, argv: tuple[str, ...]) -> None:

        executable = Path(argv[0]).name.lower()
        if executable in _FORBIDDEN_SHELLS:
            raise DevRecipeError(
                f"recipe {name}: shell executables are not allowed"
            )

        for arg in argv[1:]:
            if arg in _FORBIDDEN_INLINE:
                raise DevRecipeError(
                    f"recipe {name}: inline code option is not allowed: {arg}"
                )

    @staticmethod
    def _env(name: str, value: Any) -> dict[str, str]:

        if value is None:
            return {}
        if not isinstance(value, dict):
            raise DevRecipeError(f"recipe {name}: env must be a mapping")
        if len(value) > MAX_ENV:
            raise DevRecipeError(f"recipe {name}: too many env variables")

        result = {}
        for key, item in value.items():
            if not isinstance(key, str) or not _NAME_RE.fullmatch(key):
                raise DevRecipeError(f"recipe {name}: invalid env key")
            if not isinstance(item, str):
                raise DevRecipeError(f"recipe {name}: env values must be strings")
            result[key] = item

        return result

    def _parameter(
        self,
        recipe: str,
        name: str,
        value: Any,
    ) -> RecipeParameter:

        if not isinstance(value, dict):
            raise DevRecipeError(
                f"recipe {recipe}: parameter {name} must be a mapping"
            )

        allowed = {"type", "required", "default", "choices"}
        unknown = set(value) - allowed
        if unknown:
            raise DevRecipeError(
                f"recipe {recipe}: parameter {name} has unknown keys"
            )

        kind = value.get("type", "string")
        if kind not in {"string", "integer", "boolean", "choice", "path"}:
            raise DevRecipeError(
                f"recipe {recipe}: unsupported parameter type {kind!r}"
            )

        required = value.get("required", True)
        if not isinstance(required, bool):
            raise DevRecipeError(
                f"recipe {recipe}: parameter {name}.required must be boolean"
            )

        default = value.get("default")
        choices = value.get("choices", [])

        if kind == "choice":
            if not isinstance(choices, list) or not choices:
                raise DevRecipeError(
                    f"recipe {recipe}: choice parameter {name} needs choices"
                )
            if not all(isinstance(choice, str) for choice in choices):
                raise DevRecipeError(
                    f"recipe {recipe}: choices must be strings"
                )
            choices = tuple(choices)
        else:
            choices = ()

        if default is not None:
            self._validate_value(
                recipe,
                name,
                kind,
                default,
                choices,
            )
        elif not required:
            raise DevRecipeError(
                f"recipe {recipe}: optional parameter {name} needs a default"
            )

        return RecipeParameter(
            name=name,
            kind=kind,
            required=required,
            default=default,
            choices=choices,
        )

    def _check_placeholders(
        self,
        recipe: str,
        argv: tuple[str, ...],
        parameters: dict[str, RecipeParameter],
    ) -> None:

        used = set()

        for token in argv:
            for match in _PLACEHOLDER_RE.finditer(token):
                name = match.group(1)
                if match.group(0) != token:
                    raise DevRecipeError(
                        f"recipe {recipe}: placeholder {name} must occupy "
                        "the whole argv element"
                    )
                if name not in parameters:
                    raise DevRecipeError(
                        f"recipe {recipe}: unknown placeholder {name}"
                    )
                used.add(name)

        for name, parameter in parameters.items():
            if parameter.required and name not in used:
                raise DevRecipeError(
                    f"recipe {recipe}: required parameter {name} is unused"
                )

    def _validate_value(
        self,
        recipe: str,
        name: str,
        kind: str,
        value: Any,
        choices: tuple[str, ...],
    ) -> None:

        if kind in {"string", "path"}:
            if not isinstance(value, str) or not value:
                raise DevRecipeError(
                    f"recipe {recipe}: parameter {name} must be a string"
                )
        elif kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise DevRecipeError(
                    f"recipe {recipe}: parameter {name} must be an integer"
                )
        elif kind == "boolean":
            if not isinstance(value, bool):
                raise DevRecipeError(
                    f"recipe {recipe}: parameter {name} must be boolean"
                )
        elif kind == "choice":
            if value not in choices:
                raise DevRecipeError(
                    f"recipe {recipe}: parameter {name} is not a valid choice"
                )

    def resolve_parameters(
        self,
        recipe: DevRecipe,
        provided: dict[str, Any] | None,
    ) -> dict[str, Any]:

        provided = dict(provided or {})
        unknown = set(provided) - set(recipe.parameters)

        if unknown:
            raise DevRecipeError(
                f"recipe {recipe.name}: unknown parameters: "
                + ", ".join(sorted(unknown))
            )

        resolved = {}

        for name, parameter in recipe.parameters.items():

            if name in provided:
                value = provided[name]
            elif parameter.required:
                raise DevRecipeError(
                    f"recipe {recipe.name}: missing parameter {name}"
                )
            else:
                value = parameter.default

            self._validate_value(
                recipe.name,
                name,
                parameter.kind,
                value,
                parameter.choices,
            )
            resolved[name] = value

        return resolved

    @staticmethod
    def render_argv(
        recipe: DevRecipe,
        parameters: dict[str, Any],
    ) -> tuple[str, ...]:

        result = []

        for token in recipe.argv:
            match = _PLACEHOLDER_RE.fullmatch(token)
            if match:
                result.append(str(parameters[match.group(1)]))
            else:
                result.append(token)

        return tuple(result)
