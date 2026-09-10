"""Preparation and execution of official mock evaluations."""

import os
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from pydantic import BaseModel, ValidationError

from evals.config import EvalConfig, ModelOptions

if TYPE_CHECKING:
    from tau2.data_model.simulation import TextRunConfig


def run_evaluation(config: EvalConfig, *, config_path: Path) -> Path:
    """Prepare a mock evaluation and return its official results file path.

    Preparation failures propagate before execution. Once execution starts,
    preserve metadata and any official checkpoints if it fails.
    """
    from tau2.runner import run_domain

    from evals.metadata import create_run_directory, write_metadata
    from evals.tasks import validate_task_ids

    validate_task_ids(config.evaluation.task_ids)
    _preflight_models(config)
    _register_task_agent()
    run_directory = create_run_directory(config.output.directory)
    write_metadata(run_directory, config=config, config_path=config_path)
    run_config = _build_run_config(config, run_directory)
    run_domain(run_config)
    return run_directory / "results.json"


def _register_task_agent() -> None:
    """Register our factory once, rejecting a name owned by another factory."""
    from tau2.registry import registry

    from agents.task_agent import create_task_agent

    existing = registry.get_agent_factory("task_agent")
    if existing is create_task_agent:
        return
    if existing is not None:
        raise ValueError(
            "Agent task_agent is already registered with a different factory."
        )
    registry.register_agent_factory(create_task_agent, "task_agent")


def _build_run_config(config: EvalConfig, run_directory: Path) -> "TextRunConfig":
    """Translate validated settings without resolving keys or starting evaluation."""
    from tau2.data_model.simulation import TextRunConfig

    return TextRunConfig.model_validate(
        {
            "domain": "mock",
            "task_set_name": "mock",
            "task_split_name": None,
            "task_ids": list(config.evaluation.task_ids),
            "agent": "task_agent",
            "user": "user_simulator",
            "llm_agent": f"openai/{config.agent.model}",
            "llm_user": f"openai/{config.user.model}",
            "llm_args_agent": _build_llm_args(config.agent),
            "llm_args_user": _build_llm_args(config.user),
            "seed": config.evaluation.seed,
            "num_trials": config.evaluation.num_trials,
            "max_concurrency": config.evaluation.max_concurrency,
            "max_steps": config.evaluation.max_steps,
            "max_errors": config.evaluation.max_errors,
            # run_domain appends results.json here, despite the field docs.
            "save_to": str(run_directory.resolve()),
        }
    )


def _build_llm_args(options: ModelOptions) -> dict[str, str | int | float]:
    """Keep credentials as LiteLLM environment references in recorded arguments."""
    return {
        **{key: value for key, value in options.generation.items()},
        "base_url": options.base_url,
        # A non-empty placeholder prevents fallback to unrelated SDK credentials.
        "api_key": (
            f"os.environ/{options.api_key_env}"
            if options.api_key_env is not None
            else "not-needed"
        ),
    }


class _ModelInfo(BaseModel):
    id: str


class _ModelsResponse(BaseModel):
    data: list[_ModelInfo]


def _preflight_models(config: EvalConfig) -> None:
    """Resolve both credentials before checking agent and user models in order."""
    agent_key = _resolve_api_key(config.agent.api_key_env, role="agent")
    user_key = _resolve_api_key(config.user.api_key_env, role="user")
    _check_model(config.agent, role="agent", api_key=agent_key)
    _check_model(config.user, role="user", api_key=user_key)


def _resolve_api_key(api_key_env: str | None, *, role: str) -> str | None:
    """Read the configured key without logging or modifying its value."""
    if api_key_env is None:
        return None
    key = os.environ.get(api_key_env)
    if not key:
        raise ValueError(
            f"{role}: API key environment variable {api_key_env} is missing or empty."
        )
    return key


def _check_model(options: ModelOptions, *, role: str, api_key: str | None) -> None:
    """Check model availability with a single request and safe error messages."""
    base_url = httpx.URL(options.base_url)
    url = base_url.copy_with(path=base_url.path.rstrip("/") + "/models")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key is not None else {}
    try:
        with httpx.Client(timeout=10.0, follow_redirects=False) as client:
            response = client.get(url, headers=headers)
    except httpx.TimeoutException:
        raise ValueError(f"{role}: Model check failed: request timed out.") from None
    except httpx.RequestError:
        raise ValueError(f"{role}: Model check failed: connection failed.") from None

    if response.status_code in {401, 403}:
        raise ValueError(f"{role}: Model check failed: authentication failed.")
    if not response.is_success:
        raise ValueError(
            f"{role}: Model check failed: server returned HTTP {response.status_code}."
        )
    try:
        models = _ModelsResponse.model_validate_json(response.content)
    except ValidationError:
        raise ValueError(
            f"{role}: Model check failed: invalid model list response."
        ) from None
    if not any(model.id == options.model for model in models.data):
        raise ValueError(
            f"{role}: Model check failed: configured model ID was not found."
        )
