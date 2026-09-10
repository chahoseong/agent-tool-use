"""Errors with project-authored messages safe to display in the CLI."""


class EvaluationPreparationError(ValueError):
    """An evaluation cannot start; the message contains no external exception data."""
