"""TaskAgent's conversation state and tau2 interface."""

from dataclasses import dataclass
from typing import Any

from tau2.agent.base_agent import HalfDuplexAgent, ValidAgentInputMessage
from tau2.data_model.message import (
    APICompatibleMessage,
    AssistantMessage,
    Message,
    SystemMessage,
)
from tau2.environment.tool import Tool


@dataclass
class TaskAgentState:
    """Keep system instructions and per-conversation history in separate lists.

    This state stores context for the agent, not the environment's task database.
    """

    system_messages: list[SystemMessage]
    messages: list[APICompatibleMessage]


class TaskAgent(HalfDuplexAgent[TaskAgentState]):
    """Implement tau2's turn-based agent contract."""

    def __init__(
        self,
        tools: list[Tool],
        domain_policy: str,
        llm: str,
        llm_args: dict[str, Any] | None = None,
    ) -> None:
        """Store domain and model settings without making an LLM call."""
        super().__init__(tools=tools, domain_policy=domain_policy)
        self.llm = llm
        self.llm_args = dict(llm_args) if llm_args is not None else {}

    def get_init_state(
        self, message_history: list[Message] | None = None
    ) -> TaskAgentState:
        """Return policy instructions and a fresh list of initial messages.

        Preserve message content and order without sharing the history list with
        the caller or another state. Message objects themselves are not copied.

        tau2's Orchestrator filters initial history through
        is_valid_agent_history_message, supplying individual messages.
        MultiToolMessage bundles are turn inputs, not initial history entries;
        passing one here raises TypeError. This method makes no LLM call.
        """
        system_prompt = (
            "You are a helpful customer service agent.\n\n"
            f"## Domain Policy\n{self.domain_policy}\n\n"
            "Follow the policy strictly. Use the provided tools to help the user."
        )
        messages: list[APICompatibleMessage] = []
        for message in message_history if message_history is not None else []:
            if not isinstance(message, APICompatibleMessage):
                raise TypeError(
                    "Initial history must contain individual messages, "
                    "not MultiToolMessage bundles."
                )
            messages.append(message)
        return TaskAgentState(
            system_messages=[SystemMessage(role="system", content=system_prompt)],
            messages=messages,
        )

    def generate_next_message(
        self, message: ValidAgentInputMessage, state: TaskAgentState
    ) -> tuple[AssistantMessage, TaskAgentState]:
        """Define the next-turn contract; implementation belongs to a follow-up.

        Accept a UserMessage, ToolMessage, or MultiToolMessage and current state.
        The future implementation will append the input (individual tool results
        for a bundle), pass system instructions, history, and tools to tau2's
        generate utility, then append its AssistantMessage to the history.

        Return (assistant_message, updated_state). The assistant message contains
        text or tool-call requests; tau2 executes tools and delivers their results
        as subsequent inputs. This method currently raises NotImplementedError.
        """
        raise NotImplementedError("Next message generation is not implemented yet.")
