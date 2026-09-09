"""Task lookup for official mock evaluations."""

from tau2.data_model.tasks import Task
from tau2.runner.helpers import load_tasks


def list_tasks() -> list[Task]:
    """Return all official mock tasks without filtering or transformation."""
    return load_tasks("mock")


def get_task(task_id: str) -> Task:
    """Return the matching official mock task, or raise ValueError if absent."""
    for task in list_tasks():
        if task.id == task_id:
            return task
    raise ValueError(f"Unknown mock task ID: {task_id}.")


def validate_task_ids(task_ids: list[str]) -> None:
    """Raise ValueError listing any IDs absent from the official mock tasks."""
    existing_ids = {task.id for task in list_tasks()}
    unknown_ids = [task_id for task_id in task_ids if task_id not in existing_ids]
    if unknown_ids:
        raise ValueError(f"Unknown mock task IDs: {', '.join(unknown_ids)}.")
