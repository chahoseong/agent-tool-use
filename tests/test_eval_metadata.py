"""Verify separate output directories for evaluation runs."""

import re
import subprocess
import tomllib
from datetime import UTC, datetime, tzinfo
from importlib.metadata import PackageNotFoundError, PathDistribution
from pathlib import Path
from typing import BinaryIO, Self
from uuid import UUID

import pytest

from evals import metadata as metadata_module
from evals.config import EvalConfig


@pytest.fixture
def fixed_run_time(monkeypatch: pytest.MonkeyPatch) -> None:
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> Self:
            return cls(2026, 9, 10, 18, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(metadata_module, "datetime", FixedDatetime, raising=False)


def test_run_directories_keep_each_run_separate_with_korean_time_names(
    tmp_path: Path,
    fixed_run_time: None,
) -> None:
    parent = tmp_path / "artifacts" / "evaluations"

    first = metadata_module.create_run_directory(parent)
    saved_result = first / "results.json"
    saved_result.write_text("existing result", encoding="utf-8")
    second = metadata_module.create_run_directory(parent)

    assert first != second
    for directory in (first, second):
        assert directory.is_dir()
        assert directory.is_absolute()
        assert directory.parent == parent
        assert re.fullmatch(r"2026-09-11_03-00-00_KST_[0-9a-f]{8}", directory.name)
    assert saved_result.read_text(encoding="utf-8") == "existing result"


def test_run_directory_retries_name_collision_without_overwriting_existing_files(
    tmp_path: Path,
    fixed_run_time: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = tmp_path / "2026-09-11_03-00-00_KST_aaaaaaaa"
    existing.mkdir()
    saved_result = existing / "results.json"
    saved_result.write_text("existing result", encoding="utf-8")
    identifiers = iter([UUID("a" * 32), UUID("b" * 32)])
    monkeypatch.setattr(
        metadata_module, "uuid4", lambda: next(identifiers), raising=False
    )

    directory = metadata_module.create_run_directory(tmp_path)

    assert directory == tmp_path / "2026-09-11_03-00-00_KST_bbbbbbbb"
    assert directory.is_dir()
    assert saved_result.read_text(encoding="utf-8") == "existing result"


def test_run_directory_propagates_creation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_mkdir = Path.mkdir
    failure = PermissionError("Run directory creation denied")

    def denied_mkdir(
        path: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        if path.parent == tmp_path:
            raise failure
        original_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", denied_mkdir)

    with pytest.raises(PermissionError) as error:
        metadata_module.create_run_directory(tmp_path)

    assert error.value is failure


@pytest.fixture
def metadata_config() -> EvalConfig:
    return EvalConfig.model_validate(
        {
            "evaluation": {"task_ids": ["create_task_1"], "seed": 42},
            "agent": {
                "model": "agent-model",
                "base_url": "http://localhost:8080/v1",
                "api_key_env": "EVAL_METADATA_TEST_KEY",
                "generation": {"temperature": 0.0, "max_tokens": 256},
            },
            "user": {
                "model": "user-model",
                "base_url": "http://localhost:8081/v1",
            },
        }
    )


def test_metadata_records_effective_settings_and_run_context_without_api_key_values(
    tmp_path: Path,
    fixed_run_time: None,
    monkeypatch: pytest.MonkeyPatch,
    metadata_config: EvalConfig,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EVAL_METADATA_TEST_KEY", "test-only-secret-value")
    run_directory = Path("run")
    run_directory.mkdir()
    config_path = Path("evaluation.toml")
    config_path.write_text("# source configuration", encoding="utf-8")

    metadata_module.write_metadata(
        run_directory, config=metadata_config, config_path=config_path
    )

    contents = (run_directory / "metadata.toml").read_text(encoding="utf-8")
    recorded = tomllib.loads(contents)
    assert recorded["run"] == {
        "started_at": datetime(2026, 9, 10, 18, tzinfo=UTC),
        "config_path": str(config_path.resolve()),
        "directory": str(run_directory.resolve()),
    }
    assert recorded["run"]["started_at"].utcoffset() == metadata_module.KST.utcoffset(
        None
    )
    assert recorded["evaluation"] == {
        "task_ids": ["create_task_1"],
        "seed": 42,
        "max_steps": metadata_config.evaluation.max_steps,
        "max_errors": metadata_config.evaluation.max_errors,
        "num_trials": 1,
        "max_concurrency": 1,
    }
    assert recorded["agent"] == {
        "model": "agent-model",
        "base_url": "http://localhost:8080/v1",
        "api_key_env": "EVAL_METADATA_TEST_KEY",
        "generation": {"temperature": 0.0, "max_tokens": 256},
    }
    assert recorded["user"] == {
        "model": "user-model",
        "base_url": "http://localhost:8081/v1",
        "generation": {},
    }
    assert recorded["output"] == {"directory": str(metadata_config.output.directory)}
    assert "test-only-secret-value" not in contents


def test_metadata_preserves_current_agent_prompt_text(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    metadata_config: EvalConfig,
) -> None:
    from agents import task_agent

    prompt = '사용자를 도와주세요.\n\n도구 사용 전 "정책"을 확인하세요.\r\n경로: C:\\tasks\\new'
    monkeypatch.setattr(task_agent, "AGENT_PROMPT", prompt)

    metadata_module.write_metadata(
        tmp_path, config=metadata_config, config_path=tmp_path / "evaluation.toml"
    )

    with (tmp_path / "metadata.toml").open("rb") as metadata_file:
        recorded = tomllib.load(metadata_file)
    assert recorded["prompts"]["agent"] == prompt


@pytest.fixture
def project_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repository = tmp_path / "project"
    repository.mkdir()
    subprocess.run(
        ["git", "init", "--quiet", "--template="],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    (repository / "tracked.txt").write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repository, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Metadata Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "-m",
            "Test baseline",
        ],
        cwd=repository,
        check=True,
        capture_output=True,
    )
    monkeypatch.setattr(metadata_module, "PROJECT_ROOT", repository, raising=False)
    return repository


def test_metadata_records_project_commit_from_project_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    project_repository: Path,
    metadata_config: EvalConfig,
) -> None:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    monkeypatch.chdir(tmp_path)

    metadata_module.write_metadata(
        run_directory, config=metadata_config, config_path=tmp_path / "evaluation.toml"
    )

    recorded = tomllib.loads(
        (run_directory / "metadata.toml").read_text(encoding="utf-8")
    )
    assert recorded["project"] == {"commit": commit}


@pytest.mark.parametrize("failure", ["no_repository", "git_unavailable"])
def test_metadata_marks_project_version_unavailable_when_git_cannot_be_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    project_repository: Path,
    metadata_config: EvalConfig,
    failure: str,
) -> None:
    if failure == "no_repository":
        monkeypatch.setattr(metadata_module, "PROJECT_ROOT", tmp_path)
    else:

        def unavailable_git(
            *args: object, **kwargs: object
        ) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError("Git executable unavailable")

        monkeypatch.setattr(metadata_module.subprocess, "run", unavailable_git)

    metadata_module.write_metadata(
        tmp_path, config=metadata_config, config_path=tmp_path / "evaluation.toml"
    )

    recorded = tomllib.loads((tmp_path / "metadata.toml").read_text(encoding="utf-8"))
    assert recorded["project"] == {"status": "unavailable"}


@pytest.fixture
def tau2_distribution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    location = tmp_path / "tau2-1.2.3.dist-info"
    location.mkdir()
    (location / "METADATA").write_text("Name: tau2\nVersion: 1.2.3\n", encoding="utf-8")
    monkeypatch.setattr(
        metadata_module,
        "distribution",
        lambda name: PathDistribution(location),
        raising=False,
    )
    return location


def test_metadata_records_installed_tau2_version(
    tmp_path: Path,
    tau2_distribution: Path,
    metadata_config: EvalConfig,
) -> None:
    metadata_module.write_metadata(
        tmp_path, config=metadata_config, config_path=tmp_path / "evaluation.toml"
    )

    recorded = tomllib.loads((tmp_path / "metadata.toml").read_text(encoding="utf-8"))
    assert recorded["tau2"] == {"version": "1.2.3"}


def test_metadata_marks_tau2_version_unavailable_without_package_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    metadata_config: EvalConfig,
) -> None:
    def missing_distribution(name: str) -> PathDistribution:
        raise PackageNotFoundError(name)

    monkeypatch.setattr(
        metadata_module, "distribution", missing_distribution, raising=False
    )

    metadata_module.write_metadata(
        tmp_path, config=metadata_config, config_path=tmp_path / "evaluation.toml"
    )

    recorded = tomllib.loads((tmp_path / "metadata.toml").read_text(encoding="utf-8"))
    assert recorded["tau2"] == {
        "version_status": "unavailable",
    }


