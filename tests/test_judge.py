import json

import pytest

from evals.judge import finalize, prepare, save_result


def source(tmp_path):
    data = {
        "info": {
            "environment_info": {
                "domain_name": "airline",
                "policy": "policy",
                "tool_defs": [],
            }
        },
        "tasks": [
            {
                "id": "42",
                "user_scenario": "goal",
                "evaluation_criteria": {"secret": True},
            }
        ],
        "simulations": [
            {
                "id": "sim",
                "task_id": "42",
                "trial": 0,
                "seed": 1,
                "reward_info": {"reward": 0},
                "messages": [
                    {"role": "user", "content": "hello", "raw_data": "secret"}
                ],
            }
        ],
    }
    (tmp_path / "results.json").write_text(json.dumps(data))
    (tmp_path / "metadata.toml").write_text("version = 1")
    return tmp_path


def test_prepare_excludes_scores_and_private_metadata_from_judge_input(tmp_path):
    run = prepare(source(tmp_path))
    payload = json.loads((run / "inputs/trial_0.json").read_text())
    assert payload["messages"] == [{"role": "user", "content": "hello"}]
    assert "evaluation_criteria" not in payload["task"]
    assert "reward_info" not in payload
    assert payload["policy"] == "policy"


def test_prepare_preserves_previous_judgment_runs(tmp_path):
    root = source(tmp_path)
    first = prepare(root)
    original = (first / "manifest.json").read_bytes()
    second = prepare(root)
    assert first != second
    assert (first / "manifest.json").read_bytes() == original


def test_save_result_rejects_incomplete_completed_assessment(tmp_path):
    run = prepare(source(tmp_path))
    with pytest.raises(ValueError):
        save_result(
            run,
            {
                "trial": 0,
                "simulation_id": "sim",
                "status": "completed",
                "assessments": [],
                "attempts": [],
                "review": {"verified": True, "notes": "checked"},
            },
        )
    assert not (run / "trial_0.json").exists()


def test_save_result_preserves_failed_evaluation_without_inventing_verdicts(tmp_path):
    run = prepare(source(tmp_path))
    result = {
        "trial": 0,
        "simulation_id": "sim",
        "status": "evaluation_failed",
        "assessments": [],
        "attempts": [{"kind": "execution", "detail": "unavailable"}],
        "review": {"verified": False, "notes": "judge unavailable"},
    }
    save_result(run, result)
    assert json.loads((run / "trial_0.json").read_text())["assessments"] == []
    with pytest.raises(FileExistsError):
        save_result(run, result)


def test_prepare_rejects_duplicate_trial_numbers_before_creating_run(tmp_path):
    root = source(tmp_path)
    path = root / "results.json"
    data = json.loads(path.read_text())
    data["simulations"].append({**data["simulations"][0], "id": "another"})
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        prepare(root)
    assert not (root / "llm-judge").exists()


def completed(run):
    payload = json.loads((run / "inputs/trial_0.json").read_text())
    return {
        "trial": 0,
        "simulation_id": "sim",
        "status": "completed",
        "assessments": [
            {
                "criterion_id": c["id"],
                "verdict": "unknown",
                "reason": "Insufficient conversation",
                "evidence": [
                    {"message_index": 0, "field": "content", "excerpt": "hello"}
                ],
                "evidence_limit": "Only greeting available",
            }
            for c in payload["criteria"]
        ],
        "attempts": [{"kind": "execution", "detail": "initial response"}],
        "review": {"verified": True, "notes": "Checked against source"},
    }


def test_judgment_completion_preserves_embedded_evidence(tmp_path):
    run = prepare(source(tmp_path))
    save_result(run, completed(run))
    finalize(run)
    assert json.loads((run / "completion.json").read_text())["status"] == "completed"
    saved = json.loads((run / "trial_0.json").read_text())
    assert saved["assessments"][0]["evidence"][0]["excerpt"] == "hello"


@pytest.mark.parametrize(
    "problem", ["fabricated_excerpt", "changed_source", "excessive_retries"]
)
def test_save_result_rejects_unverifiable_judgments(tmp_path, problem):
    root = source(tmp_path)
    run = prepare(root)
    result = completed(run)
    if problem == "fabricated_excerpt":
        result["assessments"][0]["evidence"][0]["excerpt"] = "I consent"
    elif problem == "changed_source":
        (root / "metadata.toml").write_text("version = 2")
    else:
        result["attempts"] *= 4
    with pytest.raises(ValueError):
        save_result(run, result)
    assert not (run / "trial_0.json").exists()
