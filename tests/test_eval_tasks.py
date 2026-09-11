"""Verify task lookup against the official mock domain."""

import pytest
from tau2.data_model.tasks import Description, Task
from tau2.domains.mock.environment import get_tasks as get_mock_tasks
from tau2.runner.helpers import load_tasks

from evals import tasks as tasks_module


@pytest.mark.parametrize("domain", ["mock", "retail"])
def test_task_listing_returns_all_official_tasks_from_domain(domain: str) -> None:
    expected_tasks = load_tasks(domain, None)

    tasks = tasks_module.list_tasks(domain)

    assert tasks == expected_tasks


def test_task_lookup_returns_official_task_with_requested_id() -> None:
    expected_task = get_mock_tasks()[-1]

    task = tasks_module.get_task("mock", expected_task.id)

    assert task == expected_task


def test_task_lookup_raises_value_error_when_id_is_unknown() -> None:
    task_ids = {task.id for task in get_mock_tasks()}
    unknown_id = "unknown_task"
    while unknown_id in task_ids:
        unknown_id += "_"

    with pytest.raises(ValueError) as error:
        tasks_module.get_task("mock", unknown_id)

    assert str(error.value) == f"Unknown mock task ID: {unknown_id}."


def test_task_selection_accepts_existing_mock_task_ids() -> None:
    task_ids = [task.id for task in get_mock_tasks()]

    tasks_module.validate_task_ids("mock", task_ids)


def test_task_listing_reports_domain_when_official_loading_fails() -> None:
    domain = "unknown-domain"

    with pytest.raises(ValueError) as error:
        tasks_module.list_tasks(domain)

    assert str(error.value) == f"Cannot read {domain} tasks."


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
        tasks_module.validate_task_ids("mock", selected_ids)

    assert str(error.value) == f"Unknown mock task IDs: {', '.join(unknown_ids)}."


@pytest.mark.parametrize(
    "missing_description",
    [
        None,
        Description.model_validate({"notes": "Additional context without a purpose."}),
    ],
    ids=["no_description", "no_purpose"],
)
def test_task_list_display_formats_ids_and_descriptions_in_input_order(
    missing_description: Description | None,
) -> None:
    tasks = [
        Task.model_validate(
            {
                "id": "task_z",
                "description": {"purpose": "Create a task."},
                "user_scenario": {"instructions": "Create a task for a meeting."},
            }
        ),
        Task.model_validate(
            {
                "id": "task_a",
                "description": missing_description,
                "user_scenario": {"instructions": "Complete an existing task."},
            }
        ),
    ]

    text = tasks_module.format_task_list(tasks)

    assert text == "task_z: Create a task.\ntask_a: 설명 없음"


def test_task_detail_display_includes_scenario_initial_state_and_evaluation_criteria() -> (
    None
):
    task = Task.model_validate(
        {
            "id": "task_detail",
            "description": {
                "purpose": "Create a meeting task.",
                "notes": "Basic case.",
            },
            "user_scenario": {
                "persona": "A team member.",
                "instructions": "Create a task for tomorrow's meeting.",
            },
            "initial_state": {
                "initialization_data": {"agent_data": {"tasks": {}}},
                "message_history": [
                    {
                        "role": "user",
                        "content": "Help me plan a meeting.",
                        "timestamp": "2026-09-10T00:00:00Z",
                    }
                ],
            },
            "evaluation_criteria": {
                "reward_basis": ["DB"],
                "actions": [
                    {
                        "action_id": "create_meeting",
                        "name": "create_task",
                        "arguments": {"title": "Meeting", "user_id": "user_1"},
                    }
                ],
                "nl_assertions": ["The agent confirms creation."],
            },
        }
    )

    text = tasks_module.format_task_detail(task)

    assert (
        text
        == """ID: task_detail

설명:
{
  "purpose": "Create a meeting task.",
  "notes": "Basic case."
}

사용자 시나리오:
{
  "persona": "A team member.",
  "instructions": "Create a task for tomorrow's meeting."
}

초기 상태:
{
  "initialization_data": {
    "agent_data": {
      "tasks": {}
    }
  },
  "message_history": [
    {
      "role": "user",
      "content": "Help me plan a meeting.",
      "is_audio": false,
      "timestamp": "2026-09-10T00:00:00Z",
      "is_final_chunk": true,
      "contains_speech": true
    }
  ]
}

평가 기준:
{
  "actions": [
    {
      "action_id": "create_meeting",
      "requestor": "assistant",
      "name": "create_task",
      "arguments": {
        "title": "Meeting",
        "user_id": "user_1"
      }
    }
  ],
  "nl_assertions": [
    "The agent confirms creation."
  ],
  "reward_basis": [
    "DB"
  ]
}"""
    )


@pytest.mark.parametrize(
    "optional_sections",
    [{}, {"description": {}, "initial_state": {}}],
    ids=["omitted", "empty_objects"],
)
def test_task_detail_display_marks_missing_sections_without_optional_fields(
    optional_sections: dict[str, object],
) -> None:
    task = Task.model_validate(
        {
            "id": "minimal_task",
            "user_scenario": {"instructions": "Create a task."},
            **optional_sections,
        }
    )

    text = tasks_module.format_task_detail(task)

    assert text == (
        "ID: minimal_task\n\n"
        "설명:\n지정되지 않음\n\n"
        '사용자 시나리오:\n{\n  "instructions": "Create a task."\n}\n\n'
        "초기 상태:\n지정되지 않음\n\n"
        "평가 기준:\n지정되지 않음"
    )


def test_task_detail_display_preserves_default_reward_basis() -> None:
    task = Task.model_validate(
        {
            "id": "default_criteria",
            "user_scenario": {"instructions": "Create a task."},
            "evaluation_criteria": {},
        }
    )

    text = tasks_module.format_task_detail(task)

    assert text.endswith(
        '평가 기준:\n{\n  "reward_basis": [\n    "DB",\n    "COMMUNICATE"\n  ]\n}'
    )
