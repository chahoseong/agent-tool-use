"""Verify preparation for official mock evaluation runs."""

import tomllib
from collections.abc import Callable
from importlib import import_module
from pathlib import Path

import httpx
import pytest

from evals import runner as runner_module
from evals.config import EvalConfig, ModelOptions


def test_registered_task_agent_supports_repeated_official_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tau2.domains.mock.environment import get_environment
    from tau2.registry import Registry
    from tau2.runner.build import build_agent

    from agents.task_agent import TaskAgent

    registry = Registry()
    monkeypatch.setattr(import_module("tau2.registry"), "registry", registry)
    monkeypatch.setattr(import_module("tau2.runner.build"), "registry", registry)
    environment = get_environment()
    llm_args = {"base_url": "http://localhost:8080/v1", "temperature": 0.2}

    for _ in range(2):
        runner_module._register_task_agent()
        agent = build_agent(
            "task_agent", environment, llm="openai/test-model", llm_args=llm_args
        )

        assert isinstance(agent, TaskAgent)
        assert agent.llm == "openai/test-model"
        assert agent.llm_args == llm_args
        assert agent.domain_policy == environment.get_policy()
        assert [tool.openai_schema for tool in agent.tools] == [
            tool.openai_schema for tool in environment.get_tools()
        ]


def test_task_agent_registration_rejects_name_owned_by_another_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tau2.registry import Registry

    registry = Registry()
    monkeypatch.setattr(import_module("tau2.registry"), "registry", registry)

    def other_factory() -> None:
        pass

    registry.register_agent_factory(other_factory, "task_agent")

    with pytest.raises(ValueError, match="task_agent.*different factory"):
        runner_module._register_task_agent()

    assert registry.get_agent_factory("task_agent") is other_factory


@pytest.mark.parametrize(
    "authenticated", [True, False], ids=["with_keys", "without_keys"]
)
def test_run_config_maps_evaluation_settings_to_official_mock_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    authenticated: bool,
) -> None:
    from tau2.data_model.simulation import TextRunConfig

    monkeypatch.setenv("EVAL_TEST_AGENT_KEY", "private-agent-key")
    monkeypatch.setenv("EVAL_TEST_USER_KEY", "private-user-key")
    monkeypatch.setenv("OPENAI_API_KEY", "unrelated-private-key")
    config = EvalConfig.model_validate(
        {
            "evaluation": {
                "task_ids": ["second_task", "first_task"],
                "seed": 73,
                "num_trials": 3,
                "max_concurrency": 2,
                "max_steps": 25,
                "max_errors": 4,
            },
            "agent": {
                "model": "org/agent-model",
                "base_url": "http://localhost:8080/v1",
                "api_key_env": "EVAL_TEST_AGENT_KEY" if authenticated else None,
                "generation": {"temperature": 0.2, "top_p": 0.8, "max_tokens": 256},
            },
            "user": {
                "model": "user-model",
                "base_url": "http://localhost:8081/v1",
                "api_key_env": "EVAL_TEST_USER_KEY" if authenticated else None,
            },
        }
    )
    original_config = config.model_dump()
    run_directory = tmp_path / "run"

    result = runner_module._build_run_config(config, run_directory)

    assert isinstance(result, TextRunConfig)
    assert result.domain == "mock"
    assert result.task_set_name == "mock"
    assert result.task_split_name is None
    assert result.num_tasks is None
    assert result.task_ids == ["second_task", "first_task"]
    assert result.seed == 73
    assert result.num_trials == 3
    assert result.max_concurrency == 2
    assert result.max_steps == 25
    assert result.max_errors == 4
    assert result.agent == "task_agent"
    assert result.user == "user_simulator"
    assert result.llm_agent == "openai/org/agent-model"
    assert result.llm_user == "openai/user-model"
    assert result.llm_args_agent == {
        "base_url": "http://localhost:8080/v1",
        "api_key": "os.environ/EVAL_TEST_AGENT_KEY" if authenticated else "not-needed",
        "temperature": 0.2,
        "top_p": 0.8,
        "max_tokens": 256,
    }
    assert result.llm_args_user == {
        "base_url": "http://localhost:8081/v1",
        "api_key": "os.environ/EVAL_TEST_USER_KEY" if authenticated else "not-needed",
    }
    assert result.save_to == str(run_directory.resolve())
    assert config.model_dump() == original_config


