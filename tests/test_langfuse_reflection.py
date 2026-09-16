"""Validate reflection imports using saved files and an in-memory SDK substitute."""

import json
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pytest

from evals.langfuse_export import _export_selected
from evals.langfuse_publication import Ledger


@pytest.fixture(params=["issues", "feedback"])
def recording(
    tmp_path: Path, request: pytest.FixtureRequest
) -> tuple[Path, dict[str, Any]]:
    output_id = "a" * 32
    response = {
        "role": "assistant",
        "content": "Final",
        "usage": {"prompt_tokens": 4, "completion_tokens": 1},
        "cost": 0.4,
    }
    sim = {
        "id": "sim",
        "task_id": "42",
        "trial": 0,
        "seed": 10,
        "messages": [{**response, "raw_data": {"_reflection_output_id": output_id}}],
    }
    context = {"task_id": "42", "seed": 10, "attempt_id": "attempt", "agent_turn": 1}
    rows = [
        {"stage": "draft_started", "revision_count": 0, "model": "agent-model"},
        {
            "stage": "draft",
            "revision_count": 0,
            "response": {
                "role": "assistant",
                "content": "Draft",
                "usage": {"prompt_tokens": 2},
                "cost": 0.2,
            },
        },
        {"stage": "review_started", "revision_count": 0, "model": "agent-model"},
        {
            "stage": "review",
            "revision_count": 0,
            "response": {
                "role": "assistant",
                "content": "review JSON",
                "usage": {"prompt_tokens": 3},
                "cost": 0.3,
            },
            "decision": {
                "decision": "revise",
                "issues": [
                    {"evidence": "Missing confirmation", "required_change": "Ask first"}
                ],
            },
            "error": None,
        },
        {"stage": "revision_started", "revision_count": 1, "model": "agent-model"},
        {"stage": "revision", "revision_count": 1, "response": response},
        {"stage": "review_started", "revision_count": 1, "model": "agent-model"},
        {
            "stage": "review",
            "revision_count": 1,
            "response": {
                "role": "assistant",
                "content": "approval",
                "usage": {"prompt_tokens": 3},
                "cost": 0.3,
            },
            "decision": {"decision": "approve", "issues": []},
            "error": None,
        },
        {
            "stage": "final",
            "revision_count": 1,
            "response": {"role": "assistant", "content": "Final"},
            "reason": "approved",
        },
    ]
    if request.param == "feedback":
        rows[3]["decision"] = {
            "decision": "revise",
            "feedback": ["Missing confirmation. Ask first"],
        }
        rows[7]["decision"] = {"decision": "approve", "feedback": []}
    folder = tmp_path / "reflection"
    folder.mkdir()
    (folder / f"{output_id}.jsonl").write_text(
        "\n".join(
            json.dumps(
                {
                    "schema_version": 1,
                    "output_id": output_id,
                    "context": context,
                    "recorded_at": "2026-09-15T00:00:00+00:00",
                    **r,
                }
            )
            for r in rows
        )
        + "\n",
        encoding="utf-8",
    )
    (folder / "index.json").write_text(
        json.dumps(
            {
                "outputs": [
                    {
                        "status": "linked",
                        "output_id": output_id,
                        "file": f"{output_id}.jsonl",
                        "simulation_id": "sim",
                        "task_id": "42",
                        "seed": 10,
                        "trial": 0,
                        "message_index": 0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return tmp_path, sim


@pytest.mark.parametrize(
    "problem", ["message_index", "path", "final_output", "missing_revision"]
)
def test_reflection_import_rejects_mismatched_saved_records(recording, problem):
    from evals.langfuse_reflection import read_reflections

    source, sim = recording
    path = source / "reflection" / "index.json"
    index = json.loads(path.read_text())
    if problem == "message_index":
        index["outputs"][0]["message_index"] = 5
    elif problem == "path":
        index["outputs"][0]["file"] = "../outside.jsonl"
    elif problem == "missing_revision":
        log = source / "reflection" / index["outputs"][0]["file"]
        rows = [json.loads(line) for line in log.read_text().splitlines()]
        log.write_text(
            "\n".join(json.dumps(row) for row in rows if row["stage"] != "revision")
        )
    else:
        sim["messages"][0]["content"] = "Different"
    path.write_text(json.dumps(index))
    with pytest.raises(ValueError):
        read_reflections(source, [sim])


class Span:
    def __init__(self, client, kwargs, parent=None):
        self.client = client
        self.id = str(len(client.rows) + 1)
        self.trace_id = kwargs.get("trace_context", {}).get("trace_id", "trace")
        client.rows.append({"id": self.id, "parent_observation_id": parent, **kwargs})

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def start_observation(self, **kwargs):
        return Span(self.client, kwargs, self.id)

    def end(self):
        pass


class Client:
    def __init__(self):
        self.rows = []

    def auth_check(self):
        return True

    def create_trace_id(self, **kwargs):
        return "trace"

    def start_as_current_observation(self, **kwargs):
        return Span(self, kwargs)

    def start_observation(self, **kwargs):
        return Span(self, kwargs, kwargs["trace_context"]["parent_span_id"])

    def flush(self):
        pass

    def get_trace_url(self, **kwargs):
        return "https://example.test/trace"


@pytest.mark.parametrize("existing_trace", [False, True])
@pytest.mark.parametrize("delivery_confirmed", [False, True])
def test_reflection_publication_preserves_hierarchy_and_usage_on_republication(
    recording, monkeypatch, existing_trace, delivery_confirmed
):
    from evals.langfuse_reflection import read_reflections

    source, sim = recording
    records = read_reflections(source, [sim])
    client = Client()
    monkeypatch.setattr("evals.langfuse_export.verify_delivery", lambda *a: None)
    monkeypatch.setattr("evals.langfuse_reflection.verify_delivery", lambda *a: None)
    monkeypatch.setattr(
        "evals.langfuse_reflection.remote_observations", lambda *a: client.rows
    )
    info = {
        "agent_info": {"llm": "agent-model"},
        "environment_info": {
            "domain_name": "mock",
            "policy": "Policy",
            "tool_defs": [],
        },
    }
    if existing_trace:
        with Ledger(source / "ledger", "test") as ledger:
            _export_selected(
                client, ledger, [sim], info, {}, "hash", "batch", {}, {}, None
            )
    if not delivery_confirmed:

        def reject_delivery(*args):
            raise ValueError("Delivery unconfirmed")

        monkeypatch.setattr(
            "evals.langfuse_reflection.verify_delivery", reject_delivery
        )
    for _ in range(2):
        expected = nullcontext() if delivery_confirmed else pytest.raises(ValueError)
        with Ledger(source / "ledger", "test") as ledger, expected:
            _export_selected(
                client,
                ledger,
                [sim],
                info,
                {},
                "hash",
                "batch",
                {},
                {},
                None,
                reflections=records,
            )
    workflows = [r for r in client.rows if r["name"] == "reflect-agent-response"]
    assert len(workflows) == 1
    parent = next(
        r
        for r in client.rows
        if r["name"] in {"generate-agent-response", "agent-response"}
    )
    assert workflows[0]["parent_observation_id"] == parent["id"]
    children = [
        r for r in client.rows if r["parent_observation_id"] == workflows[0]["id"]
    ]
    assert len(children) == 4
    assert sum(r.get("usage_details", {}).get("input", 0) for r in client.rows) == 12
    assert sum(
        r.get("cost_details", {}).get("total", 0) for r in client.rows
    ) == pytest.approx(1.2)
    assert workflows[0]["output"]["reason"] == "approved"
    review = next(r for r in children if r["name"] == "review-agent-draft")
    saved = [
        json.loads(line)
        for line in (source / "reflection" / ("a" * 32 + ".jsonl"))
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert review["output"]["decision"] == saved[3]["decision"]
    assert not any(r.get("name", "").startswith("judge.") for r in children)
