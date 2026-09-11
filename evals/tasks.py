"""Task lookup for official evaluation domains."""

from tau2.data_model.tasks import Task
from tau2.runner.helpers import load_tasks

from evals.errors import EvaluationPreparationError


def list_domains() -> list[str]:
    """Return registered official evaluation domains."""
    from tau2.registry import registry

    return registry.get_domains()


def list_tasks(domain: str) -> list[Task]:
    """Return all official tasks for the selected domain."""
    try:
        return load_tasks(domain, None)
    except (KeyError, OSError, ValueError):
        raise EvaluationPreparationError(f"Cannot read {domain} tasks.") from None


def get_task(
    domain: str,
    task_id: str,
) -> Task:
    """Return the requested task from the selected official domain."""
    for task in list_tasks(domain):
        if task.id == task_id:
            return task
    raise EvaluationPreparationError(f"Unknown {domain} task ID: {task_id}.")


def validate_task_ids(
    domain: str,
    task_ids: list[str],
) -> None:
    """Reject IDs absent from the selected official domain."""
    existing_ids = {task.id for task in list_tasks(domain)}
    unknown_ids = [task_id for task_id in task_ids if task_id not in existing_ids]
    if unknown_ids:
        raise EvaluationPreparationError(
            f"Unknown {domain} task IDs: {', '.join(unknown_ids)}."
        )


def format_task_list(tasks: list[Task]) -> str:
    """Format task IDs and purposes in the supplied order."""
    lines = []
    for task in tasks:
        purpose = task.description.purpose if task.description is not None else None
        lines.append(f"{task.id}: {purpose or '설명 없음'}")
    return "\n".join(lines)


def format_task_detail(task: Task) -> str:
    """Format official task details, retaining headings for absent sections."""
    sections = [f"ID: {task.id}"]
    for heading, value in (
        ("설명", task.description),
        ("사용자 시나리오", task.user_scenario),
        ("초기 상태", task.initial_state),
        ("평가 기준", task.evaluation_criteria),
    ):
        content = (
            value.model_dump_json(indent=2, exclude_none=True)
            if value is not None and value.model_dump(exclude_none=True)
            else "지정되지 않음"
        )
        sections.append(f"{heading}:\n{content}")
    return "\n\n".join(sections)