def test_authentication_returns_no_key_when_environment_variable_is_unspecified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "unused-test-key")

    key = runner_module._resolve_api_key(None, role="agent")

    assert key is None


def test_authentication_returns_configured_key_without_logging_it(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    test_key = "test-only-api-key"
    monkeypatch.setenv("EVAL_TEST_API_KEY", test_key)

    key = runner_module._resolve_api_key("EVAL_TEST_API_KEY", role="user")

    assert key == test_key
    captured = capsys.readouterr()
    assert test_key not in captured.out + captured.err + caplog.text


@pytest.mark.parametrize(
    ("role", "value"),
    [("agent", None), ("user", "")],
    ids=["missing_variable", "empty_variable"],
)
def test_authentication_reports_role_when_configured_key_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, role: str, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("EVAL_TEST_API_KEY", raising=False)
    else:
        monkeypatch.setenv("EVAL_TEST_API_KEY", value)

    with pytest.raises(ValueError) as error:
        runner_module._resolve_api_key("EVAL_TEST_API_KEY", role=role)

    assert str(error.value) == (
        f"{role}: API key environment variable EVAL_TEST_API_KEY is missing or empty."
    )


@pytest.fixture
def mock_http(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Callable[[httpx.Request], httpx.Response]], list[httpx.Request]]:
    def install(
        handler: Callable[[httpx.Request], httpx.Response],
    ) -> list[httpx.Request]:
        requests: list[httpx.Request] = []

        def handle_request(
            transport: httpx.HTTPTransport, request: httpx.Request
        ) -> httpx.Response:
            requests.append(request)
            return handler(request)

        monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle_request)
        return requests

    return install


@pytest.mark.parametrize("api_key", [None, "test-only-key"])
def test_model_check_accepts_available_model_with_configured_request_options(
    mock_http: Callable,
    api_key: str | None,
) -> None:
    requests = mock_http(
        lambda request: httpx.Response(
            200,
            json={"data": [{"id": "other"}, {"id": "org/model", "object": "model"}]},
        )
    )
    options = ModelOptions(
        model="org/model", base_url="http://localhost:8080/custom/v1/"
    )

    runner_module._check_model(options, role="agent", api_key=api_key)

    assert len(requests) == 1
    request = requests[0]
    assert request.method == "GET"
    assert str(request.url) == "http://localhost:8080/custom/v1/models"
    assert request.headers.get("authorization") == (
        f"Bearer {api_key}" if api_key is not None else None
    )
    assert request.extensions["timeout"] == {
        "connect": 10.0,
        "read": 10.0,
        "write": 10.0,
        "pool": 10.0,
    }


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (401, "authentication failed"),
        (403, "authentication failed"),
        (500, "server returned HTTP 500"),
        (302, "server returned HTTP 302"),
    ],
)
def test_model_check_reports_http_failure_without_exposing_response(
    mock_http: Callable,
    status: int,
    reason: str,
) -> None:
    requests = mock_http(
        lambda request: httpx.Response(
            status,
            text="private-server-body",
            headers={"location": "http://other/models"},
        )
    )
    options = ModelOptions(model="model", base_url="http://localhost/v1")

    with pytest.raises(ValueError) as error:
        runner_module._check_model(options, role="user", api_key="test-only-key")

    assert str(error.value) == f"user: Model check failed: {reason}."
    assert len(requests) == 1


@pytest.mark.parametrize(
    ("exception", "reason"),
    [
        (httpx.ReadTimeout, "request timed out"),
        (httpx.ConnectError, "connection failed"),
    ],
)
def test_model_check_reports_transport_failure_without_retrying(
    mock_http: Callable,
    exception: type[httpx.RequestError],
    reason: str,
) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise exception("private-key-in-transport-error", request=request)

    requests = mock_http(fail)
    options = ModelOptions(model="model", base_url="http://localhost/v1")

    with pytest.raises(ValueError) as error:
        runner_module._check_model(options, role="agent", api_key=None)

    assert str(error.value) == f"agent: Model check failed: {reason}."
    assert error.value.__suppress_context__
    assert len(requests) == 1


