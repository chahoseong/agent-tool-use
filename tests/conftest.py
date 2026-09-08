"""Prepare the local tau2 environment before test modules import it."""

from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Set test-only environment variables and restore them after the session."""
    environment = pytest.MonkeyPatch()
    config.add_cleanup(environment.undo)
    project_root = Path(__file__).resolve().parents[1]
    environment.setenv(
        "TAU2_DATA_DIR", str(project_root.parent / "tau2-bench" / "data")
    )
    environment.setenv("LITELLM_LOCAL_MODEL_COST_MAP", "True")
