"""Test del loader e del runner dev.run."""

from __future__ import annotations

import json
import sys
import textwrap

import pytest
import yaml

from core.dev_recipes import DevRecipeError, DevRecipeLoader
from core.dev_runner import DevExecutionError, DevRunner


def write_recipes(tmp_path, recipes):
    path = tmp_path / "recipes.yaml"
    path.write_text(
        yaml.safe_dump(
            {"version": 1, "recipes": recipes},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_loader_and_parameters(tmp_path):
    path = write_recipes(
        tmp_path,
        {
            "test": {
                "description": "test",
                "argv": [sys.executable, "script.py", "{target}"],
                "parameters": {
                    "target": {
                        "type": "choice",
                        "choices": ["a", "b"],
                    }
                },
            }
        },
    )

    book = DevRecipeLoader().load(path)
    recipe = book.recipes["test"]
    loader = DevRecipeLoader()
    values = loader.resolve_parameters(
        recipe,
        {"target": "b"},
    )

    assert loader.render_argv(recipe, values)[-1] == "b"


def test_loader_rejects_shell_and_inline_code(tmp_path):
    path = write_recipes(
        tmp_path,
        {
            "bad": {
                "argv": ["bash", "-c", "echo x"],
            }
        },
    )

    with pytest.raises(DevRecipeError):
        DevRecipeLoader().load(path)

    path = write_recipes(
        tmp_path,
        {
            "bad": {
                "argv": [sys.executable, "-c", "print(1)"],
            }
        },
    )

    with pytest.raises(DevRecipeError):
        DevRecipeLoader().load(path)


def test_runner_executes_in_copy(tmp_path, sandbox, workspace):
    (workspace / "script.py").write_text(
        "from pathlib import Path\n"
        "Path('generated.txt').write_text('ok')\n"
        "print('hello')\n",
        encoding="utf-8",
    )
    path = write_recipes(
        tmp_path,
        {
            "hello": {
                "argv": [sys.executable, "script.py"],
                "cwd": ".",
                "timeout": 30,
            }
        },
    )
    book = DevRecipeLoader().load(path)
    runner = DevRunner(sandbox, book)

    result = runner.run("hello")

    assert result.success is True
    assert result.exit_code == 0
    assert result.stdout.strip() == "hello"
    # Il workspace reale non deve contenere gli artefatti del test.
    assert not (workspace / "generated.txt").exists()


def test_runner_exit_code_and_timeout(tmp_path, sandbox, workspace):
    (workspace / "fail.py").write_text(
        "import sys\nsys.exit(3)\n",
        encoding="utf-8",
    )
    (workspace / "slow.py").write_text(
        "import time\ntime.sleep(2)\n",
        encoding="utf-8",
    )
    path = write_recipes(
        tmp_path,
        {
            "fail": {
                "argv": [sys.executable, "fail.py"],
                "timeout": 30,
            },
            "slow": {
                "argv": [sys.executable, "slow.py"],
                "timeout": 0.1,
            },
        },
    )
    book = DevRecipeLoader().load(path)
    runner = DevRunner(sandbox, book)

    failed = runner.run("fail")
    timed = runner.run("slow")

    assert failed.success is False
    assert failed.exit_code == 3
    assert timed.timed_out is True
    assert timed.success is False


def test_runner_requires_known_parameters(tmp_path, sandbox, workspace):
    path = write_recipes(
        tmp_path,
        {
            "target": {
                "argv": [sys.executable, "script.py", "{target}"],
                "parameters": {
                    "target": {
                        "type": "choice",
                        "choices": ["a"],
                    }
                },
            }
        },
    )
    book = DevRecipeLoader().load(path)
    runner = DevRunner(sandbox, book)

    with pytest.raises(DevRecipeError):
        runner.run("target", {"target": "b"})

    with pytest.raises(DevExecutionError):
        runner.run("missing")
