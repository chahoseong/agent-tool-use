"""Verify initial conversation state without calling an LLM."""

import pytest
from tau2.data_model.message import (
    AssistantMessage,
    Message,
    MultiToolMessage,
    ToolMessage,
    UserMessage,
)

from agents import TaskAgent


@pytest.fixture
def agent() -> TaskAgent:
    return TaskAgent(tools=[], domain_policy="Policy", llm="test-model")


@pytest.fixture(params=["omitted", "empty", "populated"])
def history(request: pytest.FixtureRequest) -> list[Message] | None:
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
def test_initial_state_includes_domain_policy(policy: str) -> None:
    agent = TaskAgent(tools=[], domain_policy=policy, llm="test-model")
    state = agent.get_init_state()
    assert state.system_messages
    assert all(message.role == "system" for message in state.system_messages)
    content = "\n".join(message.content or "" for message in state.system_messages)
    assert policy in content


def test_initial_state_separates_user_request_from_system_messages(
    agent: TaskAgent,
) -> None:
    request_text = "Unique user request"
    request = UserMessage(role="user", content=request_text)
    state = agent.get_init_state([request])
    content = "\n".join(message.content or "" for message in state.system_messages)
    assert request_text not in content
    assert state.messages == [request]


def test_initial_state_preserves_history(
    agent: TaskAgent, history: list[Message] | None
) -> None:
    expected = list(history) if history is not None else []
    state = agent.get_init_state() if history is None else agent.get_init_state(history)
    assert state.messages == expected


@pytest.mark.parametrize("history", ["empty", "populated"], indirect=True)
def test_state_history_changes_preserve_input_history(
    agent: TaskAgent, history: list[Message] | None
) -> None:
    assert history is not None
    expected = list(history)
    state = agent.get_init_state(history)
    assert history == expected
    state.messages.append(AssistantMessage(role="assistant", content="Done"))
    assert history == expected


def test_state_history_changes_preserve_other_states(
    agent: TaskAgent, history: list[Message] | None
) -> None:
    expected = list(history) if history is not None else []
    first = agent.get_init_state() if history is None else agent.get_init_state(history)
    second = (
        agent.get_init_state() if history is None else agent.get_init_state(history)
    )
    first.messages.append(AssistantMessage(role="assistant", content="Done"))
    assert second.messages == expected


def test_initial_state_rejects_multi_tool_message(agent: TaskAgent) -> None:
    message = MultiToolMessage(
        role="tool",
        tool_messages=[
            ToolMessage(
                role="tool", id="call-1", content="Result", requestor="assistant"
            ),
            ToolMessage(
                role="tool", id="call-2", content="Result", requestor="assistant"
            ),
        ],
    )
    with pytest.raises(TypeError):
        agent.get_init_state([message])