@pytest.mark.parametrize(
    "body",
    [b"private-invalid-json", b'{"data": {}}', b'{"data": [{"id": 12}]}'],
    ids=["invalid_json", "invalid_list", "invalid_id"],
)
def test_model_check_rejects_invalid_model_list_without_exposing_body(
    mock_http: Callable,
    body: bytes,
) -> None:
    mock_http(lambda request: httpx.Response(200, content=body))
    options = ModelOptions(model="model", base_url="http://localhost/v1")

    with pytest.raises(ValueError) as error:
        runner_module._check_model(options, role="user", api_key=None)

    assert str(error.value) == "user: Model check failed: invalid model list response."


def test_model_check_rejects_model_without_exact_id_match(mock_http: Callable) -> None:
    mock_http(
        lambda request: httpx.Response(200, json={"data": [{"id": "model-extra"}]})
    )
    options = ModelOptions(model="model", base_url="http://localhost/v1")

    with pytest.raises(ValueError) as error:
        runner_module._check_model(options, role="agent", api_key=None)

    assert (
        str(error.value)
        == "agent: Model check failed: configured model ID was not found."
    )


@pytest.fixture
def preflight_config(monkeypatch: pytest.MonkeyPatch) -> EvalConfig:
    monkeypatch.setenv("EVAL_TEST_AGENT_KEY", "test-agent-key")
    monkeypatch.setenv("EVAL_TEST_USER_KEY", "test-user-key")
    return EvalConfig.model_validate(
        {
            "evaluation": {"task_ids": ["create_task_1"], "seed": 42},
            "agent": {
                "model": "agent-model",
                "base_url": "http://localhost:8080/v1",
                "api_key_env": "EVAL_TEST_AGENT_KEY",
            },
            "user": {
                "model": "user-model",
                "base_url": "http://localhost:8081/v1",
                "api_key_env": "EVAL_TEST_USER_KEY",
            },
        }
    )


@pytest.mark.parametrize(
    "same_server", [False, True], ids=["separate_servers", "shared_server"]
)
def test_preflight_checks_each_role_with_its_model_and_credentials(
    mock_http: Callable,
    preflight_config: EvalConfig,
    same_server: bool,
) -> None:
    if same_server:
        preflight_config.user.base_url = preflight_config.agent.base_url
    original_config = preflight_config.model_dump()
    models_by_key = {
        "Bearer test-agent-key": "agent-model",
        "Bearer test-user-key": "user-model",
    }
    requests = mock_http(
        lambda request: httpx.Response(
            200,
            json={"data": [{"id": models_by_key[request.headers["authorization"]]}]},
        )
    )

    runner_module._preflight_models(preflight_config)

    assert [
        (str(request.url), request.headers["authorization"]) for request in requests
    ] == [
        ("http://localhost:8080/v1/models", "Bearer test-agent-key"),
        (f"{preflight_config.user.base_url}/models", "Bearer test-user-key"),
    ]
    assert preflight_config.model_dump() == original_config


def test_preflight_stops_before_server_requests_when_user_key_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    mock_http: Callable,
    preflight_config: EvalConfig,
) -> None:
    monkeypatch.delenv("EVAL_TEST_USER_KEY")
    requests = mock_http(lambda request: httpx.Response(200, json={"data": []}))

    with pytest.raises(ValueError) as error:
        runner_module._preflight_models(preflight_config)

    assert str(error.value) == (
        "user: API key environment variable EVAL_TEST_USER_KEY is missing or empty."
    )
    assert requests == []


def test_preflight_stops_before_user_request_when_agent_model_check_fails(
    mock_http: Callable,
    preflight_config: EvalConfig,
) -> None:
    requests = mock_http(lambda request: httpx.Response(200, json={"data": []}))

    with pytest.raises(ValueError) as error:
        runner_module._preflight_models(preflight_config)

    assert (
        str(error.value)
        == "agent: Model check failed: configured model ID was not found."
    )
    assert [str(request.url) for request in requests] == [
        "http://localhost:8080/v1/models"
    ]


