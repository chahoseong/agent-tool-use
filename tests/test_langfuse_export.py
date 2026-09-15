from typing import Any

from evals.langfuse_export import conversation_message, judge_scores, observations


def test_conversation_message_preserves_tool_arguments_in_chat_format():
    result = conversation_message(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call", "name": "lookup", "arguments": {"id": "abc"}}
            ],
            "raw_data": {"api_key": "secret"},
        }
    )
    assert result["tool_calls"][0]["function"]["arguments"] == '{"id": "abc"}'
    assert "raw_data" not in result


def test_observations_pair_tool_results_with_requests():
    messages: list[dict[str, Any]] = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call", "name": "lookup", "arguments": {"id": "abc"}}
            ],
        },
        {"role": "tool", "tool_call_id": "call", "content": '{"found":true}'},
    ]
    records = observations(messages, {"agent_info": {"llm": "agent-model"}})
    tool = next(x for x in records if x["as_type"] == "tool")
    assert tool["input"] == {"id": "abc"}
    assert tool["output"] == '{"found":true}'
    assert records[0]["model"] == "agent-model"


def test_judge_scores_keep_unresolved_results_out_of_numeric_success_rates():
    result = {
        "status": "review_required",
        "assessments": [
            {
                "criterion_id": "consent",
                "verdict": "pass",
                "reason": "r",
                "evidence": [],
            }
        ],
    }
    assert judge_scores(result) == []


def test_judge_scores_include_actual_evidence_for_unknown_verdict():
    result = {
        "status": "completed",
        "assessments": [
            {
                "criterion_id": "consent",
                "verdict": "unknown",
                "reason": "insufficient",
                "evidence": [{"excerpt": "Can I cancel?"}],
                "evidence_limit": "no reply",
            }
        ],
    }
    score = judge_scores(result)[0]
    assert score["data_type"] == "CATEGORICAL"
    assert score["value"] == "unknown"
    assert "Can I cancel?" in score["comment"]


def test_observations_mark_missing_tool_results_as_unobserved():
    records = observations(
        [
            {
                "role": "assistant",
                "tool_calls": [{"id": "call", "name": "cancel", "arguments": {}}],
            }
        ],
        {},
    )
    assert records[-1]["output"] is None
    assert records[-1]["level"] == "WARNING"
