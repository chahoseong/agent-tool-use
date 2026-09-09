"""Verify TaskAgent construction through the official factory call contract."""

from typing import Any

import pytest
from tau2.data_model.message import AssistantMessage
from tau2.environment.tool import Tool

from agents import TaskAgent, create_task_agent
from agents import task_agent as task_agent_module


@pytest.mark.parametrize(
    "llm_args",
    [None, {"temperature": 0.25, "seed": 42}],
    ids=["default_options", "configured_options"],
)
def test_task_agent_factory_creates_agent_with_runner_settings(
    monkeypatch: pytest.MonkeyPatch, llm_args: dict[str, Any] | None
) -> None:
    def get_task(task_id: str) -> str:
        """Return details for the selected task."""
        pytest.fail("Agent construction must not execute tools.")

    def reject_generation(**kwargs: object) -> AssistantMessage:
        pytest.fail("Agent construction must not invoke generate().")

    monkeypatch.setattr(task_agent_module, "generate", reject_generation)
    tools = [Tool(get_task)]
    expected_schemas = [tool.openai_schema for tool in tools]
    policy = "Inspect tasks using the provided tools."
    model = "openai/test-model"

    agent = create_task_agent(
        tools=tools,
        domain_policy=policy,
        llm=model,
        llm_args=llm_args,
        task=object(),
        audio_native_config=None,
        audio_taps_dir=None,
    )

    assert isinstance(agent, TaskAgent)
    assert [tool.openai_schema for tool in agent.tools] == expected_schemas
    assert agent.domain_policy == policy
    assert agent.llm == model
    assert agent.llm_args == (llm_args if llm_args is not None else {})


@pytest.mark.parametrize(
    "model_settings",
    [{}, {"llm": None}],
    ids=["omitted", "none"],
)
def test_task_agent_factory_rejects_missing_model(
    model_settings: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match="requires an llm model name"):
        create_task_agent(tools=[], domain_policy="Policy", **model_settings)
