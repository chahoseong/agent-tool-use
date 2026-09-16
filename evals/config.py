"""Validated evaluation settings loaded from TOML."""

import tomllib
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ConfigError(ValueError):
    """An evaluation configuration cannot be read or contains invalid settings."""


class _ConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


def _validate_setting_string(value: str) -> str:
    if not value or value != value.strip():
        raise ValueError("Expected a non-empty string without surrounding whitespace.")
    return value


def _default_max_steps() -> int:
    from tau2.config import DEFAULT_MAX_STEPS

    return DEFAULT_MAX_STEPS


def _default_max_errors() -> int:
    from tau2.config import DEFAULT_MAX_ERRORS

    return DEFAULT_MAX_ERRORS


class EvaluationOptions(_ConfigModel):
    """Evaluation conditions, including resolved official execution limits."""

    domain: str = "mock"
    task_ids: list[str] = Field(min_length=1)
    seed: int = Field(ge=0)
    max_steps: int = Field(default_factory=_default_max_steps, ge=1)
    max_errors: int = Field(default_factory=_default_max_errors, ge=1)
    num_trials: int = Field(default=1, ge=1)
    max_concurrency: int = Field(default=1, ge=1)

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        return _validate_setting_string(value)

    @field_validator("task_ids")
    @classmethod
    def validate_task_ids(cls, value: list[str]) -> list[str]:
        if any(not task_id.strip() for task_id in value):
            raise ValueError("Task IDs must not be empty or blank.")
        if len(set(value)) != len(value):
            raise ValueError("Task IDs must not contain duplicates.")
        return value


class _GenerationOptions(_ConfigModel):
    """Validate individual options without adding omitted values to requests."""

    temperature: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    top_p: float | None = Field(default=None, gt=0, le=1, allow_inf_nan=False)
    max_tokens: int | None = Field(default=None, ge=1)


class ModelOptions(_ConfigModel):
    """Server model ID and options; credentials remain environment references."""

    model: str
    base_url: str
    api_key_env: str | None = None
    generation: dict[Literal["temperature", "top_p", "max_tokens"], int | float] = (
        Field(default_factory=dict)
    )

    @field_validator("generation", mode="before")
    @classmethod
    def validate_generation_options(cls, value: object) -> dict[str, int | float]:
        return _GenerationOptions.model_validate(value).model_dump(exclude_unset=True)

    @field_validator("model", "base_url", "api_key_env")
    @classmethod
    def validate_connection_string(cls, value: str | None) -> str | None:
        return _validate_setting_string(value) if value is not None else None

    @field_validator("base_url")
    @classmethod
    def validate_server_url(cls, value: str) -> str:
        if any(
            character.isspace() or ord(character) < 32 or ord(character) == 127
            for character in value
        ):
            raise ValueError(
                "Server URL must not contain whitespace or control characters."
            )
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Expected an HTTP(S) URL with a host.")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("Credentials must not be embedded in the server URL.")
        # Reading port also rejects malformed and out-of-range port values.
        port = parsed.port
        if port is not None and not 0 <= port <= 65535:
            raise ValueError("Invalid server port.")
        return value


class OutputOptions(_ConfigModel):
    """Absolute parent directory for separate evaluation runs."""

    directory: Path = PROJECT_ROOT / "artifacts" / "evaluations"

    @field_validator("directory", mode="before")
    @classmethod
    def resolve_directory(cls, value: object) -> object:
        if isinstance(value, str):
            _validate_setting_string(value)
        if isinstance(value, (str, Path)):
            directory = Path(value)
            if directory.is_absolute():
                return directory
            if directory.anchor:
                raise ValueError(
                    "Expected a relative path or a complete absolute path."
                )
            return PROJECT_ROOT / directory
        return value


class ReflectionOptions(_ConfigModel):
    """Output review settings, separate from model generation options."""

    enabled: bool = False
    max_revisions: int = Field(default=2, ge=0)


class EvalConfig(_ConfigModel):
    """Evaluation settings shared by execution and metadata collection."""

    evaluation: EvaluationOptions
    agent: ModelOptions
    user: ModelOptions
    output: OutputOptions = Field(default_factory=OutputOptions)
    reflection: ReflectionOptions = Field(default_factory=ReflectionOptions)


def load_config(path: Path) -> EvalConfig:
    """Read and validate TOML settings without exposing input values."""
    try:
        with path.open("rb") as config_file:
            data = tomllib.load(config_file)
    except OSError:
        raise ConfigError("Cannot read configuration file.") from None
    except (tomllib.TOMLDecodeError, UnicodeDecodeError):
        raise ConfigError("Configuration file must contain valid UTF-8 TOML.") from None

    try:
        return EvalConfig.model_validate(data)
    except ValidationError as error:
        detail = error.errors(
            include_input=False, include_context=False, include_url=False
        )[0]
        setting_path = ".".join(str(part) for part in detail["loc"] if part != "[key]")
        if detail["type"] == "missing":
            message = f"Missing required setting: {setting_path}."
        elif detail["type"] in {"extra_forbidden", "literal_error"}:
            message = f"Unknown setting: {setting_path}."
        else:
            message = f"Invalid setting: {setting_path}."
        raise ConfigError(message) from None
