"""Verify the evaluation command-line interface."""

import os
import subprocess
import sys
import tomllib
from importlib import import_module
from pathlib import Path

import pytest

evaluate = import_module("scripts.evaluate")


@pytest.mark.parametrize(
    "arguments",
    [["tasks"], ["show", "task"], ["run", "eval.toml"]],
    ids=["tasks", "show", "run"],
)
def test_cli_rejects_missing_data_directory_before_loading_tau2(
    tmp_path: Path, arguments: list[str]
) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "evaluate.py"
    environment = {
        key: value for key, value in os.environ.items() if key != "TAU2_DATA_DIR"
    }
    # The import guard makes this independent of tau2's logging configuration.
    code = (
        "import runpy, sys\n"
        "class RejectTau2:\n"
        "    def find_spec(self, fullname, path=None, target=None):\n"
        "        if fullname == 'tau2' or fullname.startswith('tau2.'):\n"
        "            raise AssertionError('tau2 imported before validation')\n"
        "sys.meta_path.insert(0, RejectTau2())\n"
        "sys.argv = sys.argv[1:]\n"
        "runpy.run_path(sys.argv[0], run_name='__main__')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(script), *arguments],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert (
        result.stderr == "error: Set TAU2_DATA_DIR to the tau2-bench data directory.\n"
    )


@pytest.mark.parametrize("invalid_path", ["empty", "blank", "missing", "file"])
def test_cli_rejects_invalid_data_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    invalid_path: str,
) -> None:
    path = tmp_path / "data"
    if invalid_path == "file":
        path.write_text("not a directory", encoding="utf-8")
    value = {"empty": "", "blank": "   "}.get(invalid_path, str(path))
    monkeypatch.setenv("TAU2_DATA_DIR", value)

    result = evaluate.main(["tasks"])

    assert result == 1
    output = capsys.readouterr()
    assert output.out == ""
    expected = (
        "Set TAU2_DATA_DIR to the tau2-bench data directory."
        if invalid_path in {"empty", "blank"}
        else "TAU2_DATA_DIR must point to an existing directory."
    )
    assert output.err == f"error: {expected}\n"


@pytest.fixture
def run_config_path(tmp_path: Path) -> Path:
    path = tmp_path / "evaluation.toml"
    path.write_text(
        evaluate.EVALUATION_TEMPLATE.replace(
            "task_ids = []", 'task_ids = ["selected_task"]'
        ),
        encoding="utf-8",
    )
    return path


