"""Verify evaluation settings loaded from TOML files."""

import json
import sys
from pathlib import Path

import pytest
from tau2.config import DEFAULT_MAX_ERRORS, DEFAULT_MAX_STEPS

from evals import config as config_module


@pytest.fixture
def toml_sections() -> dict[str, dict[str, str]]:
    """Return fresh valid sections with values expressed as TOML literals."""
    return {
        "evaluation": {"task_ids": '["create_task_1"]', "seed": "42"},
        "agent": {
            "model": '"agent-model"',
            "base_url": '"http://localhost:8080/v1"',
        },
        "user": {
            "model": '"user-model"',
            "base_url": '"http://localhost:8081/v1"',
        },
    }


def write_toml_config(
    path: Path, sections: dict[str, dict[str, str]], *, prefix: str = ""
) -> None:
    """Write literal values unchanged; prefix holds any top-level settings."""
    contents = prefix + "\n\n".join(
        f"[{name}]\n" + "\n".join(f"{key} = {value}" for key, value in fields.items())
        for name, fields in sections.items()
    )
    path.write_text(contents, encoding="utf-8")


def test_config_applies_defaults_when_only_required_settings_are_provided(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "evaluation.toml"
    config_path.write_text(
        """
[evaluation]
task_ids = ["create_task_1"]
seed = 42

[agent]
model = "agent-model"
base_url = "http://localhost:8080/v1"

[user]
model = "user-model"
base_url = "http://localhost:8081/v1"
""",
        encoding="utf-8",
    )

    config = config_module.load_config(config_path)

    assert config.evaluation.task_ids == ["create_task_1"]
    assert config.evaluation.domain == "mock"
    assert config.evaluation.seed == 42
    assert config.evaluation.num_trials == 1
    assert config.evaluation.max_concurrency == 1
    assert config.evaluation.max_steps == DEFAULT_MAX_STEPS
    assert config.evaluation.max_errors == DEFAULT_MAX_ERRORS
    assert config.agent.model == "agent-model"
    assert config.agent.base_url == "http://localhost:8080/v1"
    assert config.user.model == "user-model"
    assert config.user.base_url == "http://localhost:8081/v1"
    assert config.agent.api_key_env is None
    assert config.user.api_key_env is None
    assert config.agent.generation == {}
    assert config.user.generation == {}
    project_root = Path(__file__).resolve().parents[1]
    assert config.output.directory == project_root / "artifacts" / "evaluations"


def test_config_preserves_explicit_evaluation_and_model_options(tmp_path: Path) -> None:
    config_path = tmp_path / "evaluation.toml"
    config_path.write_text(
        """
[evaluation]
domain = "retail"
task_ids = ["create_task_1", "update_task_1"]
seed = 73
num_trials = 3
max_concurrency = 2
max_steps = 45
max_errors = 4

[agent]
model = "agent-model"
base_url = "http://localhost:8080/v1"
api_key_env = "AGENT_API_KEY"

[agent.generation]
temperature = 0.0
top_p = 0.9
max_tokens = 256

[user]
model = "user-model"
base_url = "http://localhost:8081/v1"
api_key_env = "USER_API_KEY"

[user.generation]
temperature = 0.7
top_p = 0.8
max_tokens = 128
""",
        encoding="utf-8",
    )

    config = config_module.load_config(config_path)

    assert config.evaluation.domain == "retail"
    assert config.evaluation.task_ids == ["create_task_1", "update_task_1"]
    assert config.evaluation.seed == 73
    assert config.evaluation.num_trials == 3
    assert config.evaluation.max_concurrency == 2
    assert config.evaluation.max_steps == 45
    assert config.evaluation.max_errors == 4
    assert config.agent.api_key_env == "AGENT_API_KEY"
    assert config.agent.generation == {
        "temperature": 0.0,
        "top_p": 0.9,
        "max_tokens": 256,
    }
    assert config.user.api_key_env == "USER_API_KEY"
    assert config.user.generation == {
        "temperature": 0.7,
        "top_p": 0.8,
        "max_tokens": 128,
    }


@pytest.mark.parametrize("path_kind", ["relative", "absolute"])
def test_config_resolves_output_directory_from_project_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path_kind: str
) -> None:
    project_root = Path(__file__).resolve().parents[1]
    configured_directory = (
        Path("custom results") / "evaluations"
        if path_kind == "relative"
        else tmp_path / "absolute results"
    )
    expected_directory = (
        project_root / configured_directory
        if path_kind == "relative"
        else configured_directory
    )
    config_directory = tmp_path / "configs"
    config_directory.mkdir()
    working_directory = tmp_path / "working"
    working_directory.mkdir()
    config_path = config_directory / "evaluation.toml"
    config_path.write_text(
        f"""
[evaluation]
task_ids = ["create_task_1"]
seed = 42

[agent]
model = "agent-model"
base_url = "http://localhost:8080/v1"

[user]
model = "user-model"
base_url = "http://localhost:8081/v1"

[output]
directory = '{configured_directory.as_posix()}'
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(working_directory)

    config = config_module.load_config(config_path)

    assert config.output.directory == expected_directory
    assert config.output.directory.is_absolute()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows path semantics")
@pytest.mark.parametrize("directory", ["D:results", r"\results"])
def test_config_rejects_incomplete_windows_output_path(
    tmp_path: Path, toml_sections: dict[str, dict[str, str]], directory: str
) -> None:
    toml_sections["output"] = {"directory": json.dumps(directory)}
    config_path = tmp_path / "evaluation.toml"
    write_toml_config(config_path, toml_sections)

    with pytest.raises(config_module.ConfigError) as error:
        config_module.load_config(config_path)

    assert str(error.value) == "Invalid setting: output.directory."


@pytest.mark.parametrize("path_kind", ["missing", "directory"])
def test_config_reports_read_failure_when_file_is_unreadable(
    tmp_path: Path, path_kind: str
) -> None:
    config_path = tmp_path / "evaluation.toml"
    if path_kind == "directory":
        config_path.mkdir()

    with pytest.raises(
        config_module.ConfigError, match="Cannot read configuration file"
    ):
        config_module.load_config(config_path)


@pytest.mark.parametrize(
    "contents",
    [b'private_setting = "sensitive-value"\n[broken', b'private_setting = "\xff"'],
    ids=["invalid_toml", "invalid_utf8"],
)
def test_config_reports_invalid_toml_without_exposing_file_contents(
    tmp_path: Path, contents: bytes
) -> None:
    config_path = tmp_path / "evaluation.toml"
    config_path.write_bytes(contents)

    with pytest.raises(config_module.ConfigError) as error:
        config_module.load_config(config_path)

    assert str(error.value) == "Configuration file must contain valid UTF-8 TOML."


@pytest.mark.parametrize(
    "missing_path",
    [
        "evaluation",
        "agent",
        "user",
        "evaluation.task_ids",
        "evaluation.seed",
        "agent.model",
        "agent.base_url",
        "user.model",
        "user.base_url",
    ],
)
def test_config_identifies_missing_required_setting(
    tmp_path: Path, toml_sections: dict[str, dict[str, str]], missing_path: str
) -> None:
    section, separator, field = missing_path.partition(".")
    if separator:
        del toml_sections[section][field]
    else:
        del toml_sections[section]
    config_path = tmp_path / "evaluation.toml"
    write_toml_config(config_path, toml_sections)

    with pytest.raises(config_module.ConfigError) as error:
        config_module.load_config(config_path)

    assert str(error.value) == f"Missing required setting: {missing_path}."


@pytest.mark.parametrize(
    "unknown_path",
    [
        "unexpected",
        "evaluation.num_trails",
        "agent.api_key",
        "user.provider",
        "output.path",
        "agent.generation.temprature",
        "user.generation.seed",
    ],
)
def test_config_rejects_unknown_setting_with_its_path(
    tmp_path: Path, toml_sections: dict[str, dict[str, str]], unknown_path: str
) -> None:
    section, separator, name = unknown_path.rpartition(".")
    prefix = ""
    if separator:
        toml_sections.setdefault(section, {})[name] = '"unexpected-value"'
    else:
        prefix = 'unexpected = "unexpected-value"\n'
    config_path = tmp_path / "evaluation.toml"
    write_toml_config(config_path, toml_sections, prefix=prefix)

    with pytest.raises(config_module.ConfigError) as error:
        config_module.load_config(config_path)

    assert str(error.value) == f"Unknown setting: {unknown_path}."


@pytest.mark.parametrize("seed_value", ['"42"', "true", "42.0"])
def test_config_rejects_wrong_type_without_coercing_or_exposing_input(
    tmp_path: Path, toml_sections: dict[str, dict[str, str]], seed_value: str
) -> None:
    toml_sections["evaluation"]["seed"] = seed_value
    config_path = tmp_path / "evaluation.toml"
    write_toml_config(config_path, toml_sections)

    with pytest.raises(config_module.ConfigError) as error:
        config_module.load_config(config_path)
    assert str(error.value) == "Invalid setting: evaluation.seed."


@pytest.mark.parametrize(
    ("field_name", "minimum"),
    [
        ("seed", 0),
        ("num_trials", 1),
        ("max_concurrency", 1),
        ("max_steps", 1),
        ("max_errors", 1),
    ],
)
def test_config_accepts_evaluation_integer_at_lower_bound(
    tmp_path: Path,
    toml_sections: dict[str, dict[str, str]],
    field_name: str,
    minimum: int,
) -> None:
    toml_sections["evaluation"][field_name] = str(minimum)
    config_path = tmp_path / "evaluation.toml"
    write_toml_config(config_path, toml_sections)

    config = config_module.load_config(config_path)

    assert getattr(config.evaluation, field_name) == minimum


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("seed", -1),
        ("num_trials", 0),
        ("max_concurrency", 0),
        ("max_steps", 0),
        ("max_errors", 0),
    ],
)
def test_config_rejects_evaluation_integer_below_lower_bound(
    tmp_path: Path,
    toml_sections: dict[str, dict[str, str]],
    field_name: str,
    value: int,
) -> None:
    toml_sections["evaluation"][field_name] = str(value)
    config_path = tmp_path / "evaluation.toml"
    write_toml_config(config_path, toml_sections)

    with pytest.raises(config_module.ConfigError) as error:
        config_module.load_config(config_path)

    assert str(error.value) == f"Invalid setting: evaluation.{field_name}."


@pytest.mark.parametrize(
    ("setting_path", "value"),
    [
        ("agent.model", ""),
        ("agent.model", " \t"),
        ("agent.model", " model"),
        ("agent.model", "model "),
        ("evaluation.domain", ""),
        ("evaluation.domain", " retail"),
        ("user.model", " model "),
        ("agent.base_url", " http://localhost:8080/v1"),
        ("user.base_url", "http://localhost:8081/v1 "),
        ("agent.api_key_env", ""),
        ("user.api_key_env", " KEY "),
        ("output.directory", " results "),
        ("output.directory", ""),
    ],
)
def test_config_rejects_empty_or_untrimmed_string_setting(
    tmp_path: Path,
    toml_sections: dict[str, dict[str, str]],
    setting_path: str,
    value: str,
) -> None:
    section, name = setting_path.split(".")
    toml_sections.setdefault(section, {})[name] = json.dumps(value)
    config_path = tmp_path / "evaluation.toml"
    write_toml_config(config_path, toml_sections)

    with pytest.raises(config_module.ConfigError) as error:
        config_module.load_config(config_path)

    assert str(error.value) == f"Invalid setting: {setting_path}."


@pytest.mark.parametrize("setting", ["task_set", "task_split"])
def test_config_rejects_removed_task_scope_setting(
    tmp_path: Path,
    toml_sections: dict[str, dict[str, str]],
    setting: str,
) -> None:
    toml_sections["evaluation"][setting] = '"retail"'
    config_path = tmp_path / "evaluation.toml"
    write_toml_config(config_path, toml_sections)

    with pytest.raises(config_module.ConfigError) as error:
        config_module.load_config(config_path)

    assert str(error.value) == f"Unknown setting: evaluation.{setting}."


@pytest.mark.parametrize(
    ("role", "base_url"),
    [
        ("agent", "ftp://localhost/v1"),
        ("agent", "localhost:8080/v1"),
        ("agent", "http:///v1"),
        ("agent", "http://:8080/v1"),
        ("user", "https://username@localhost/v1"),
        ("user", "https://username:password@localhost/v1"),
        ("user", "http://[invalid/v1"),
        ("agent", "http://localhost:invalid/v1"),
        ("agent", "http://local\x00host/v1"),
        ("user", "http://localhost/v1\x7f"),
    ],
)
def test_config_rejects_invalid_server_url_without_exposing_credentials(
    tmp_path: Path, toml_sections: dict[str, dict[str, str]], role: str, base_url: str
) -> None:
    toml_sections[role]["base_url"] = json.dumps(base_url)
    config_path = tmp_path / "evaluation.toml"
    write_toml_config(config_path, toml_sections)

    with pytest.raises(config_module.ConfigError) as error:
        config_module.load_config(config_path)
    assert str(error.value) == f"Invalid setting: {role}.base_url."


def test_config_preserves_https_server_url_with_custom_api_path(tmp_path: Path) -> None:
    config_path = tmp_path / "evaluation.toml"
    config_path.write_text(
        """
[evaluation]
task_ids = ["create_task_1"]
seed = 42
[agent]
model = "agent-model"
base_url = "https://localhost:8443/custom/api/"
[user]
model = "user-model"
base_url = "http://localhost:8080"
""",
        encoding="utf-8",
    )
    config = config_module.load_config(config_path)
    assert config.agent.base_url == "https://localhost:8443/custom/api/"
    assert config.user.base_url == "http://localhost:8080"


@pytest.mark.parametrize(
    "task_ids",
    [[], [""], [" \t"], ["create_task_1", "create_task_1"]],
    ids=["empty_list", "empty_id", "blank_id", "duplicate_id"],
)
def test_config_rejects_empty_or_duplicate_task_selection(
    tmp_path: Path, toml_sections: dict[str, dict[str, str]], task_ids: list[str]
) -> None:
    toml_sections["evaluation"]["task_ids"] = json.dumps(task_ids)
    config_path = tmp_path / "evaluation.toml"
    write_toml_config(config_path, toml_sections)

    with pytest.raises(config_module.ConfigError) as error:
        config_module.load_config(config_path)
    assert str(error.value) == "Invalid setting: evaluation.task_ids."


def test_config_preserves_task_ids_without_imposing_a_name_format(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "evaluation.toml"
    config_path.write_text(
        """
[evaluation]
task_ids = ["123", "arbitrary/id", "not_a_known_task"]
seed = 42
[agent]
model = "agent-model"
base_url = "http://localhost:8080/v1"
[user]
model = "user-model"
base_url = "http://localhost:8081/v1"
""",
        encoding="utf-8",
    )
    config = config_module.load_config(config_path)
    assert config.evaluation.task_ids == ["123", "arbitrary/id", "not_a_known_task"]


def test_config_preserves_domain_selection_without_imposing_a_name_format(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "evaluation.toml"
    config_path.write_text(
        """
[evaluation]
domain = "custom-domain"
task_ids = ["selected-task"]
seed = 42
[agent]
model = "agent-model"
base_url = "http://localhost:8080/v1"
[user]
model = "user-model"
base_url = "http://localhost:8081/v1"
""",
        encoding="utf-8",
    )

    config = config_module.load_config(config_path)

    assert config.evaluation.domain == "custom-domain"


@pytest.mark.parametrize(
    ("option", "literal", "expected"),
    [
        ("temperature", "0.0", 0.0),
        ("top_p", "1.0", 1.0),
        ("max_tokens", "1", 1),
    ],
)
def test_config_preserves_specified_generation_option(
    tmp_path: Path,
    toml_sections: dict[str, dict[str, str]],
    option: str,
    literal: str,
    expected: float,
) -> None:
    toml_sections["user.generation"] = {option: literal}
    config_path = tmp_path / "evaluation.toml"
    write_toml_config(config_path, toml_sections)

    config = config_module.load_config(config_path)

    assert config.user.generation == {option: expected}
    assert config.agent.generation == {}


@pytest.mark.parametrize(
    ("option", "literal"),
    [
        ("temperature", "-0.1"),
        ("temperature", "nan"),
        ("temperature", "inf"),
        ("temperature", "true"),
        ("top_p", "0.0"),
        ("top_p", "1.1"),
        ("top_p", "nan"),
        ("max_tokens", "0"),
        ("max_tokens", "1.5"),
        ("max_tokens", "true"),
    ],
)
def test_config_rejects_invalid_generation_option_value(
    tmp_path: Path,
    toml_sections: dict[str, dict[str, str]],
    option: str,
    literal: str,
) -> None:
    toml_sections["user.generation"] = {option: literal}
    config_path = tmp_path / "evaluation.toml"
    write_toml_config(config_path, toml_sections)

    with pytest.raises(config_module.ConfigError) as error:
        config_module.load_config(config_path)

    assert str(error.value) == f"Invalid setting: user.generation.{option}."
