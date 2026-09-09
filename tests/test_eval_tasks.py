"""Verify task lookup against the official mock domain."""

import pytest
from tau2.domains.mock.environment import get_tasks as get_mock_tasks

from evals import tasks as tasks_module


def test_task_listing_returns_all_official_mock_tasks() -> None:
    expected_tasks = get_mock_tasks()

    tasks = tasks_module.list_tasks()

    assert tasks == expected_tasks


def test_task_lookup_returns_official_task_with_requested_id() -> None:
    expected_task = get_mock_tasks()[-1]

    task = tasks_module.get_task(expected_task.id)

    assert task == expected_task


def test_task_lookup_raises_value_error_when_id_is_unknown() -> None:
    task_ids = {task.id for task in get_mock_tasks()}
    unknown_id = "unknown_task"
    while unknown_id in task_ids:
        unknown_id += "_"

    with pytest.raises(ValueError) as error:
        tasks_module.get_task(unknown_id)

    assert str(error.value) == f"Unknown mock task ID: {unknown_id}."


def test_task_selection_accepts_existing_mock_task_ids() -> None:
    task_ids = [task.id for task in get_mock_tasks()]

    tasks_module.validate_task_ids(task_ids)


def test_task_selection_reports_all_unknown_ids() -> None:
    tasks = get_mock_tasks()
    existing_ids = {task.id for task in tasks}
    unknown_ids = []
    for candidate in ("unknown_task_a", "unknown_task_b"):
        while candidate in existing_ids:
            candidate += "_"
        unknown_ids.append(candidate)
    selected_ids = [unknown_ids[0], tasks[0].id, unknown_ids[1]]

    with pytest.raises(ValueError) as error:
        tasks_module.validate_task_ids(selected_ids)

    assert str(error.value) == f"Unknown mock task IDs: {', '.join(unknown_ids)}."
