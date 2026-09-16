"""Export saved mock evaluations to Langfuse without re-running the agent."""

import argparse
import hashlib
import json
import os
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from evals.judge import Judgment
from evals.langfuse_publication import (
    Ledger,
    attach_judge,
    remote_observations,
    stable_id,
    verify_delivery,
)
from evals.langfuse_reflection import attach_reflections, read_reflections


def conversation_message(message: dict[str, Any]) -> dict[str, Any]:
    """Use Langfuse's OpenAI chat format, excluding provider/raw credentials."""
    result: dict[str, Any] = {
        k: message[k] for k in ("role", "content", "tool_call_id") if k in message
    }
    if message.get("tool_calls"):
        result["tool_calls"] = [
            {
                "id": c["id"],
                "type": "function",
                "function": {
                    "name": c["name"],
                    "arguments": json.dumps(c["arguments"], ensure_ascii=False),
                },
            }
            for c in message["tool_calls"]
        ]
    return result


def observations(
    messages: list[dict[str, Any]], info: dict[str, Any]
) -> list[dict[str, Any]]:
    records = []
    returned = {m.get("tool_call_id"): m for m in messages if m["role"] == "tool"}
    history: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        role = message["role"]
        chat = conversation_message(message)
        if role in ("assistant", "user"):
            actor = "agent" if role == "assistant" else "user"
            usage = message.get("usage") or {}
            records.append(
                {
                    "name": f"generate-{actor}-response",
                    "as_type": "generation",
                    "model": info.get(f"{actor}_info", {}).get("llm"),
                    "input": list(history),
                    "output": [chat],
                    "usage_details": {
                        target: usage[source]
                        for source, target in (
                            ("prompt_tokens", "input"),
                            ("completion_tokens", "output"),
                        )
                        if source in usage
                    },
                    "metadata": {
                        "message_index": index,
                        "original_timestamp": message.get("timestamp"),
                        "original_generation_seconds": message.get(
                            "generation_time_seconds"
                        ),
                        "input_scope": "recorded dialogue prefix; not a reconstructed model request",
                        "delivered_to_user": role == "assistant"
                        and not message.get("tool_calls"),
                    },
                }
            )
            if message.get("cost") is not None:
                records[-1]["cost_details"] = {"total": message["cost"]}
            for call in message.get("tool_calls") or []:
                response = returned.get(call["id"])
                records.append(
                    {
                        "name": call["name"],
                        "as_type": "tool",
                        "input": call["arguments"],
                        "output": response.get("content") if response else None,
                        "level": "DEFAULT" if response else "WARNING",
                        "metadata": {
                            "call_id": call["id"],
                            "message_index": index,
                            "result_observed": response is not None,
                            "original_timestamp": response.get("timestamp")
                            if response
                            else None,
                        },
                    }
                )
        history.append(chat)
    return records


def judge_scores(result: dict[str, Any]) -> list[dict[str, Any]]:
    if result["status"] != "completed":
        return []
    return [
        {
            "name": f"judge.{a['criterion_id']}",
            "value": a["verdict"],
            "data_type": "CATEGORICAL",
            "comment": "\n\n".join(
                [
                    a["reason"],
                    *[e["excerpt"] for e in a["evidence"]],
                    a.get("evidence_limit", ""),
                ]
            ).strip(),
        }
        for a in result["assessments"]
    ]