@pytest.fixture
def evaluation_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    preflight_config: EvalConfig,
    mock_http: Callable,
) -> EvalConfig:
    from tau2.registry import Registry

    from evals.tasks import list_tasks

    preflight_config.evaluation.task_ids = [list_tasks()[0].id]
    preflight_config.output.directory = tmp_path / "evaluations"
    monkeypatch.setattr(import_module("tau2.registry"), "registry", Registry())
    mock_http(
        lambda request: httpx.Response(
            200, json={"data": [{"id": "agent-model"}, {"id": "user-model"}]}
        )
    )
    return preflight_config


def test_evaluation_returns_official_results_path_after_preparing_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evaluation_config: EvalConfig,
) -> None:
    from tau2.data_model.simulation import TextRunConfig
    from tau2.registry import registry

    from agents.task_agent import create_task_agent

    config_path = tmp_path / "evaluation.toml"
    saved_paths: list[Path] = []

    def run_domain(config: TextRunConfig) -> None:
        assert registry.get_agent_factory(config.agent) is create_task_agent
        assert config.task_ids == evaluation_config.evaluation.task_ids
        assert config.save_to is not None
        directory = Path(config.save_to)
        recorded = tomllib.loads((directory / "metadata.toml").read_text("utf-8"))
        assert recorded["run"]["config_path"] == str(config_path.resolve())
        assert recorded["evaluation"]["task_ids"] == config.task_ids
        result_path = directory / "results.json"
        result_path.write_text('{"official_result": true}', encoding="utf-8")
        saved_paths.append(result_path)

    monkeypatch.setattr(import_module("tau2.runner"), "run_domain", run_domain)

    result = runner_module.run_evaluation(evaluation_config, config_path=config_path)

    assert saved_paths == [result]
    assert result.parent.parent == evaluation_config.output.directory
    assert result.read_text("utf-8") == '{"official_result": true}'


@pytest.mark.parametrize(
    "failure", ["unknown_task", "model_unavailable", "name_conflict"]
)
def test_evaluation_stops_before_creating_output_when_preparation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evaluation_config: EvalConfig,
    failure: str,
) -> None:
    from tau2.registry import registry

    from evals.tasks import list_tasks

    if failure == "unknown_task":
        known_ids = {task.id for task in list_tasks()}
        unknown_id = "unknown"
        while unknown_id in known_ids:
            unknown_id += "_"
        evaluation_config.evaluation.task_ids = [unknown_id]
    elif failure == "model_unavailable":
        evaluation_config.agent.model = "unavailable-model"
    else:
        registry.register_agent_factory(lambda: None, "task_agent")

    def unexpected_run(config: object) -> None:
        pytest.fail("Evaluation started despite a preparation failure")

    monkeypatch.setattr(import_module("tau2.runner"), "run_domain", unexpected_run)

    with pytest.raises(ValueError):
        runner_module.run_evaluation(
            evaluation_config, config_path=tmp_path / "evaluation.toml"
        )

    assert not evaluation_config.output.directory.exists()


def test_evaluation_preserves_artifacts_when_official_execution_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    evaluation_config: EvalConfig,
) -> None:
    from tau2.data_model.simulation import TextRunConfig

    failure = RuntimeError("Official evaluation failed")
    saved_paths: list[Path] = []

    def interrupted_run(config: TextRunConfig) -> None:
        assert config.save_to is not None
        result_path = Path(config.save_to) / "results.json"
        result_path.write_text("partial results", encoding="utf-8")
        saved_paths.append(result_path)
        raise failure

    monkeypatch.setattr(import_module("tau2.runner"), "run_domain", interrupted_run)

    with pytest.raises(RuntimeError) as error:
        runner_module.run_evaluation(
            evaluation_config, config_path=tmp_path / "evaluation.toml"
        )

    assert error.value is failure
    assert len(saved_paths) == 1
    assert saved_paths[0].read_text("utf-8") == "partial results"
    assert saved_paths[0].with_name("metadata.toml").is_file()
