"""Shared plumbing for running async command callbacks under click."""

import asyncio
import functools
from collections.abc import Callable, Coroutine
from typing import Any


def run_async[**P, R](func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, R]:
    """
    Adapt an async command callback to click's synchronous calling convention.

    Opens a fresh event loop per invocation (``asyncio.run``) -- CLI
    commands are one-shot processes, not a long-lived server like the API,
    so there's no existing loop to reuse.

    :param func: the async callback a ``@click.command()`` wraps.
    :return: a sync callable click can invoke directly.
    """

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return asyncio.run(func(*args, **kwargs))

    return wrapper
