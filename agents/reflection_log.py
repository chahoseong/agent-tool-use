"""Write per-output reflection events without retaining conversation state."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from tau2.data_model.message import AssistantMessage, UserMessage


def response_data(response: AssistantMessage | UserMessage) -> dict[str, Any]:
    """Retain output and supplied usage, excluding model connection settings."""
    return response.model_dump(
        mode="json",
        include={"role", "content", "tool_calls", "id", "usage", "cost"},
        exclude_none=True,
    )


class ReflectionLog:
    """Append and close each event; a missing directory disables recording.

    Each instance owns a unique file for one output. I/O errors propagate so
    a caller is not silently told that logging succeeded. This is not an fsync
    guarantee against power loss.
    """

    def __init__(
        self, directory: Path | None, *, context: dict[str, Any] | None = None
    ) -> None:
        self.path: Path | None = None
        self.context = dict(context or {})
        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True)
            while True:
                path = directory / f"{uuid4().hex}.jsonl"
                try:
                    with path.open("x", encoding="utf-8"):
                        pass
                except FileExistsError:
                    continue
                self.path = path
                break

    def write(self, stage: str, **data: Any) -> None:
        if self.path is None:
            return
        event = {
            "schema_version": 1,
            "output_id": self.path.stem,
            "recorded_at": datetime.now(UTC).isoformat(),
            "stage": stage,
            "context": self.context,
            **data,
        }
        line = json.dumps(event, ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as output:
            output.write(line + "\n")
