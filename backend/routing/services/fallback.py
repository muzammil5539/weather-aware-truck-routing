"""Try a sequence of interchangeable providers until one answers.

Only transport-level failures are worth retrying elsewhere. A rate limit, a
timeout or a server fault means *this* provider cannot answer right now, so the
next one gets a turn. A 4xx answer like "no route exists" or "no such place" is
a real answer: every provider would say the same thing, and falling through
would just be slower.
"""
from __future__ import annotations

import logging
from typing import Callable, Iterable, TypeVar

from routing.exceptions import UpstreamError

logger = logging.getLogger(__name__)

T = TypeVar("T")


def is_transient(exc: UpstreamError) -> bool:
    return exc.status_code == 429 or exc.status_code >= 500


def first_success(attempts: Iterable[tuple[str, Callable[[], T]]], label: str) -> T:
    """Call each attempt in order; return the first that succeeds."""
    failures: list[str] = []
    for name, call in attempts:
        try:
            result = call()
            if failures:
                logger.info("%s: %s answered after %d failure(s)", label, name, len(failures))
            return result
        except UpstreamError as exc:
            if not is_transient(exc):
                raise
            logger.warning("%s: %s unavailable (%s)", label, name, exc.detail)
            failures.append(f"{name} ({exc.detail})")

    raise UpstreamError(
        label,
        "Every provider is unavailable right now. Tried " + "; ".join(failures) + ".",
        status_code=503,
    )
