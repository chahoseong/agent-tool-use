"""Validate and attach saved reflection calls to their official response."""

import json
import re
from pathlib import Path
from typing import Any

from evals.langfuse_publication import (
    Ledger,
    remote_observations,
    stable_id,
    verify_delivery,
)


def read_reflections(
    source: Path, simulations: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    from evals.langfuse_export import conversation_message

    directory = source / "reflection"
    index_path = directory / "index.json"
    if not index_path.exists():
        if any(
            (m.get("raw_data") or {}).get("_reflection_output_id")
            for s in simulations
            for m in s["messages"]
        ):
            raise ValueError("Reflection index is missing for recorded outputs")
        return {}
    selected = {s["id"]: s for s in simulations}
    result: dict[str, list[dict[str, Any]]] = {}
    seen: set[str] = set()
    for entry in json.loads(index_path.read_text("utf-8"))["outputs"]:
        if entry["status"] != "linked" or entry.get("simulation_id") not in selected:
            continue
        sim = selected[entry["simulation_id"]]
        output_id = entry["output_id"]
        index = entry["message_index"]
        if (
            not isinstance(output_id, str)
            or not re.fullmatch(r"[0-9a-f]{32}", output_id)
            or output_id in seen
            or entry["file"] != output_id + ".jsonl"
            or type(index) is not int
            or not 0 <= index < len(sim["messages"])
        ):
            raise ValueError("Invalid reflection output reference")
        seen.add(output_id)
        path = directory / entry["file"]
        if path.resolve().parent != directory.resolve():
            raise ValueError("Reflection log path escapes its directory")
        message = sim["messages"][index]
        if (
            message["role"] != "assistant"
            or (message.get("raw_data") or {}).get("_reflection_output_id") != output_id
            or any(entry.get(k) != sim.get(k) for k in ("task_id", "seed", "trial"))
        ):
            raise ValueError("Reflection identity does not match official output")
        events = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
        if (
            not events
            or events[-1].get("stage") != "final"
            or conversation_message(events[-1]["response"])
            != conversation_message(message)
        ):
            raise ValueError("Reflection final output does not match official output")
        count = events[-1].get("revision_count")
        if type(count) is not int or count < 0 or count > len(events):
            raise ValueError("Invalid reflection revision count")
        expected = ["draft_started", "draft", "review_started", "review"]
        expected += ["revision_started", "revision", "review_started", "review"] * count
        expected += ["final"]
        if [event.get("stage") for event in events] != expected:
            raise ValueError("Reflection log has missing or out-of-order calls")
        selected_response = events[-4]["response"]
        if conversation_message(selected_response) != conversation_message(message):
            raise ValueError("Selected generation does not match official output")
        for event in events:
            context = event.get("context", {})
            if (
                event.get("schema_version") != 1
                or event.get("output_id") != output_id
                or any(context.get(k) != sim.get(k) for k in ("task_id", "seed"))
            ):
                raise ValueError("Reflection event identity mismatch")
        result.setdefault(sim["id"], []).append(
            {
                "output_id": output_id,
                "message_index": index,
                "events": events,
                "fingerprint": stable_id(events),
            }
        )
    for sim in simulations:
        for message in sim["messages"]:
            output_id = (message.get("raw_data") or {}).get("_reflection_output_id")
            if output_id and output_id not in seen:
                raise ValueError("Official reflection output has no validated log link")
    return result


def call_records(
    record: dict[str, Any], model: str | None, *, selected_on_parent: bool
) -> list[dict[str, Any]]:
    from evals.langfuse_export import conversation_message

    events = record["events"]
    final_count = events[-1]["revision_count"]
    calls = []
    current_draft = None
    feedback = None
    started: dict[str, Any] = {}
    for event in events:
        stage = event["stage"]
        if stage.endswith("_started"):
            started = event
            continue
        if stage not in {"draft", "revision", "review"}:
            continue
        response = event.get("response") or {}
        selected = (
            stage in {"draft", "revision"} and event["revision_count"] == final_count
        )
        reference_only = selected and selected_on_parent
        usage = response.get("usage") or {}
        data: dict[str, Any] = {
            "name": {
                "draft": "generate-agent-draft",
                "revision": "revise-agent-draft",
                "review": "review-agent-draft",
            }[stage],
            "as_type": "span" if reference_only else "generation",
            "input": {"draft": current_draft, "feedback": feedback},
            "output": {
                "response": [conversation_message(response)] if response else None,
                "decision": event.get("decision"),
                "error": event.get("error"),
            },
            "level": "WARNING" if event.get("error") else "DEFAULT",
            "metadata": {
                "revision_count": event["revision_count"],
                "original_started_at": started.get("recorded_at"),
                "original_recorded_at": event.get("recorded_at"),
                "input_scope": "saved draft and feedback; full model request was not recorded",
                "selected_output": selected,
                "usage_on_parent": reference_only,
            },
        }
        if not reference_only:
            data["model"] = started.get("model") or model
            data["usage_details"] = {
                target: usage[source]
                for source, target in (
                    ("prompt_tokens", "input"),
                    ("completion_tokens", "output"),
                )
                if source in usage
            }
            if response.get("cost") is not None:
                data["cost_details"] = {"total": response["cost"]}
        if stage == "review":
            feedback = event.get("decision")
        else:
            current_draft = conversation_message(response)
        calls.append(data)
    return calls


def attach_reflections(
    client: Any,
    ledger: Ledger,
    trace: dict[str, Any],
    simulation: dict[str, Any],
    records: list[dict[str, Any]],
    source_hash: str,
    info: dict[str, Any],
) -> None:
    if not records:
        return
    parents = trace.get("agent_observations")
    if parents is None:
        parents = {}
        for row in remote_observations(client, trace["trace_id"]):
            if row.get("name") not in {"generate-agent-response", "agent-response"}:
                continue
            index = str(row.get("metadata", {}).get("message_index"))
            if index in parents:
                raise ValueError("Ambiguous agent observation for reflection")
            parents[index] = {
                "id": row["id"],
                "selected_on_parent": row["name"] == "generate-agent-response",
            }
    for record in records:
        key = "reflection:" + stable_id(
            [source_hash, simulation["id"], record["output_id"]]
        )
        receipt = ledger.get(key)
        if receipt:
            if receipt["fingerprint"] != record["fingerprint"]:
                raise ValueError(
                    "Published reflection log has changed; inspect before replacing"
                )
            continue
        parent = parents.get(str(record["message_index"]))
        if parent is None:
            raise ValueError(
                "Cannot locate official response observation for reflection"
            )
        ledger.reserve(
            key, {"trace_id": trace["trace_id"], "fingerprint": record["fingerprint"]}
        )
        final = record["events"][-1]
        root = client.start_observation(
            trace_context={
                "trace_id": trace["trace_id"],
                "parent_span_id": parent["id"],
            },
            name="reflect-agent-response",
            as_type="span",
            input={"message_index": record["message_index"]},
            output={
                "reason": final["reason"],
                "revision_count": final["revision_count"],
            },
            level="DEFAULT" if final["reason"] == "approved" else "WARNING",
            metadata={
                "output_id": record["output_id"],
                "source_sha256": source_hash,
                "reflection_sha256": record["fingerprint"],
                "imported_recording": True,
            },
        )
        required = {root.id}
        for call in call_records(
            record,
            info.get("agent_info", {}).get("llm"),
            selected_on_parent=parent["selected_on_parent"],
        ):
            child = root.start_observation(**call)
            required.add(child.id)
            child.end()
        root.end()
        client.flush()
        verify_delivery(client, trace["trace_id"], required)
        ledger.confirm(
            key,
            {
                "trace_id": trace["trace_id"],
                "root_id": root.id,
                "fingerprint": record["fingerprint"],
            },
        )
