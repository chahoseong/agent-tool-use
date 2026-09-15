"""Publish a named set of completed judge runs as a Langfuse experiment."""

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

from evals.judge import digest
from evals.langfuse_export import export, judge_scores, read_judgments
from evals.langfuse_publication import (
    Ledger,
    experiment_identity,
    stable_id,
    verify_delivery,
)


def prepare_plan(plan: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(plan.get("name"), str) or not plan["name"].strip():
        raise ValueError("An approved experiment name is required")
    members = []
    seen: set[str] = set()
    identities = []
    for entry in plan["members"]:
        source, judge = Path(entry["source"]).resolve(), Path(entry["judge"]).resolve()
        data = json.loads((source / "results.json").read_text("utf-8"))
        # Require the end of local evaluation, even if some trials need attention.
        completion = json.loads((judge / "completion.json").read_text("utf-8"))
        results, judge_meta = read_judgments(judge, source)
        source_hash = digest(source / "results.json")
        identity = {"source": source_hash, "judge": digest(judge / "manifest.json")}
        identities.append(identity)
        domain = data["info"]["environment_info"]["domain_name"]
        tasks = {t["id"]: t for t in data["tasks"]}
        for sim in data["simulations"]:
            if (
                sim["id"] not in results
                or str(sim["trial"]) not in completion["trials"]
            ):
                raise ValueError("Every selected trial needs a finalized judge result")
            item = {
                "domain": domain,
                "task_id": sim["task_id"],
                "trial": sim["trial"],
                "seed": sim["seed"],
                "task": tasks[sim["task_id"]],
            }
            case_id = stable_id(item)
            if case_id in seen:
                raise ValueError("Duplicate comparison case in one experiment")
            seen.add(case_id)
            members.append(
                {
                    "source": source,
                    "judge": judge,
                    "source_hash": source_hash,
                    "judge_meta": judge_meta,
                    "simulation": sim,
                    "item": item,
                    "case_id": case_id,
                    "judge_result": results[sim["id"]],
                }
            )
    if not members:
        raise ValueError("Experiment has no cases")
    return experiment_identity(plan["name"], identities), members


def publish_experiment_item(
    client: Any,
    ledger: Ledger,
    key: str,
    item: Any,
    member: dict[str, Any],
    source_trace: dict[str, Any],
    name: str,
    run_name: str,
) -> dict[str, Any]:
    """Record saved output through the SDK runner; never execute the benchmark.

    v4 observations are immutable. A small experiment result trace links to the
    existing conversation, avoiding re-ingestion of model/tool observations.
    """
    receipt = ledger.get(key)
    if receipt is None:
        receipt = {
            "run_name": run_name,
            "dataset_item_id": item.id,
        }
        ledger.reserve(key, receipt)

        def saved_output(*, item: Any, **kwargs: Any) -> dict[str, Any]:
            receipt.update(
                trace_id=client.get_current_trace_id(),
                root_id=client.get_current_observation_id(),
            )
            # Persist identities before flushing so interrupted sends can be
            # inspected remotely without creating a second experiment item.
            ledger.update_pending(key, receipt)
            return {
                "source_trace_url": client.get_trace_url(
                    trace_id=source_trace["trace_id"]
                ),
                "judgment": member["judge_result"],
            }

        result = client.run_experiment(
            name=name,
            run_name=run_name,
            data=[item],
            task=saved_output,
            max_concurrency=1,
            metadata={"publication_mode": "saved-results", "display_name": name},
        )
        if not result.dataset_run_id or not receipt.get("root_id"):
            raise ValueError("SDK experiment registration incomplete; receipt pending")
        receipt.update(
            experiment_id=result.dataset_run_id,
            experiment_url=result.dataset_run_url,
        )
        ledger.update_pending(key, receipt)
        client.flush()
        verify_delivery(client, receipt["trace_id"], {receipt["root_id"]})
        ledger.confirm(key, receipt)

    scores = judge_scores(member["judge_result"])
    reward = (member["simulation"].get("reward_info") or {}).get("reward")
    if isinstance(reward, (int, float)):
        scores.append({"name": "tau2.reward", "value": reward, "data_type": "NUMERIC"})
    for score in scores:
        score_key = key + ":score:" + score["name"]
        if ledger.get(score_key):
            continue
        score_id = stable_id([key, score["name"]])
        ledger.reserve(
            score_key,
            {
                "score_id": score_id,
                "trace_id": receipt["trace_id"],
                "root_id": receipt["root_id"],
            },
        )
        client.api.scores.create(
            id=score_id,
            trace_id=receipt["trace_id"],
            observation_id=receipt["root_id"],
            metadata={"judge": member["judge_meta"]},
            **score,
        )
        ledger.confirm(score_key, {"score_id": score_id})
    return receipt


def publish(plan_path: Path) -> dict[str, Any]:
    from langfuse import Langfuse

    plan = json.loads(plan_path.read_text("utf-8"))
    experiment_id, members = prepare_plan(plan)
    # A stable dataset groups the exact same cases across independent executions.
    dataset_name = "tau2-" + stable_id(sorted(m["case_id"] for m in members))[:16]
    run_name = f"{plan['name']} [{experiment_id[:12]}]"
    sources = {(m["source"], m["judge"]) for m in members}
    trace_urls = []
    for source, judge in sorted(sources):
        trace_urls.extend(export(source, judge=judge))
    host = os.environ["LANGFUSE_BASE_URL"]
    project_key = stable_id([host, os.environ["LANGFUSE_PUBLIC_KEY"]])
    client = Langfuse(base_url=host, environment="evaluation", timeout=30)
    try:
        dataset = client.api.datasets.create(
            name=dataset_name,
            description="Saved tau2 mock cases; one domain/task/trial/seed per item",
        )
        experiment_receipts = []
        for member in members:
            sim = member["simulation"]
            with Ledger(member["source"] / "langfuse", project_key) as ledger:
                trace = ledger.get(
                    "trace:" + stable_id([member["source_hash"], sim["id"]])
                )
                judged = ledger.get(
                    "judge:"
                    + stable_id(
                        [member["source_hash"], sim["id"], member["judge_meta"]]
                    )
                )
                if trace is None or judged is None:
                    raise ValueError(
                        "Trace and judge publication must be confirmed first"
                    )
                item_id = stable_id([dataset_name, member["case_id"]])
                item = client.api.dataset_items.create(
                    dataset_name=dataset_name,
                    id=item_id,
                    input=member["item"],
                    metadata={
                        "case_id": member["case_id"],
                    },
                )
                key = "experiment-v4:" + stable_id([experiment_id, item_id])
                experiment_receipts.append(
                    publish_experiment_item(
                        client, ledger, key, item, member, trace, plan["name"], run_name
                    )
                )
        result = {
            "experiment_id": experiment_id,
            "name": plan["name"],
            "run_name": run_name,
            "dataset": dataset_name,
            "cloud_experiment_id": experiment_receipts[0]["experiment_id"],
            "experiment_url": experiment_receipts[0]["experiment_url"],
            "trace_urls": trace_urls,
            "dataset_url": f"{host.rstrip('/')}/project/{dataset.project_id}/datasets/{dataset.id}",
            "run_path": quote(run_name, safe=""),
        }
        receipt = plan_path.with_name(plan_path.stem + ".published.json")
        receipt.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return result
    finally:
        client.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    args = parser.parse_args()
    print(json.dumps(publish(args.plan), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