def read_judgments(
    directory: Path, source: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads((directory / "manifest.json").read_text("utf-8"))
    for name in ("results.json", "metadata.toml"):
        if (
            hashlib.sha256((source / name).read_bytes()).hexdigest()
            != manifest["source_hashes"][name]
        ):
            raise ValueError("Judge source hashes do not match this evaluation")
    results = {}
    for item in manifest["trials"]:
        result = Judgment.model_validate_json(
            (directory / f"trial_{item['trial']}.json").read_text("utf-8")
        )
        if (
            result.simulation_id != item["simulation_id"]
            or result.trial != item["trial"]
        ):
            raise ValueError("Judge result identity mismatch")
        if result.status == "completed" and not result.review.verified:
            raise ValueError("Judge result has not been verified")
        results[result.simulation_id] = result.model_dump()
    return results, {
        k: manifest[k]
        for k in (
            "model",
            "reasoning_effort",
            "criteria_version",
            "resource_hashes",
            "created_at",
        )
    }


def export(
    source: Path,
    *,
    trial: int | None = None,
    judge: Path | None = None,
    adopt_trace: str | None = None,
) -> list[str]:
    # Import after the caller has loaded .env, as required by the SDK.
    from langfuse import Langfuse

    required = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")
    if any(not os.getenv(key) for key in required):
        raise ValueError(
            "Set LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY and LANGFUSE_BASE_URL"
        )
    host = os.environ["LANGFUSE_BASE_URL"]
    parsed = urlparse(host)
    if parsed.scheme != "https" or parsed.username or parsed.password:
        raise ValueError("Use the HTTPS Langfuse Cloud project URL without credentials")
    if os.getenv("LANGFUSE_TRACING_ENABLED", "true").lower() == "false":
        raise ValueError("Langfuse tracing is disabled")
    data = json.loads((source / "results.json").read_text("utf-8"))
    meta = tomllib.loads((source / "metadata.toml").read_text("utf-8"))
    simulations = [
        s for s in data["simulations"] if trial is None or s["trial"] == trial
    ]
    if not simulations:
        raise ValueError("No matching saved trials")
    judgments, judge_meta = read_judgments(judge, source) if judge else ({}, {})
    reflections = read_reflections(source, simulations)
    info = data["info"]
    batch = uuid4().hex
    source_hash = hashlib.sha256((source / "results.json").read_bytes()).hexdigest()
    client = Langfuse(base_url=host, environment="evaluation", timeout=30)
    project_key = stable_id([host, os.environ["LANGFUSE_PUBLIC_KEY"]])
    ledger = Ledger(source / "langfuse", project_key)
    if adopt_trace and len(simulations) != 1:
        raise ValueError("Adopting a trace requires exactly one selected simulation")
    try:
        with ledger:
            return _export_selected(
                client,
                ledger,
                simulations,
                info,
                meta,
                source_hash,
                batch,
                judgments,
                judge_meta,
                adopt_trace,
                reflections=reflections,
            )
    finally:
        client.shutdown()


def _export_selected(
    client: Any,
    ledger: Ledger,
    simulations: list[dict[str, Any]],
    info: dict[str, Any],
    meta: dict[str, Any],
    source_hash: str,
    batch: str,
    judgments: dict[str, Any],
    judge_meta: dict[str, Any],
    adopt_trace: str | None,
    *,
    reflections: dict[str, list[dict[str, Any]]] | None = None,
) -> list[str]:
    from langfuse import propagate_attributes

    urls = []
    if not client.auth_check():
        raise ValueError("Langfuse project authentication failed")
    for simulation in simulations:
        reflection_records = (reflections or {}).get(simulation["id"], [])
        key = "trace:" + stable_id([source_hash, simulation["id"]])
        if adopt_trace:
            rows = remote_observations(client, adopt_trace)
            roots = [r for r in rows if not r.get("parent_observation_id")]
            if (
                len(roots) != 1
                or roots[0].get("metadata", {}).get("source_sha256") != source_hash
                or roots[0].get("metadata", {}).get("simulation_id") != simulation["id"]
            ):
                raise ValueError("Existing trace does not match source and simulation")
            expected_count = 1 + len(observations(simulation["messages"], info))
            if len(rows) < expected_count:
                raise ValueError(
                    "Existing trace is incomplete; inspect missing observations"
                )
            old = ledger.data.get(key)
            if old and old["trace_id"] != adopt_trace:
                raise ValueError("A different trace is already recorded")
            scores = client.api.scores_v3.get_many_v3(
                trace_id=adopt_trace, observation_id=roots[0]["id"], name="tau2.reward"
            )
            if len(scores.data) > 1:
                raise ValueError(
                    "Existing official scores are duplicated; inspect before adopting"
                )
            adopted = {"trace_id": adopt_trace, "root_id": roots[0]["id"]}
            if scores.data:
                adopted["official_score_id"] = scores.data[0].id
            ledger.confirm(key, adopted)
        receipt = ledger.get(key)
        if receipt:
            attach_reflections(
                client,
                ledger,
                receipt,
                simulation,
                reflection_records,
                source_hash,
                info,
            )
            _finish_trial(
                client, ledger, receipt, simulation, judgments, judge_meta, source_hash
            )
            urls.append(client.get_trace_url(trace_id=receipt["trace_id"]))
            continue
        trace_id = client.create_trace_id(seed=key)
        ledger.reserve(key, {"trace_id": trace_id})
        messages = simulation["messages"]
        visible = [
            conversation_message(m)
            for m in messages
            if m["role"] in ("assistant", "user") and not m.get("tool_calls")
        ]
        metadata = {
            "domain": info["environment_info"]["domain_name"],
            "task_id": simulation["task_id"],
            "trial": simulation["trial"],
            "seed": simulation.get("seed"),
            "simulation_id": simulation["id"],
            "source_sha256": source_hash,
            "import_batch": batch,
            "imported_recording": True,
            "timing_note": "Trace timing measures import; original timings are in metadata",
            "original_start_time": simulation.get("start_time"),
            "original_end_time": simulation.get("end_time"),
            "original_duration_seconds": simulation.get("duration"),
            "termination_reason": simulation.get("termination_reason"),
            "project_commit": meta.get("project", {}).get("commit"),
            "agent_prompt": meta.get("prompts", {}).get("agent"),
            "policy": simulation.get("policy") or info["environment_info"]["policy"],
            "tools": info["environment_info"]["tool_defs"],
            "judge": judge_meta,
        }
        # This exporter is for official synthetic mock-domain records. Do not
        # copy arbitrary config/raw_data dictionaries, which may hold keys.
        with (
            propagate_attributes(
                session_id=simulation["id"],
                tags=["tau2-bench", "imported-recording"],
            ),
            client.start_as_current_observation(
                name="evaluate-task",
                trace_context={"trace_id": trace_id},
                as_type="agent",
                input=visible[:1],
                output=visible[1:],
                metadata=metadata,
            ) as root,
        ):
            required = {root.id}
            agent_observations = {}
            reflected_indices = {r["message_index"] for r in reflection_records}
            for record in observations(messages, info):
                is_agent = record["name"] == "generate-agent-response"
                message_index = record["metadata"]["message_index"]
                reflected = is_agent and message_index in reflected_indices
                if reflected:
                    record["name"] = "agent-response"
                    record["as_type"] = "agent"
                    for field in ("usage_details", "cost_details", "model"):
                        record.pop(field, None)
                child = root.start_observation(**record)
                if is_agent:
                    agent_observations[str(message_index)] = {
                        "id": child.id,
                        "selected_on_parent": not reflected,
                    }
                required.add(child.id)
                child.end()
            receipt = {
                "trace_id": root.trace_id,
                "root_id": root.id,
                "agent_observations": agent_observations,
            }
        client.flush()
        verify_delivery(client, trace_id, required)
        ledger.confirm(key, receipt)
        attach_reflections(
            client, ledger, receipt, simulation, reflection_records, source_hash, info
        )
        _finish_trial(
            client, ledger, receipt, simulation, judgments, judge_meta, source_hash
        )
        urls.append(client.get_trace_url(trace_id=trace_id))
    client.flush()
    return urls


def _finish_trial(
    client: Any,
    ledger: Ledger,
    receipt: dict[str, Any],
    simulation: dict[str, Any],
    judgments: dict[str, Any],
    judge_meta: dict[str, Any],
    source_hash: str,
) -> None:
    reward = simulation.get("reward_info") or {}
    if isinstance(reward.get("reward"), (int, float)):
        client.api.scores.create(
            id=receipt.get("official_score_id")
            or stable_id(["tau2.reward", receipt["trace_id"]]),
            name="tau2.reward",
            value=reward["reward"],
            trace_id=receipt["trace_id"],
            observation_id=receipt["root_id"],
            data_type="NUMERIC",
            comment="Official tau2 evaluator reward",
        )
    result = judgments.get(simulation["id"])
    if result:
        attach_judge(client, ledger, receipt, result, judge_meta, source_hash)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--trial", type=int)
    parser.add_argument("--judge", type=Path, help="Completed llm-judge run directory")
    parser.add_argument(
        "--adopt-trace", help="Verified existing trace ID; requires --trial"
    )
    args = parser.parse_args()
    for url in export(
        args.directory, trial=args.trial, judge=args.judge, adopt_trace=args.adopt_trace
    ):
        print(url)


if __name__ == "__main__":
    main()
