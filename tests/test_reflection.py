"""Exercise reflection control flow with a fake model, not a live judge."""

import json

import pytest
from tau2.data_model.message import (
    APICompatibleMessage,
    AssistantMessage,
    UserMessage,
)


@pytest.mark.parametrize(
    ("review_response", "expected_kind", "expected_error_type"),
    [
        pytest.param(
            RuntimeError("Server failed with a private credential in its message"),
            "review_generation_error",
            "RuntimeError",
            id="model_call_failure",
        ),
        pytest.param(
            AssistantMessage(role="assistant", content="not JSON"),
            "review_parse_error",
            "ValueError",
            id="invalid_json",
        ),
        pytest.param(
            AssistantMessage(role="assistant", content='{"decision": "approve"}'),
            "review_parse_error",
            "ValidationError",
            id="missing_required_field",
        ),
        *[
            pytest.param(
                AssistantMessage(role="assistant", content=text),
                "review_parse_error",
                "ValidationError" if case == "multiple_objects" else "ValueError",
                id=case,
            )
            for case, text in [
                ("truncated_json", '{"decision":"approve","feedback":[]'),
                (
                    "multiple_objects",
                    '{"decision":"approve","feedback":[]} {"decision":"approve","feedback":[]}',
                ),
                ("missing_opening_brace", '"decision":"approve","feedback":[]}'),
            ]
        ],
        *[
            pytest.param(
                AssistantMessage(
                    role="assistant",
                    content=json.dumps({"decision": "revise", "feedback": value}),
                ),
                "review_parse_error",
                "ValidationError",
                id=case,
            )
            for case, value in [
                ("feedback_is_string", "Check the reservation."),
                ("feedback_is_object", [{"required_change": "Check it."}]),
                ("feedback_is_number", [1]),
            ]
        ],
        pytest.param(
            AssistantMessage(
                role="assistant",
                content='{"decision":"revise","feedback":[]}',
            ),
            "review_parse_error",
            "ValidationError",
            id="revise_without_feedback",
        ),
        pytest.param(
            AssistantMessage(
                role="assistant",
                content=json.dumps(
                    {
                        "decision": "need_information",
                        "feedback": ["Ask for the missing reservation ID."],
                    }
                ),
            ),
            "review_parse_error",
            "ValidationError",
            id="unsupported_decision",
        ),
        pytest.param(
            AssistantMessage(
                role="assistant",
                content=json.dumps(
                    {
                        "decision": "approve",
                        "feedback": ["The ID is unconfirmed. Confirm the task ID."],
                    }
                ),
            ),
            "review_parse_error",
            "ValidationError",
            id="approval_with_feedback",
        ),
        pytest.param(
            AssistantMessage(
                role="assistant",
                content=json.dumps(
                    {
                        "decision": "revise",
                        "feedback": [" \n\t"],
                    }
                ),
            ),
            "review_parse_error",
            "ValidationError",
            id="blank_feedback_item",
        ),
    ],
)
def test_review_preserves_current_draft_when_review_fails(
    monkeypatch: pytest.MonkeyPatch,
    review_response: RuntimeError | AssistantMessage,
    expected_kind: str,
    expected_error_type: str,
) -> None:
    from agents import reflection

    conversation: list[APICompatibleMessage] = [
        UserMessage(role="user", content="Please look up my task.")
    ]
    current_draft = AssistantMessage(role="assistant", content="What is the task ID?")
    original_conversation = [message.model_dump() for message in conversation]
    original_draft = current_draft.model_dump()
    calls = 0

    def fake_generate(**kwargs: object) -> AssistantMessage:
        nonlocal calls
        calls += 1
        if isinstance(review_response, RuntimeError):
            raise review_response
        return review_response

    monkeypatch.setattr(reflection, "generate", fake_generate)

    result = reflection.review_draft(
        draft=current_draft,
        conversation=conversation,
        domain_policy="Look up tasks before answering.",
        tools=[],
        model="configured-agent-model",
        llm_args={},
    )

    assert result.draft is current_draft
    assert result.decision is None
    assert result.error is not None
    assert result.error.kind == expected_kind
    assert result.error.error_type == expected_error_type
    assert result.response is (
        review_response if isinstance(review_response, AssistantMessage) else None
    )
    assert "private credential" not in repr(result)
    assert [message.model_dump() for message in conversation] == original_conversation
    assert current_draft.model_dump() == original_draft
    assert calls == 1


@pytest.mark.parametrize(
    ("prefix", "suffix"),
    [
        pytest.param("", "", id="plain_json"),
        pytest.param("```json\n", "\n```", id="complete_fence"),
        pytest.param("```json\n", "", id="opening_fence_only"),
        pytest.param("", "\n```", id="closing_fence_only"),
        pytest.param("Review result:\n", "\nEnd of review.", id="surrounding_text"),
    ],
)
def test_review_returns_decision_from_wrapped_json_without_changing_original_response(
    monkeypatch: pytest.MonkeyPatch, prefix: str, suffix: str
) -> None:
    from agents import reflection

    expected = {
        "decision": "revise",
        "feedback": ["The value {target} is unconfirmed. Ask for confirmation."],
    }
    content = prefix + json.dumps(expected) + suffix
    response = AssistantMessage(role="assistant", content=content)
    monkeypatch.setattr(reflection, "generate", lambda **kwargs: response)
    result = reflection.review_draft(
        draft=AssistantMessage(role="assistant", content="I will change it now."),
        conversation=[],
        domain_policy="Confirm the target first.",
        tools=[],
        model="test-model",
        llm_args={},
    )
    assert result.error is None
    assert result.decision is not None
    assert result.decision.model_dump() == expected
    assert result.response is response
    assert result.response.content == content
