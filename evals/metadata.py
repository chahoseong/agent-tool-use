"""Run directories and metadata for evaluations."""

import subprocess
from datetime import datetime, timedelta, timezone
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from uuid import uuid4

import tomli_w

from evals.config import PROJECT_ROOT, EvalConfig

KST = timezone(timedelta(hours=9), name="KST")


def _git_output(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
    ).stdout.strip()


def _tau2_version_info() -> dict[str, str]:
    """Read the installed tau2 package version."""
    try:
        if version := distribution("tau2").version:
            return {"version": version}
    except (PackageNotFoundError, OSError, ValueError):
        pass
    return {"version_status": "unavailable"}


def _project_git_info() -> dict[str, str]:
    """Read the project commit without falling back to a parent repository."""
    if not (PROJECT_ROOT / ".git").exists():
        return {"status": "unavailable"}
    try:
        commit = _git_output(PROJECT_ROOT, "rev-parse", "--verify", "HEAD")
    except (OSError, subprocess.SubprocessError):
        return {"status": "unavailable"}
    return {"commit": commit}


def create_run_directory(parent: Path) -> Path:
    """Create a separate run directory named with Korean time and a short UUID."""
    parent = parent.resolve()
    parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(KST).strftime("%Y-%m-%d_%H-%M-%S_KST")
    while True:
        directory = parent / f"{timestamp}_{uuid4().hex[:8]}"
        try:
            directory.mkdir()
        except FileExistsError:
            continue
        return directory


def write_metadata(
    run_directory: Path, *, config: EvalConfig, config_path: Path
) -> None:
    """Record effective settings and run context without resolving credentials."""
    from agents import task_agent

    data = {
        "run": {
            "started_at": datetime.now(KST),
            "config_path": str(config_path.resolve()),
            "directory": str(run_directory.resolve()),
        },
        **config.model_dump(mode="json", exclude_none=True),
        "prompts": {"agent": task_agent.AGENT_PROMPT},
        "project": _project_git_info(),
        "tau2": _tau2_version_info(),
    }
    metadata_path = run_directory / "metadata.toml"
    metadata_file = metadata_path.open("xb")
    try:
        with metadata_file:
            tomli_w.dump(data, metadata_file)
    except BaseException:
        metadata_path.unlink()
        raise
