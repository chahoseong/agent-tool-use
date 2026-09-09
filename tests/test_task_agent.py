"""Verify message history and response generation without calling an LLM."""

from typing import Any

import pytest
from tau2.agent.base_agent import ValidAgentInputMessage
from tau2.data_model.message import (
    APICompatibleMessage,
    AssistantMessage,
    Message,
    MultiToolMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from tau2.environment.tool import Tool

from agents import TaskAgent
from agents import task_agent as task_agent_module


@pytest.fixture
def agent() -> TaskAgent:
    return TaskAgent(tools=[], domain_policy="Policy", llm="test-model")


@pytest.fixture(params=["omitted", "empty", "populated"])
def message_history(request: pytest.FixtureRequest) -> list[Message] | None:
    if request.param == "omitted":
        return None
    if request.param == "empty":
        return []
    return [
        UserMessage(role="user", content="Hello"),
        AssistantMessage(role="assistant", content="How can I help?"),
        ToolMessage(
            role="tool", id="call-1", content="Tool result", requestor="assistant"
        ),
    ]


@pytest.mark.parametrize(
    "policy", ["Ask before deleting tasks.", "Only list open tasks."]
)
def test_initial_instructions_include_agent_prompt_and_domain_policy(
    policy: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent_prompt = "Help the user manage tasks with concise, clear responses."
    monkeypatch.setattr(task_agent_module, "AGENT_PROMPT", agent_prompt)
    agent = TaskAgent(tools=[], domain_policy=policy, llm="test-model")
    state = agent.get_init_state()
    assert state.instructions
    assert all(isinstance(message, SystemMessage) for message in state.instructions)
    content = "\n".join(message.content or "" for message in state.instructions)
    assert agent_prompt in content
    assert policy in content


@pytest.mark.parametrize("message_history", ["empty", "populated"], indirect=True)
def test_initial_state_preserves_provided_message_history(
    agent: TaskAgent, message_history: list[Message] | None
) -> None:
    assert message_history is not None
    expected_message_history = [message.model_dump() for message in message_history]
    state = agent.get_init_state(message_history)
    assert [
        message.model_dump() for message in state.message_history
    ] == expected_message_history


@pytest.mark.parametrize("message_history", ["empty", "populated"], indirect=True)
def test_input_message_history_remains_unchanged_when_state_message_history_changes(
    agent: TaskAgent, message_history: list[Message] | None
) -> None:
    assert message_history is not None
    expected_message_history = list(message_history)
    state = agent.get_init_state(message_history)
    assert message_history == expected_message_history
    state.message_history.append(AssistantMessage(role="assistant", content="Done"))
    assert message_history == expected_message_history


def test_agent_returns_independent_initial_states(
    agent: TaskAgent,
) -> None:
    first = agent.get_init_state()
    second = agent.get_init_state()
    assert first is not second
    assert first.message_history == []
    assert second.message_history == []
    first.message_history.append(AssistantMessage(role="assistant", content="Done"))
    assert second.message_history == []


@pytest.mark.parametrize(
    "input_kind", ["user", "tool", "multiple_tools", "mixed_tool_results"]
)
def test_agent_appends_input_message_and_generated_response_to_message_history(
    agent: TaskAgent, monkeypatch: pytest.MonkeyPatch, input_kind: str
) -> None:
    initial_message_history: list[Message] = [
        UserMessage(role="user", content="Help me inspect my tasks."),
        AssistantMessage(role="assistant", content="Which tasks should I inspect?"),
    ]
    incoming: ValidAgentInputMessage
    expected_inputs: list[APICompatibleMessage]
    if input_kind == "user":
        incoming = UserMessage(role="user", content="Inspect my open tasks.")
        expected_inputs = [incoming]
    else:
        tool_calls = [
            ToolCall(
                id="call-z",
                name="get_task",
                arguments={"task_id": "task-2"},
                requestor="assistant",
            )
        ]
        tool_results = [
            ToolMessage(
                role="tool",
                id="call-z",
                content='{"title": "Buy milk"}',
                requestor="assistant",
            )
        ]
        if input_kind != "tool":
            tool_calls.append(
                ToolCall(
                    id="call-a",
                    name="get_task",
                    arguments={"task_id": "task-1"},
                    requestor="assistant",
                )
            )
            has_error = input_kind == "mixed_tool_results"
            tool_results.append(
                ToolMessage(
                    role="tool",
                    id="call-a",
                    content="Task not found" if has_error else '{"title": "Read"}',
                    error=has_error,
                    requestor="assistant",
                )
            )
        initial_message_history.extend(
            [
                UserMessage(role="user", content="Inspect the selected tasks."),
                AssistantMessage(role="assistant", tool_calls=tool_calls),
            ]
        )
        expected_inputs = list(tool_results)
        incoming = (
            tool_results[0]
            if input_kind == "tool"
            else MultiToolMessage(role="tool", tool_messages=tool_results)
        )

    state = agent.get_init_state(initial_message_history)
    expected_system = [message.model_dump() for message in state.instructions]
    expected_message_history = [
        message.model_dump() for message in [*initial_message_history, *expected_inputs]
    ]
    generated_response = AssistantMessage(
        role="assistant", content="I have the results."
    )
    expected_response = generated_response.model_dump()
    generation_contexts: list[list[dict[str, Any]]] = []

    def fake_generate(*, messages: list[Message], **kwargs: object) -> AssistantMessage:
        generation_contexts.append([message.model_dump() for message in messages])
        return generated_response

    monkeypatch.setattr(task_agent_module, "generate", fake_generate)

    _, updated_state = agent.generate_next_message(incoming, state)

    assert updated_state is state
    assert generation_contexts == [expected_system + expected_message_history]
    assert [
        message.model_dump() for message in updated_state.message_history
    ] == expected_message_history + [expected_response]
    assert [
        message.model_dump() for message in updated_state.instructions
    ] == expected_system


def test_agent_preserves_state_when_response_generation_fails(
    agent: TaskAgent, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = agent.get_init_state(
        [
            UserMessage(role="user", content="Help me inspect my tasks."),
            AssistantMessage(role="assistant", content="Which tasks should I inspect?"),
        ]
    )
    expected_instructions = [message.model_dump() for message in state.instructions]
    expected_message_history = [
        message.model_dump() for message in state.message_history
    ]
    generation_error = RuntimeError("Response generation failed")

    def fake_generate(**kwargs: object) -> AssistantMessage:
        raise generation_error

    monkeypatch.setattr(task_agent_module, "generate", fake_generate)

    with pytest.raises(RuntimeError) as exc_info:
        agent.generate_next_message(
            UserMessage(role="user", content="Inspect my open tasks."), state
        )

    assert exc_info.value is generation_error
    assert [
        message.model_dump() for message in state.instructions
    ] == expected_instructions
    assert [
        message.model_dump() for message in state.message_history
    ] == expected_message_history


def test_agent_rejects_invalid_response_without_changing_state(
    agent: TaskAgent, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = agent.get_init_state(
        [
            UserMessage(role="user", content="Help me inspect my tasks."),
            AssistantMessage(role="assistant", content="Which tasks should I inspect?"),
        ]
    )
    expected_instructions = [message.model_dump() for message in state.instructions]
    expected_message_history = [
        message.model_dump() for message in state.message_history
    ]

    def fake_generate(**kwargs: object) -> UserMessage:
        return UserMessage(role="user", content="This is not an assistant response.")

    monkeypatch.setattr(task_agent_module, "generate", fake_generate)

    with pytest.raises(TypeError):
        agent.generate_next_message(
            UserMessage(role="user", content="Inspect my open tasks."), state
        )

    assert [
        message.model_dump() for message in state.instructions
    ] == expected_instructions
    assert [
        message.model_dump() for message in state.message_history
    ] == expected_message_history


def test_agent_preserves_message_history_across_tool_use_turns(
    agent: TaskAgent, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_request = UserMessage(role="user", content="Inspect task-2.")
    tool_request = AssistantMessage(
        role="assistant",
        tool_calls=[
            ToolCall(
                id="call-z",
                name="get_task",
                arguments={"task_id": "task-2"},
                requestor="assistant",
            )
        ],
    )
    tool_result = ToolMessage(
        role="tool",
        id="call-z",
        content='{"title": "Buy milk"}',
        requestor="assistant",
    )
    follow_up = AssistantMessage(role="assistant", content="Task-2 is Buy milk.")
    state = agent.get_init_state()
    expected_system = [message.model_dump() for message in state.instructions]
    expected_message_history = [
        message.model_dump()
        for message in [user_request, tool_request, tool_result, follow_up]
    ]
    generation_contexts: list[list[dict[str, Any]]] = []
    generated_responses = iter([tool_request, follow_up])

    def fake_generate(*, messages: list[Message], **kwargs: object) -> AssistantMessage:
        generation_contexts.append([message.model_dump() for message in messages])
        return next(generated_responses)

    monkeypatch.setattr(task_agent_module, "generate", fake_generate)

    first_response, state = agent.generate_next_message(user_request, state)
    second_response, state = agent.generate_next_message(tool_result, state)

    assert generation_contexts == [
        expected_system + expected_message_history[:1],
        expected_system + expected_message_history[:3],
    ]
    assert first_response.model_dump() == expected_message_history[1]
    assert second_response.model_dump() == expected_message_history[3]
    assert [
        message.model_dump() for message in state.message_history
    ] == expected_message_history


def test_agent_passes_tools_and_model_settings_to_generate_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def get_task(task_id: str) -> str:
        """Return the selected task's details."""
        return task_id

    def list_tasks(completed: bool = False) -> list[str]:
        """List tasks with the selected completion status."""
        return []

    tools = [Tool(get_task), Tool(list_tasks)]
    expected_schemas = [tool.openai_schema for tool in tools]
    model = "configured-task-model"
    model_options = {"temperature": 0.25, "max_tokens": 137, "seed": 42}
    agent = TaskAgent(
        tools=tools,
        domain_policy="Inspect tasks using the provided tools.",
        llm=model,
        llm_args=model_options,
    )
    captured_settings: dict[str, Any] = {}

    def fake_generate(
        *,
        model: str,
        messages: list[Message],
        tools: list[Tool],
        **kwargs: object,
    ) -> AssistantMessage:
        captured_settings.update(
            model=model,
            tools=[tool.openai_schema for tool in tools],
            options=dict(kwargs),
        )
        return AssistantMessage(
            role="assistant", content="Which task should I inspect?"
        )

    monkeypatch.setattr(task_agent_module, "generate", fake_generate)

    agent.generate_next_message(
        UserMessage(role="user", content="Help me inspect my tasks."),
        agent.get_init_state(),
    )

    assert captured_settings["model"] == model
    assert captured_settings["tools"] == expected_schemas
    assert captured_settings["options"] == model_options


def test_agent_passes_latest_seed_to_response_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = TaskAgent(
        tools=[],
        domain_policy="Inspect tasks using the provided tools.",
        llm="test-model",
        llm_args={"temperature": 0.25, "max_tokens": 137},
    )
    generation_options: list[dict[str, object]] = []

    def fake_generate(
        *,
        model: str,
        messages: list[Message],
        tools: list[Tool],
        **kwargs: object,
    ) -> AssistantMessage:
        generation_options.append(dict(kwargs))
        return AssistantMessage(role="assistant", content="Your tasks are ready.")

    monkeypatch.setattr(task_agent_module, "generate", fake_generate)

    for seed in (42, 73):
        agent.set_seed(seed)
        agent.generate_next_message(
            UserMessage(role="user", content="Inspect my tasks."),
            agent.get_init_state(),
        )

    assert generation_options == [
        {"temperature": 0.25, "max_tokens": 137, "seed": 42},
        {"temperature": 0.25, "max_tokens": 137, "seed": 73},
    ]
