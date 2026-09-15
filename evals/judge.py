"""Offline input preparation and immutable storage for Codex judge subagents."""

import argparse
import hashlib
import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

SKILL = Path(__file__).resolve().parents[1] / ".agents/skills/judge-evaluation"
Text = Annotated[str, Field(min_length=1, pattern=r"\S")]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Evidence(Record):
    message_index: int = Field(ge=0)
    field: Literal["content", "tool_calls"]
    excerpt: Text


class Assessment(Record):
    criterion_id: Text
    verdict: Literal["pass", "fail", "unknown", "-"]
    reason: Text
    evidence: list[Evidence]
    evidence_limit: str


class Attempt(Record):
    kind: Literal["execution", "review"]
    detail: Text


class Review(Record):
    verified: bool
    notes: Text


class Judgment(Record):
    trial: int = Field(ge=0)
    simulation_id: Text
    status: Literal["completed", "evaluation_failed", "review_required"]
    assessments: list[Assessment]
    attempts: list[Attempt]
    review: Review


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: Any) -> None:
    # Exclusive creation protects previous attempts even during concurrent writes.
    encoded = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(encoded + "\n")


def prepare(root: Path, model: str = "gpt-6-astra", effort: str = "high") -> Path:
    root = root.resolve()
    data = json.loads((root / "results.json").read_text(encoding="utf-8"))
    tomllib.loads((root / "metadata.toml").read_text(encoding="utf-8"))
    environment = data["info"]["environment_info"]
    criteria = json.loads((SKILL / "references/criteria.json").read_text("utf-8"))
    domain = environment["domain_name"]
    tasks = {task["id"]: task for task in data["tasks"]}
    inputs = []
    seen = set()
    for sim in data["simulations"]:
        trial = sim["trial"]
        if type(trial) is not int or trial < 0 or trial in seen:
            raise ValueError("Expected one task per run and unique nonnegative trials")
        seen.add(trial)
        key = f"{domain}/{sim['task_id']}"
        if key not in criteria["tasks"]:
            raise ValueError(f"No approved criteria for {key}")
        task = tasks[sim["task_id"]]
        # Allowlist: official reward, reference actions, reviews and run labels
        # are never sent to the judge. Tool outcomes remain evidence.
        inputs.append(
            {
                "trial": trial,
                "simulation_id": sim["id"],
                "task_id": sim["task_id"],
                "domain": domain,
                "task": {
                    k: task[k] for k in ("id", "user_scenario", "ticket") if k in task
                },
                "policy": sim.get("policy") or environment["policy"],
                "tools": environment["tool_defs"],
                "messages": [
                    {
                        k: msg[k]
                        for k in (
                            "role",
                            "content",
                            "tool_calls",
                            "tool_call_id",
                            "name",
                        )
                        if k in msg
                    }
                    for msg in sim["messages"]
                ],
                "criteria": criteria["common"] + criteria["tasks"][key],
            }
        )
    if not inputs:
        raise ValueError("No saved simulations to judge")
    run = (
        root
        / "llm-judge"
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ_") + uuid4().hex)
    )
    (run / "inputs").mkdir(parents=True)
    for payload in inputs:
        write_new(run / "inputs" / f"trial_{payload['trial']}.json", payload)
    # Snapshot instructions: later edits must not change an existing judge run.
    for name in ("judge.md", "criteria.json"):
        (run / name).write_bytes((SKILL / "references" / name).read_bytes())
    write_new(run / "schema.json", Judgment.model_json_schema())
    write_new(
        run / "manifest.json",
        {
            "schema_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "source": str(root),
            "source_hashes": {
                name: digest(root / name) for name in ("results.json", "metadata.toml")
            },
            "model": model,
            "reasoning_effort": effort,
            "criteria_version": criteria["version"],
            "resource_hashes": {
                name: digest(run / name)
                for name in ("judge.md", "criteria.json", "schema.json")
            },
            "trials": [
                {
                    "trial": p["trial"],
                    "simulation_id": p["simulation_id"],
                    "input_sha256": digest(run / "inputs" / f"trial_{p['trial']}.json"),
                }
                for p in inputs
            ],
            "status": "prepared",
        },
    )
    return run


def save_result(run: Path, raw: Any) -> None:
    result = Judgment.model_validate(raw)
    manifest = json.loads((run / "manifest.json").read_text("utf-8"))
    item = next((x for x in manifest["trials"] if x["trial"] == result.trial), None)
    if item is None or result.simulation_id != item["simulation_id"]:
        raise ValueError("Judgment does not identify the prepared simulation")
    input_path = run / "inputs" / f"trial_{result.trial}.json"
    if digest(input_path) != item["input_sha256"]:
        raise ValueError("Judge input changed")
    for name, expected in manifest["source_hashes"].items():
        if digest(Path(manifest["source"]) / name) != expected:
            raise ValueError("Source changed; prepare a new judge run")
    payload = json.loads(input_path.read_text("utf-8"))
    expected_ids = {c["id"] for c in payload["criteria"]}
    ids = [a.criterion_id for a in result.assessments]
    if len(ids) != len(set(ids)) or not set(ids) <= expected_ids:
        raise ValueError("Duplicate or unknown criterion")
    if result.status == "completed" and (
        set(ids) != expected_ids or not result.review.verified
    ):
        raise ValueError("Completed judgments require all criteria and verified review")
    if result.status != "completed" and result.review.verified:
        raise ValueError("Unresolved judgments cannot be verified")
    for kind, limit in (("execution", 3), ("review", 2)):
        count = sum(a.kind == kind for a in result.attempts)
        if count > limit or (kind == "execution" and count == 0):
            raise ValueError("Invalid retry history")
    for assessment in result.assessments:
        if not assessment.evidence and not assessment.evidence_limit.strip():
            raise ValueError("Missing evidence needs an explicit explanation")
        for evidence in assessment.evidence:
            if evidence.message_index >= len(payload["messages"]):
                raise ValueError("Evidence message does not exist")
            value = payload["messages"][evidence.message_index].get(evidence.field)
            actual = (
                value
                if isinstance(value, str)
                else json.dumps(value, ensure_ascii=False)
            )
            if value is None or evidence.excerpt not in actual:
                raise ValueError("Evidence excerpt does not match the original value")
    write_new(run / f"trial_{result.trial}.json", result.model_dump())


def finalize(run: Path) -> None:
    manifest = json.loads((run / "manifest.json").read_text("utf-8"))
    states = {}
    for item in manifest["trials"]:
        path = run / f"trial_{item['trial']}.json"
        states[str(item["trial"])] = (
            Judgment.model_validate_json(path.read_text("utf-8")).status
            if path.exists()
            else "pending"
        )
    if "pending" in states.values():
        raise ValueError("Save a result or failure record for every trial first")
    write_new(
        run / "completion.json",
        {
            "finished_at": datetime.now(UTC).isoformat(),
            "trials": states,
            "status": "completed"
            if all(s == "completed" for s in states.values())
            else "needs_attention",
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "save", "finalize"])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--model", default="gpt-6-astra")
    parser.add_argument("--effort", default="high")
    args = parser.parse_args()
    if args.command == "prepare":
        print(prepare(args.directory, args.model, args.effort))
    elif args.command == "save":
        if args.result is None:
            parser.error("save requires --result")
        save_result(args.directory, json.loads(args.result.read_text("utf-8")))
    else:
        finalize(args.directory)


if __name__ == "__main__":
    main()
