"""Preparation and execution of official mock evaluations."""

import os

import httpx
from pydantic import BaseModel, ValidationError

from evals.config import EvalConfig, ModelOptions


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
