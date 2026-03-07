"""
Retry decorator with exponential backoff and jitter.

Usage:
    @retry(max_attempts=5, base_delay=1.0, retryable=(aiohttp.ClientError,))
    async def my_func():
        ...
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
from typing import Callable, Sequence, Type

logger = logging.getLogger(__name__)

# Errors that should NEVER be retried (e.g. bad auth, bad request).
NON_RETRYABLE_HTTP_CODES: frozenset[int] = frozenset({400, 401, 403, 404, 422})


def retry(
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: float = 0.3,
    retryable: Sequence[Type[BaseException]] = (Exception,),
) -> Callable:
    """
    Async retry decorator with exponential backoff + jitter.

    Args:
        max_attempts: Total attempts (1 = no retry).
        base_delay:   Initial wait in seconds.
        max_delay:    Cap on wait time in seconds.
        jitter:       Fraction of delay added as random noise (0–1).
        retryable:    Exception types that trigger a retry.
                      All others propagate immediately.
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            last_exc: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await fn(*args, **kwargs)
                except tuple(retryable) as exc:  # type: ignore[misc]
                    last_exc = exc
                    if attempt == max_attempts:
                        break
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    delay += random.uniform(0, jitter * delay)
                    logger.warning(
                        "[retry] %s failed (attempt %d/%d): %s — retrying in %.2fs",
                        fn.__name__, attempt, max_attempts, exc, delay,
                    )
                    await asyncio.sleep(delay)
                except BaseException:
                    raise  # non-retryable — propagate immediately

            logger.error(
                "[retry] %s exhausted %d attempts. Last error: %s",
                fn.__name__, max_attempts, last_exc,
            )
            raise last_exc  # type: ignore[misc]

        return wrapper
    return decorator
