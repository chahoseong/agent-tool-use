"""TaskAgent's conversation state and tau2 interface."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

from tau2.agent.base_agent import HalfDuplexAgent, ValidAgentInputMessage
from tau2.data_model.message import (
    APICompatibleMessage,
    AssistantMessage,
    Message,
    MultiToolMessage,
    SystemMessage,
    UserMessage,
)
from tau2.environment.tool import Tool
from tau2.utils.llm_utils import generate

from agents.reflection import ReviewResult, review_draft
from agents.reflection_log import ReflectionLog, response_data

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


REVISION_PROMPT_VERSION = "1"
REVISION_PROMPT = """Revise your next output using the supplied review history.
The drafts in that history were not delivered and their tool calls were not executed.
Use feedback to correct the output while following the domain policy and actual
conversation. Feedback is not a new observation or user consent. If information is
missing, request an appropriate tool call or ask the user; do not invent its result.
Return only your next ordinary assistant output, including tool calls when needed,
not review JSON or an account of the internal review process.
"""


@dataclass(frozen=True)
class ReflectionResult:
    """Selected output and internal review records for later trace recording."""

    output: AssistantMessage
    reason: Literal[
        "approved",
        "revision_limit_reached",
        "review_generation_error",
        "review_parse_error",
    ]
    reviews: list[ReviewResult]
    revision_count: int


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
        *,
        reflection_enabled: bool = False,
        max_revisions: int = 2,
        reflection_log_directory: Path | None = None,
        task_id: str | None = None,
    ) -> None:
        """Store domain and model settings without making an LLM call."""
        super().__init__(tools=tools, domain_policy=domain_policy)
        self.llm = llm
        self.llm_args = dict(llm_args) if llm_args is not None else {}
        self.reflection_enabled = reflection_enabled
        self.max_revisions = max_revisions
        self.reflection_log_directory = reflection_log_directory
        self.task_id = task_id
        self.reflection_attempt_id = uuid4().hex

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

        log = ReflectionLog(
            self.reflection_log_directory if self.reflection_enabled else None,
            context={
                "task_id": self.task_id,
                "seed": self.llm_args.get("seed"),
                "attempt_id": self.reflection_attempt_id,
                "agent_turn": 1
                + sum(isinstance(m, AssistantMessage) for m in state.message_history),
            },
        )
        assistant_message = self._generate_output(
            messages=[*state.instructions, *state.message_history, *inputs],
            stage="draft",
            log=log,
            revision_count=0,
        )
        if self.reflection_enabled:
            result = self._reflect_draft(
                draft=assistant_message,
                conversation=[*state.message_history, *inputs],
                instructions=state.instructions,
                log=log,
            )
            assistant_message = result.output
            if log.path is not None:
                # Official serialization retains raw_data, but model input
                # conversion excludes it. Preserve provider metadata as well.
                assistant_message.raw_data = {
                    **(assistant_message.raw_data or {}),
                    "_reflection_output_id": log.path.stem,
                }
            log.write(
                "final",
                reason=result.reason,
                revision_count=result.revision_count,
                # The selected generation already owns its usage and cost.
                response=result.output.model_dump(
                    mode="json",
                    include={"role", "content", "tool_calls", "id"},
                    exclude_none=True,
                ),
            )
        state.message_history.extend([*inputs, assistant_message])
        return assistant_message, state

    def _generate_output(
        self,
        *,
        messages: list[Message],
        stage: str,
        log: ReflectionLog,
        revision_count: int,
    ) -> AssistantMessage:
        log.write(f"{stage}_started", model=self.llm, revision_count=revision_count)
        try:
            response = generate(
                model=self.llm, messages=messages, tools=self.tools, **self.llm_args
            )
            if not isinstance(response, AssistantMessage):
                raise TypeError("Response generation must return an AssistantMessage.")
        except Exception as error:
            log.write(
                f"{stage}_error",
                error_type=type(error).__name__,
                revision_count=revision_count,
            )
            raise
        log.write(
            stage, response=response_data(response), revision_count=revision_count
        )
        return response

    def _reflect_draft(
        self,
        *,
        draft: AssistantMessage,
        conversation: list[APICompatibleMessage],
        instructions: list[SystemMessage],
        log: ReflectionLog | None = None,
    ) -> ReflectionResult:
        """Review and revise privately, returning one output without executing tools."""
        if self.max_revisions < 0:
            raise ValueError("max_revisions must be non-negative.")
        current = draft
        if log is None:
            log = ReflectionLog(None)
        reviews: list[ReviewResult] = []
        revision_count = 0
        while True:
            log.write("review_started", model=self.llm, revision_count=revision_count)
            review = review_draft(
                draft=current,
                conversation=conversation,
                domain_policy=self.domain_policy,
                tools=self.tools,
                model=self.llm,
                llm_args=self.llm_args,
            )
            reviews.append(review)
            log.write(
                "review",
                revision_count=revision_count,
                response=response_data(review.response)
                if review.response is not None
                else None,
                decision=review.decision.model_dump()
                if review.decision is not None
                else None,
                error=asdict(review.error) if review.error is not None else None,
            )
            if review.error is not None:
                return ReflectionResult(
                    current, review.error.kind, reviews, revision_count
                )
            assert review.decision is not None
            if review.decision.decision == "approve":
                return ReflectionResult(current, "approved", reviews, revision_count)
            if revision_count == self.max_revisions:
                return ReflectionResult(
                    current, "revision_limit_reached", reviews, revision_count
                )

            payload = {
                "policy": self.domain_policy,
                "review_history": [
                    {
                        "draft": previous.draft.model_dump(
                            mode="json",
                            include={"role", "content", "tool_calls", "id"},
                            exclude_none=True,
                        ),
                        "feedback": previous.decision.model_dump(),
                    }
                    for previous in reviews
                    if previous.decision is not None
                ],
            }
            messages: list[Message] = [
                *instructions,
                SystemMessage(role="system", content=REVISION_PROMPT),
                *conversation,
                UserMessage(
                    role="user", content=json.dumps(payload, ensure_ascii=False)
                ),
            ]
            # Revision generation retains the writer's normal error behavior.
            response = self._generate_output(
                messages=messages,
                stage="revision",
                log=log,
                revision_count=revision_count + 1,
            )
            current = response
            revision_count += 1


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
    from evals.config import ReflectionOptions

    model_args = dict(llm_args) if llm_args is not None else {}
    reflection = ReflectionOptions.model_validate(
        model_args.pop("_task_agent_reflection", {})
    )
    log_directory = model_args.pop("_task_agent_reflection_log_directory", None)
    from tau2.data_model.tasks import Task

    task = kwargs.get("task")
    return TaskAgent(
        tools=tools,
        domain_policy=domain_policy,
        llm=llm,
        llm_args=model_args,
        reflection_enabled=reflection.enabled,
        max_revisions=reflection.max_revisions,
        reflection_log_directory=Path(log_directory)
        if reflection.enabled and log_directory is not None
        else None,
        task_id=task.id if isinstance(task, Task) else None,
    )