def test_cli_run_prints_results_path_after_evaluating_loaded_config(
    run_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from evals import runner
    from evals.config import EvalConfig, load_config

    expected_config = load_config(run_config_path)
    results_path = run_config_path.parent / "run" / "results.json"
    received: list[tuple[EvalConfig, Path]] = []

    def run_evaluation(config: EvalConfig, *, config_path: Path) -> Path:
        received.append((config, config_path))
        return results_path

    monkeypatch.setattr(runner, "run_evaluation", run_evaluation)

    result = evaluate.main(["run", str(run_config_path)])

    assert result == 0
    assert received == [(expected_config, run_config_path)]
    output = capsys.readouterr()
    assert output.out == f"{results_path}\n"
    assert output.err == ""


def test_cli_run_rejects_invalid_config_before_evaluation(
    run_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from evals import runner

    run_config_path.write_text(evaluate.EVALUATION_TEMPLATE, encoding="utf-8")

    def unexpected_run(*args: object, **kwargs: object) -> Path:
        pytest.fail("Evaluation started with an invalid configuration")

    monkeypatch.setattr(runner, "run_evaluation", unexpected_run)

    result = evaluate.main(["run", str(run_config_path)])

    assert result == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "error: Invalid setting: evaluation.task_ids.\n"


def test_cli_run_reports_execution_failure_without_exposing_exception_details(
    run_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from evals import runner

    def failed_run(*args: object, **kwargs: object) -> Path:
        raise RuntimeError("private-api-key and private-server-response")

    monkeypatch.setattr(runner, "run_evaluation", failed_run)

    result = evaluate.main(["run", str(run_config_path)])

    assert result == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "error: Evaluation failed.\n"


@pytest.mark.parametrize("command", ["tasks", "show"])
def test_cli_displays_formatted_official_tasks(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    from evals.tasks import format_task_detail, format_task_list, list_tasks

    tasks = list_tasks()
    arguments = ["tasks"] if command == "tasks" else ["show", tasks[0].id]
    expected = (
        format_task_list(tasks) if command == "tasks" else format_task_detail(tasks[0])
    )

    result = evaluate.main(arguments)

    assert result == 0
    assert capsys.readouterr().out == expected + "\n"


def test_cli_reports_unknown_task_without_displaying_task_details(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from evals.tasks import list_tasks

    known_ids = {task.id for task in list_tasks()}
    unknown_id = "unknown"
    while unknown_id in known_ids:
        unknown_id += "_"

    result = evaluate.main(["show", unknown_id])

    assert result == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == f"error: Unknown mock task ID: {unknown_id}.\n"


def test_cli_loads_task_listing_from_script_outside_project(tmp_path: Path) -> None:
    from evals.tasks import format_task_list, list_tasks

    script = Path(__file__).resolve().parents[1] / "scripts" / "evaluate.py"
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    result = subprocess.run(
        [sys.executable, str(script), "tasks"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == format_task_list(list_tasks()) + "\n"


def test_cli_init_creates_only_a_template_requiring_task_selection(
    tmp_path: Path,
) -> None:
    from evals.config import ConfigError, load_config

    script = Path(__file__).resolve().parents[1] / "scripts" / "evaluate.py"

    result = subprocess.run(
        [sys.executable, str(script), "init"],
        cwd=tmp_path,
        env={key: value for key, value in os.environ.items() if key != "TAU2_DATA_DIR"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout == result.stderr == ""
    template_path = tmp_path / "evaluation.toml"
    assert list(tmp_path.iterdir()) == [template_path]
    template = template_path.read_text(encoding="utf-8")
    assert tomllib.loads(template)["evaluation"]["task_ids"] == []
    with pytest.raises(ConfigError, match="evaluation.task_ids"):
        load_config(template_path)

    template_path.write_text(
        template.replace("task_ids = []", 'task_ids = ["selected_task"]'),
        encoding="utf-8",
    )
    config = load_config(template_path)
    assert config.evaluation.task_ids == ["selected_task"]
    assert config.agent.api_key_env is None
    assert config.user.api_key_env is None


@pytest.mark.parametrize("existing_path", ["file", "directory"])
def test_cli_init_reports_failure_without_overwriting_existing_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    existing_path: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    template_path = tmp_path / "evaluation.toml"
    if existing_path == "file":
        template_path.write_text("existing configuration", encoding="utf-8")
    else:
        template_path.mkdir()

    result = evaluate.main(["init"])

    assert result == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "evaluation.toml" in output.err
    if existing_path == "file":
        assert template_path.read_text("utf-8") == "existing configuration"
    else:
        assert template_path.is_dir()


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (["init"], {"command": "init"}),
        (["tasks"], {"command": "tasks"}),
        (["show", "task_id"], {"command": "show", "task_id": "task_id"}),
        (
            ["run", "my evaluation.toml"],
            {"command": "run", "config_path": Path("my evaluation.toml")},
        ),
    ],
    ids=["init", "tasks", "show", "run"],
)
def test_cli_parses_supported_commands(
    arguments: list[str], expected: dict[str, object]
) -> None:
    parsed = evaluate._build_parser().parse_args(arguments)

    assert vars(parsed) == expected


@pytest.mark.parametrize(
    "arguments",
    [[], ["unknown"], ["show"], ["run"]],
    ids=[
        "missing_command",
        "unknown_command",
        "missing_task_id",
        "missing_config_path",
    ],
)
def test_cli_reports_usage_when_required_arguments_are_invalid(
    arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as error:
        evaluate._build_parser().parse_args(arguments)

    assert error.value.code == 2
    output = capsys.readouterr()
    assert "usage:" in output.err
    assert output.out == ""


def test_cli_displays_available_commands_from_script_help(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "evaluate.py"

    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        env={key: value for key, value in os.environ.items() if key != "TAU2_DATA_DIR"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0
    assert "{init,tasks,show,run}" in result.stdout
    assert result.stderr == ""


def test_cli_run_reports_infrastructure_error_counts_and_results_path(
    run_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from evals import runner

    results_path = run_config_path.parent / "results.json"

    def failed_run(*args: object, **kwargs: object) -> Path:
        raise runner.EvaluationInfrastructureError(
            total_count=3, error_count=1, results_path=results_path
        )

    monkeypatch.setattr(runner, "run_evaluation", failed_run)

    result = evaluate.main(["run", str(run_config_path)])

    assert result == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "error: 1 of 3 simulations failed with infrastructure errors.\n"
        f"Results: {results_path}\n"
    )


def test_cli_run_displays_safe_preparation_error(
    run_config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from evals import runner

    def missing_key(*args: object, **kwargs: object) -> Path:
        runner._resolve_api_key("EVAL_MISSING_TEST_KEY", role="user")
        pytest.fail("Missing key was accepted")

    monkeypatch.delenv("EVAL_MISSING_TEST_KEY", raising=False)
    monkeypatch.setattr(runner, "run_evaluation", missing_key)

    result = evaluate.main(["run", str(run_config_path)])

    assert result == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == (
        "error: user: API key environment variable EVAL_MISSING_TEST_KEY is missing or empty.\n"
    )
