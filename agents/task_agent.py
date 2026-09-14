"""TaskAgent's conversation state and tau2 interface."""

from dataclasses import dataclass
from typing import Any, cast

from tau2.agent.base_agent import HalfDuplexAgent, ValidAgentInputMessage
from tau2.data_model.message import (
    APICompatibleMessage,
    AssistantMessage,
    Message,
    MultiToolMessage,
    SystemMessage,
)
from tau2.environment.tool import Tool
from tau2.utils.llm_utils import generate

AGENT_PROMPT = (
    "You are a helpful customer service agent.\n\n"
    "Follow the policy strictly. Use the provided tools to help the user."
    "\n\n"
    "Before proposing changes, use the available tools to retrieve the records "
    "needed to identify the correct targets. Check those records against the "
    "user's requirements, exclusions, and the policy. Do not conclude that a "
    "relevant record is absent, or expand the scope of work, based on information "
    "you have not checked."
)


@dataclass
class TaskAgentState:
    """Keep system instructions and per-conversation history in separate lists.

    This state stores context for the agent, not the environment's task database.
    """

    instructions: list[SystemMessage]
    message_history: list[APICompatibleMessage]


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

    def set_seed(self, seed: int) -> None:
        """Use the trial seed supplied by tau2 for response generation."""
        self.llm_args["seed"] = seed

    def get_init_state(
        self, message_history: list[Message] | None = None
    ) -> TaskAgentState:
        """Return policy instructions and a fresh list of initial messages.

        Preserve message content and order without sharing the history list with
        the caller or another state. Message objects themselves are not copied.

        tau2's Orchestrator filters initial history through
        is_valid_agent_history_message; trust that input to contain individual
        API-compatible messages. This method makes no LLM call.
        """
        system_prompt = f"{AGENT_PROMPT}\n\n## Domain Policy\n{self.domain_policy}"
        messages = cast(
            list[APICompatibleMessage],
            list(message_history) if message_history is not None else [],
        )
        return TaskAgentState(
            instructions=[SystemMessage(role="system", content=system_prompt)],
            message_history=messages,
        )

    def generate_next_message(
        self, message: ValidAgentInputMessage, state: TaskAgentState
    ) -> tuple[AssistantMessage, TaskAgentState]:
        """Generate one response, then append the input and response to the state.

        Preserve bundled tool results as individual history entries in order.
        Store and return the response; tau2 executes any requested tools and
        delivers their results as subsequent inputs. Leave state unchanged if
        generation fails or returns an invalid response.
        """
        inputs: list[APICompatibleMessage]
        if isinstance(message, MultiToolMessage):
            inputs = list(message.tool_messages)
        else:
            inputs = [message]

        assistant_message = generate(
            model=self.llm,
            messages=[*state.instructions, *state.message_history, *inputs],
            tools=self.tools,
            **self.llm_args,
        )
        if not isinstance(assistant_message, AssistantMessage):
            raise TypeError("Response generation must return an AssistantMessage.")
        state.message_history.extend([*inputs, assistant_message])
        return assistant_message, state


def create_task_agent(
    tools: list[Tool],
    domain_policy: str,
    *,
    llm: str | None = None,
    llm_args: dict[str, Any] | None = None,
    **kwargs: object,
) -> TaskAgent:
    """Create a TaskAgent from tau2.runner.build.build_agent's factory inputs.

    The official runner also passes task and audio context through kwargs;
    TaskAgent only uses tools, policy, and model settings. Construction does
    not invoke the model or execute tools.
    """
    if llm is None:
        raise ValueError("TaskAgent requires an llm model name.")
    return TaskAgent(
        tools=tools,
        domain_policy=domain_policy,
        llm=llm,
        llm_args=llm_args,
    )
