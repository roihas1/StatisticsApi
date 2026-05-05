"""Retry transient network failures when calling stats.nba.com (nba_api uses requests)."""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY_SEC = 1.0


def _is_transient_nba_http_error(exc: BaseException) -> bool:
    if isinstance(
        exc,
        (
            BrokenPipeError,
            ConnectionResetError,
            TimeoutError,
        ),
    ):
        return True

    try:
        from urllib3.exceptions import ProtocolError, ReadTimeoutError

        if isinstance(exc, (ReadTimeoutError, ProtocolError)):
            return True
    except ImportError:
        pass

    try:
        from requests.exceptions import ChunkedEncodingError, ConnectionError, Timeout
    except ImportError:
        return False

    return isinstance(exc, (Timeout, ConnectionError, ChunkedEncodingError))


def run_with_nba_retries(
    fn: Callable[[], T],
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay_sec: float = DEFAULT_BASE_DELAY_SEC,
    context: str = "",
) -> T:
    """
    Run `fn`; on transient connection/read timeouts retry with exponential backoff.
    Re-raises the last exception when out of attempts or when the error is not retryable.
    """
    last: BaseException | None = None
    label = f" ({context})" if context else ""
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last = exc
            transient = _is_transient_nba_http_error(exc)
            if attempt >= max_attempts or not transient:
                raise
            delay = base_delay_sec * (2 ** (attempt - 1))
            logger.warning(
                "NBA HTTP attempt %s/%s%s failed: %s; retrying in %.1fs",
                attempt,
                max_attempts,
                label,
                exc,
                delay,
            )
            time.sleep(delay)
    assert last is not None
    raise last
