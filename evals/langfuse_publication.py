"""Durable, project-scoped receipts for Langfuse publication."""

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Self


def stable_id(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def experiment_identity(name: str, members: list[dict[str, str]]) -> str:
    return stable_id(
        [name, sorted(members, key=lambda item: (item["source"], item["judge"]))]
    )


class Ledger:
    """Fail closed after uncertain uploads; never infer delivery from flush()."""

    def __init__(self, directory: Path, project: str):
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"{project}.json"
        self.lock = directory / f"{project}.lock"
        self.data: dict[str, Any] = {}

    def __enter__(self) -> Self:
        with self.lock.open("x") as stream:
            stream.write(
                "Publication in progress. Inspect before recovering a stale lock.\n"
            )
        try:
            if self.path.exists():
                self.data = json.loads(self.path.read_text("utf-8"))
        except BaseException:
            self.lock.unlink()
            raise
        return self

    def __exit__(self, *args: object) -> None:
        self.lock.unlink()

    def get(self, key: str) -> dict[str, Any] | None:
        value = self.data.get(key)
        if value and value["status"] != "confirmed":
            raise ValueError(
                f"Publication uncertain: {key}. Verify the recorded trace before retrying."
            )
        return value

    def _write(self) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        for attempt in range(5):
            try:
                temporary.replace(self.path)
                break
            except PermissionError:
                if attempt == 4:
                    raise
                # Windows readers/antivirus can briefly hold the destination.
                time.sleep(0.05 * (2**attempt))

    def reserve(self, key: str, value: dict[str, Any]) -> None:
        if key in self.data:
            raise ValueError("Publication already reserved")
        self.data[key] = {**value, "status": "pending"}
        self._write()

    def confirm(self, key: str, value: dict[str, Any]) -> None:
        self.data[key] = {**value, "status": "confirmed"}
        self._write()

    def update_pending(self, key: str, value: dict[str, Any]) -> None:
        if self.data[key]["status"] != "pending":
            raise ValueError("Only pending publication can be updated")
        self.data[key].update(value)
        self._write()


def remote_observations(client: Any, trace_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cursor = None
    while True:
        response = client.api.observations.get_many(
            trace_id=trace_id,
            fields="core,basic,metadata",
            expand_metadata="source_sha256,simulation_id",
            limit=1000,
            cursor=cursor,
        )
        rows.extend(row.model_dump(by_alias=True) for row in response.data)
        cursor = response.meta.cursor
        if not cursor:
            return rows


def verify_delivery(client: Any, trace_id: str, required: set[str]) -> None:
    # Ingestion is asynchronous: flush() can finish before the read index catches up.
    # Bound the wait while allowing normal indexing delays without re-uploading.
    for delay in (0, 2, 4, 8, 16):
        if delay:
            time.sleep(delay)
        if required <= {row["id"] for row in remote_observations(client, trace_id)}:
            return
    raise ValueError(
        "Cloud delivery is not confirmed; publication receipt remains pending"
    )


def attach_judge(
    client: Any,
    ledger: Ledger,
    trace: dict[str, Any],
    result: dict[str, Any],
    judge_meta: dict[str, Any],
    source_hash: str,
) -> dict[str, Any]:
    from evals.langfuse_export import judge_scores

    key = "judge:" + stable_id([source_hash, result["simulation_id"], judge_meta])
    receipt = ledger.get(key)
    if receipt is None:
        ledger.reserve(key, {"trace_id": trace["trace_id"]})
        child = client.start_observation(
            trace_context={
                "trace_id": trace["trace_id"],
                "parent_span_id": trace["root_id"],
            },
            name="judge-trial",
            as_type="evaluator",
            input={"simulation_id": result["simulation_id"]},
            output=result,
            metadata={"judge": judge_meta, "assessment_status": result["status"]},
        )
        receipt = {"trace_id": trace["trace_id"], "root_id": child.id}
        child.end()
        client.flush()
        verify_delivery(client, trace["trace_id"], {child.id})
        ledger.confirm(key, receipt)
    for score in judge_scores(result):
        # Synchronous upsert: a retry after a lost response reuses the score ID.
        client.api.scores.create(
            id=stable_id([key, score["name"]]),
            trace_id=trace["trace_id"],
            observation_id=receipt["root_id"],
            metadata={"judge": judge_meta},
            **score,
        )
    return receipt
