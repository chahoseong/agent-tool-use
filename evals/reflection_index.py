"""Link local reflection output IDs to saved official simulation messages."""

import json
from pathlib import Path
from typing import Any


def write_reflection_index(run_directory: Path) -> None:
    """Preserve unmatched attempts; never infer a simulation from matching text."""
    directory = run_directory / "reflection"
    if not directory.exists():
        return
    results_path = run_directory / "results.json"
    results_status = "available"
    try:
        simulations = json.loads(results_path.read_text(encoding="utf-8")).get(
            "simulations", []
        )
    except (OSError, UnicodeError, json.JSONDecodeError):
        # A failed run may have no checkpoint or an interrupted checkpoint write.
        # Keep the original artifacts and index the logs without guessing links.
        simulations = []
        results_status = "unavailable"
    references: dict[str, list[dict[str, Any]]] = {}
    for simulation in simulations:
        for message_index, message in enumerate(simulation.get("messages", [])):
            output_id = (message.get("raw_data") or {}).get("_reflection_output_id")
            if message.get("role") != "assistant" or not isinstance(output_id, str):
                continue
            references.setdefault(output_id, []).append(
                {
                    "simulation_id": simulation["id"],
                    "task_id": simulation["task_id"],
                    "trial": simulation.get("trial"),
                    "seed": simulation.get("seed"),
                    "message_index": message_index,
                    "turn_idx": message.get("turn_idx"),
                }
            )

    entries: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.jsonl")):
        events = []
        incomplete = False
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                incomplete = True
                break
        context = events[0].get("context", {}) if events else {}
        entry: dict[str, Any] = {
            "output_id": path.stem,
            "file": path.name,
            "context": context,
            "status": "unlinked",
        }
        candidates = references.get(path.stem, [])
        if incomplete or not events:
            entry["status"] = "incomplete_log"
        elif len(candidates) > 1:
            entry["status"] = "ambiguous"
        elif len(candidates) == 1:
            reference = candidates[0]
            if (
                context.get("task_id") == reference["task_id"]
                and context.get("seed") == reference["seed"]
                and events[-1].get("stage") == "final"
            ):
                entry.update(reference, status="linked")
            else:
                entry["status"] = "context_mismatch"
        entries.append(entry)
    (directory / "index.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "message_index_base": 0,
                "results_status": results_status,
                "outputs": entries,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
