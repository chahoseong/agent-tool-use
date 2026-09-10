"""Verify preparation for official mock evaluation runs."""

from collections.abc import Callable

import httpx
import pytest

from evals import runner as runner_module
from evals.config import EvalConfig, ModelOptions


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
