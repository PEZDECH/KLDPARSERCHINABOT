"""
Retry utilities using Tenacity.
"""

from typing import Any, Callable, TypeVar

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import settings
from utils.logger import logger

T = TypeVar("T")


def retry_with_backoff(
    exceptions: tuple[type[Exception], ...] = (Exception,),
    max_retries: int = None,
    min_wait: int = 1,
    max_wait: int = 10,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for retrying functions with exponential backoff.

    Args:
        exceptions: Tuple of exception types to retry on
        max_retries: Maximum number of retry attempts
        min_wait: Minimum wait time between retries (seconds)
        max_wait: Maximum wait time between retries (seconds)

    Returns:
        Decorated function with retry logic
    """
    if max_retries is None:
        max_retries = settings.max_retries

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @retry(
            retry=retry_if_exception_type(exceptions),
            stop=stop_after_attempt(max_retries),
            wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
            before_sleep=lambda retry_state: logger.warning(
                f"Retrying {func.__name__} after error: {retry_state.outcome.exception()}. "
                f"Attempt {retry_state.attempt_number}/{max_retries}"
            ),
            reraise=True,
        )
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            return await func(*args, **kwargs)

        @retry(
            retry=retry_if_exception_type(exceptions),
            stop=stop_after_attempt(max_retries),
            wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
            before_sleep=lambda retry_state: logger.warning(
                f"Retrying {func.__name__} after error: {retry_state.outcome.exception()}. "
                f"Attempt {retry_state.attempt_number}/{max_retries}"
            ),
            reraise=True,
        )
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            return func(*args, **kwargs)

        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