def test_metadata_removes_incomplete_file_when_writing_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    metadata_config: EvalConfig,
) -> None:
    failure = OSError("Metadata write failed")

    def interrupted_dump(data: object, output: BinaryIO) -> None:
        output.write(b"[run]\nstarted_at = ")
        output.flush()
        raise failure

    monkeypatch.setattr(metadata_module.tomli_w, "dump", interrupted_dump)

    with pytest.raises(OSError) as error:
        metadata_module.write_metadata(
            tmp_path, config=metadata_config, config_path=tmp_path / "evaluation.toml"
        )

    assert error.value is failure
    assert not (tmp_path / "metadata.toml").exists()


@pytest.mark.parametrize("existing_path", ["file", "directory"])
def test_metadata_propagates_write_failure_without_overwriting_existing_path(
    tmp_path: Path,
    metadata_config: EvalConfig,
    existing_path: str,
) -> None:
    metadata_path = tmp_path / "metadata.toml"
    if existing_path == "file":
        metadata_path.write_text("existing metadata", encoding="utf-8")
    else:
        metadata_path.mkdir()

    with pytest.raises(OSError):
        metadata_module.write_metadata(
            tmp_path, config=metadata_config, config_path=tmp_path / "evaluation.toml"
        )

    if existing_path == "file":
        assert metadata_path.read_text(encoding="utf-8") == "existing metadata"
    else:
        assert metadata_path.is_dir()
