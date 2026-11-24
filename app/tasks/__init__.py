"""Taskiq broker and task definitions."""

# `recurring` is imported for its side effect of registering
# @broker.task-decorated functions -- an unimported task module is a
# silent no-op, not an error, so every task module must be imported here.
from app.tasks import (
    exchange_rates,  # noqa: F401
    imports,  # noqa: F401
    recurring,  # noqa: F401
    statement_parsing,  # noqa: F401
)
from app.tasks.broker import broker, scheduler

__all__ = ["broker", "scheduler"]
