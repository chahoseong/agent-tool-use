import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from evals.judge import finalize, prepare, save_result
from evals.langfuse_export import _export_selected
from evals.langfuse_publication import Ledger, experiment_identity, verify_delivery
from evals.publish_evaluation import prepare_plan, publish_experiment_item


def test_publication_ledger_preserves_confirmed_trace_across_restarts(tmp_path):
    with Ledger(tmp_path, "project") as ledger:
        ledger.reserve("source", {"trace_id": "trace"})
        ledger.confirm("source", {"trace_id": "trace", "root_id": "root"})
    with Ledger(tmp_path, "project") as ledger:
        receipt = ledger.get("source")
        assert receipt is not None
        assert receipt["root_id"] == "root"


def test_publication_ledger_blocks_duplicate_upload_after_uncertain_failure(tmp_path):
    with Ledger(tmp_path, "project") as ledger:
        ledger.reserve("source", {"trace_id": "trace"})
    with (
        Ledger(tmp_path, "project") as ledger,
        pytest.raises(ValueError, match="uncertain"),
    ):
        ledger.get("source")


def test_publication_ledger_rejects_concurrent_writers(tmp_path):
    with (
        Ledger(tmp_path, "project"),
        pytest.raises(FileExistsError),
        Ledger(tmp_path, "project"),
    ):
        pass


def test_publication_ledger_preserves_receipt_after_transient_file_lock(
    tmp_path, monkeypatch
):
    original = Path.replace
    locked = True

    def replace(path, target):
        nonlocal locked
        if locked:
            locked = False
            raise PermissionError("Windows reader temporarily holds destination")
        return original(path, target)

    monkeypatch.setattr(Path, "replace", replace)
    monkeypatch.setattr("evals.langfuse_publication.time.sleep", lambda _: None)
    with Ledger(tmp_path, "project") as ledger:
        ledger.reserve("score", {"score_id": "id"})
    assert (
        json.loads((tmp_path / "project.json").read_text())["score"]["status"]
        == "pending"
    )


def test_delivery_verification_confirms_observations_after_indexing_delay(monkeypatch):
    elapsed = 0

    def advance(seconds):
        nonlocal elapsed
        elapsed += seconds

    monkeypatch.setattr("evals.langfuse_publication.time.sleep", advance)
    monkeypatch.setattr(
        "evals.langfuse_publication.remote_observations",
        lambda *args: [{"id": "judge"}] if elapsed >= 20 else [],
    )
    verify_delivery(object(), "trace", {"judge"})
    assert 20 <= elapsed <= 60


def test_delivery_verification_stops_when_observations_remain_missing(monkeypatch):
    waits = []
    monkeypatch.setattr("evals.langfuse_publication.time.sleep", waits.append)
    monkeypatch.setattr(
        "evals.langfuse_publication.remote_observations", lambda *args: []
    )
    with pytest.raises(ValueError, match="receipt remains pending"):
        verify_delivery(object(), "trace", {"missing"})
    assert sum(waits) <= 60


def test_experiment_publication_reuses_saved_judgment_and_registered_item(
    tmp_path, monkeypatch
):
    """A legacy REST link alone does not populate the v4 experiment view."""
    client = FakeClient()
    executions = []
    client.get_current_observation_id = lambda: "item-root"
    client.get_current_trace_id = lambda: "item-trace"

    def run_experiment(**kwargs):
        executions.append(kwargs)
        assert kwargs["data"] == [item]
        output = kwargs["task"](item=item)
        assert output["judgment"] == member["judge_result"]
        assert output["source_trace_url"] == "https://example.test/source-trace"
        return SimpleNamespace(
            dataset_run_id="cloud-run", dataset_run_url="https://example.test/run"
        )

    client.run_experiment = run_experiment
    monkeypatch.setattr("evals.publish_evaluation.verify_delivery", lambda *a: None)
    item = SimpleNamespace(id="case")
    member = {
        "judge_result": {
            "status": "completed",
            "assessments": [
                {
                    "criterion_id": "consent",
                    "verdict": "pass",
                    "reason": "Confirmed before action",
                    "evidence": [{"excerpt": "Yes, cancel it."}],
                    "evidence_limit": "",
                }
            ],
        },
        "judge_meta": {"model": "judge"},
        "simulation": {"reward_info": {"reward": 0}},
    }
    for _ in range(2):
        with Ledger(tmp_path, "project") as ledger:
            receipt = publish_experiment_item(
                client,
                ledger,
                "experiment-v4:key",
                item,
                member,
                {"trace_id": "source-trace"},
                "approved name",
                "run name",
            )
    assert len(executions) == 1
    assert receipt["experiment_id"] == "cloud-run"
    assert len(client.scores) == 2
    judge_score = next(
        s for s in client.scores.values() if s["name"] == "judge.consent"
    )
    assert judge_score["observation_id"] == "item-root"
    assert "Yes, cancel it." in judge_score["comment"]
    assert client.score_writes == 2


def test_experiment_identity_changes_for_new_judgment_but_not_source_order():
    first = experiment_identity(
        "P1", [{"source": "a", "judge": "j1"}, {"source": "b", "judge": "j2"}]
    )
    assert first == experiment_identity(
        "P1", [{"source": "b", "judge": "j2"}, {"source": "a", "judge": "j1"}]
    )
    assert first != experiment_identity(
        "P1", [{"source": "a", "judge": "j3"}, {"source": "b", "judge": "j2"}]
    )


class FakeClient:
    def __init__(self):
        self.created = 0
        self.scores = {}
        self.score_writes = 0
        self.api = SimpleNamespace(scores=SimpleNamespace(create=self.save_score))

    def save_score(
        self,
        *,
        id,
        name,
        value,
        trace_id,
        observation_id,
        data_type,
        metadata=None,
        comment=None,
    ):
        kwargs = {
            "id": id,
            "name": name,
            "value": value,
            "trace_id": trace_id,
            "observation_id": observation_id,
            "data_type": data_type,
            "metadata": metadata,
            "comment": comment,
        }
        self.score_writes += 1
        self.scores[kwargs["id"]] = kwargs

    def auth_check(self):
        return True

    def create_trace_id(self, *, seed):
        return seed[-32:]

    def start_as_current_observation(self, **kwargs):
        self.created += 1
        return FakeSpan(kwargs["trace_context"]["trace_id"])

    def flush(self):
        pass

    def get_trace_url(self, *, trace_id):
        return "https://example.test/" + trace_id


def test_adoption_reuses_existing_root_and_official_score(tmp_path, monkeypatch):
    client = FakeClient()
    client.api.scores_v3 = SimpleNamespace(
        get_many_v3=lambda **kw: SimpleNamespace(data=[SimpleNamespace(id="old-score")])
    )
    monkeypatch.setattr(
        "evals.langfuse_export.remote_observations",
        lambda *args: [
            {
                "id": "root",
                "parent_observation_id": None,
                "metadata": {"source_sha256": "hash", "simulation_id": "sim"},
            },
            {"id": "child", "parent_observation_id": "root", "metadata": {}},
        ],
    )
    sim = {
        "id": "sim",
        "task_id": "42",
        "trial": 0,
        "messages": [],
        "reward_info": {"reward": 1},
    }
    with Ledger(tmp_path, "project") as ledger:
        _export_selected(
            client, ledger, [sim], {}, {}, "hash", "batch", {}, {}, "old-trace"
        )
    assert client.created == 0
    assert list(client.scores) == ["old-score"]


def test_experiment_plan_requires_finalized_judgments_and_unique_cases(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "results.json").write_text(
        json.dumps(
            {
                "info": {
                    "environment_info": {
                        "domain_name": "airline",
                        "policy": "p",
                        "tool_defs": [],
                    }
                },
                "tasks": [{"id": "42"}],
                "simulations": [
                    {
                        "id": "sim",
                        "task_id": "42",
                        "trial": 0,
                        "seed": 1,
                        "messages": [],
                    }
                ],
            }
        )
    )
    (source / "metadata.toml").write_text("version = 1")
    judge = prepare(source)
    member = {"source": str(source), "judge": str(judge)}
    plan = {"name": "P1", "members": [member]}
    with pytest.raises(FileNotFoundError):
        prepare_plan(plan)
    save_result(
        judge,
        {
            "trial": 0,
            "simulation_id": "sim",
            "status": "evaluation_failed",
            "assessments": [],
            "attempts": [{"kind": "execution", "detail": "unavailable"}],
            "review": {"verified": False, "notes": "unavailable"},
        },
    )
    finalize(judge)
    identity, members = prepare_plan(plan)
    assert identity
    assert members[0]["judge_result"]["status"] == "evaluation_failed"
    assert members[0]["item"]["trial"] == 0
    with pytest.raises(ValueError, match="Duplicate"):
        prepare_plan({"name": "P1", "members": [member, member]})


class FakeSpan:
    id = "root"

    def __init__(self, trace_id):
        self.trace_id = trace_id

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_repeated_export_reuses_conversation_and_official_score(tmp_path, monkeypatch):
    monkeypatch.setattr("evals.langfuse_export.verify_delivery", lambda *args: None)
    client = FakeClient()
    sim = {
        "id": "sim",
        "task_id": "42",
        "trial": 0,
        "messages": [],
        "reward_info": {"reward": 1},
    }
    info = {
        "environment_info": {"domain_name": "airline", "policy": "p", "tool_defs": []}
    }
    for _ in range(2):
        with Ledger(tmp_path, "project") as ledger:
            _export_selected(
                client, ledger, [sim], info, {}, "hash", "batch", {}, {}, None
            )
    assert client.created == 1
    assert len(client.scores) == 1


def test_export_does_not_retry_trace_creation_after_delivery_failure(
    tmp_path, monkeypatch
):
    def fail(*args):
        raise ConnectionError("lost response")

    monkeypatch.setattr("evals.langfuse_export.verify_delivery", fail)
    client = FakeClient()
    sim = {"id": "sim", "task_id": "42", "trial": 0, "messages": []}
    info = {
        "environment_info": {"domain_name": "airline", "policy": "p", "tool_defs": []}
    }
    with Ledger(tmp_path, "project") as ledger, pytest.raises(ConnectionError):
        _export_selected(client, ledger, [sim], info, {}, "hash", "batch", {}, {}, None)
    with (
        Ledger(tmp_path, "project") as ledger,
        pytest.raises(ValueError, match="uncertain"),
    ):
        _export_selected(client, ledger, [sim], info, {}, "hash", "batch", {}, {}, None)
    assert client.created == 1
