# Copyright 2024 the Isard-vdi project authors
# License: AGPLv3

"""
Libvirt timeout infrastructure for detecting slow/overloaded hypervisors.

This module provides timeout wrappers for libvirt operations to detect
hypervisors that are too slow to respond. When a hypervisor is overloaded,
libvirt calls can hang indefinitely, blocking the worker thread.

Key components:
- LibvirtTimeoutError: Exception raised when a libvirt operation times out
- LibvirtOperationStats: Track latency statistics per hypervisor
- execute_with_timeout(): ThreadPoolExecutor-based timeout wrapper

Hardcoded thresholds (edit and restart engine to change):
- LIBVIRT_OPERATION_TIMEOUT: Max seconds before timeout error (30s)
- LIBVIRT_OPERATION_WARNING: Log warning if exceeded (10s)
- DEGRADED_TIMEOUT_THRESHOLD: Timeouts to trigger degradation (2)
- SLOW_DETECTION_WINDOW: Slow responses to trigger degradation (5)
- RECOVERY_WINDOW: Normal responses to trigger recovery (10)
- DEGRADED_RECOVERY_SECONDS: Min time before recovery check (300s)
"""

import atexit
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, Optional

from engine.services.log import logs

# =============================================================================
# Hardcoded Configuration Constants
# To change these values, edit this file and restart the engine.
# =============================================================================

# Maximum time (seconds) to wait for a libvirt operation before raising timeout
LIBVIRT_OPERATION_TIMEOUT = 30

# Log a warning if operation takes longer than this (seconds)
LIBVIRT_OPERATION_WARNING = 10

# Number of timeouts within the window to trigger degradation
DEGRADED_TIMEOUT_THRESHOLD = 2

# Number of slow responses (>WARNING threshold) to trigger degradation
SLOW_DETECTION_WINDOW = 5

# Number of consecutive normal responses needed to recover from degraded state
RECOVERY_WINDOW = 10

# Minimum time (seconds) in degraded state before attempting recovery
DEGRADED_RECOVERY_SECONDS = 300

# Time (seconds) after which counters start decaying if no issues occur
COUNTER_DECAY_SECONDS = 300


class LibvirtTimeoutError(Exception):
    """Exception raised when a libvirt operation times out.

    Attributes:
        operation: Name of the operation that timed out (e.g., "createXML")
        timeout: The timeout value in seconds
        hyp_id: The hypervisor ID where the timeout occurred
    """

    def __init__(self, operation: str, timeout: float, hyp_id: str):
        self.operation = operation
        self.timeout = timeout
        self.hyp_id = hyp_id
        super().__init__(
            f"Libvirt operation '{operation}' timed out after {timeout}s on hypervisor {hyp_id}"
        )


@dataclass
class LibvirtOperationStats:
    """Track latency statistics for libvirt operations per hypervisor.

    Maintains a sliding window of recent operation times to detect
    slow hypervisors and track recovery.
    """

    hyp_id: str
    # Recent response times (milliseconds) - sliding window
    recent_times_ms: deque = field(default_factory=lambda: deque(maxlen=20))
    # Count of slow responses in current detection window
    slow_response_count: int = 0
    # Count of timeout errors in current detection window
    timeout_count: int = 0
    # Count of consecutive normal responses (for recovery)
    normal_response_count: int = 0
    # Timestamp of last slow response or timeout (for counter decay)
    last_issue_time: Optional[float] = None
    # Lock for thread-safe updates
    _lock: Lock = field(default_factory=Lock)

    def record_response(self, duration_ms: float, is_timeout: bool = False):
        """Record a response time and update counters.

        Args:
            duration_ms: Operation duration in milliseconds
            is_timeout: True if the operation timed out
        """
        with self._lock:
            self.recent_times_ms.append(duration_ms)

            # Apply counter decay: if no issues for COUNTER_DECAY_SECONDS, reset counters
            self._apply_counter_decay()

            if is_timeout:
                self.timeout_count += 1
                self.normal_response_count = 0
                self.last_issue_time = time.time()
                logs.workers.warning(
                    f"[{self.hyp_id}] Libvirt timeout recorded "
                    f"(count: {self.timeout_count}/{DEGRADED_TIMEOUT_THRESHOLD})"
                )
            elif duration_ms > LIBVIRT_OPERATION_WARNING * 1000:
                self.slow_response_count += 1
                self.normal_response_count = 0
                self.last_issue_time = time.time()
                logs.workers.warning(
                    f"[{self.hyp_id}] Slow libvirt response: {duration_ms:.0f}ms "
                    f"(count: {self.slow_response_count}/{SLOW_DETECTION_WINDOW})"
                )
            else:
                self.normal_response_count += 1
                logs.workers.debug(
                    f"[{self.hyp_id}] Normal libvirt response: {duration_ms:.0f}ms "
                    f"(normal count: {self.normal_response_count}/{RECOVERY_WINDOW})"
                )

    def _apply_counter_decay(self):
        """Decay counters if no issues have occurred for a while.

        Called with lock held. Resets slow_response_count and timeout_count
        if COUNTER_DECAY_SECONDS have passed since the last issue.
        """
        if self.last_issue_time is None:
            return

        time_since_issue = time.time() - self.last_issue_time
        if time_since_issue >= COUNTER_DECAY_SECONDS:
            if self.slow_response_count > 0 or self.timeout_count > 0:
                logs.workers.info(
                    f"[{self.hyp_id}] Decaying counters after {time_since_issue:.0f}s "
                    f"of normal operation (slow: {self.slow_response_count}, "
                    f"timeout: {self.timeout_count})"
                )
                self.slow_response_count = 0
                self.timeout_count = 0
                self.last_issue_time = None

    def should_degrade(self) -> bool:
        """Check if hypervisor should be marked as degraded.

        Returns:
            True if timeout or slow response thresholds exceeded
        """
        with self._lock:
            return (
                self.timeout_count >= DEGRADED_TIMEOUT_THRESHOLD
                or self.slow_response_count >= SLOW_DETECTION_WINDOW
            )

    def should_recover(self, degraded_since: Optional[float]) -> bool:
        """Check if hypervisor should recover from degraded state.

        Args:
            degraded_since: Timestamp when degradation started

        Returns:
            True if recovery conditions are met
        """
        with self._lock:
            # Must have been degraded for minimum recovery time
            if degraded_since is None:
                return False

            time_degraded = time.time() - degraded_since
            if time_degraded < DEGRADED_RECOVERY_SECONDS:
                return False

            # Must have enough consecutive normal responses
            return self.normal_response_count >= RECOVERY_WINDOW

    def get_average_ms(self) -> float:
        """Get average response time in milliseconds.

        Returns:
            Average response time, or 0 if no samples
        """
        with self._lock:
            if not self.recent_times_ms:
                return 0.0
            return sum(self.recent_times_ms) / len(self.recent_times_ms)

    def reset(self):
        """Reset all counters (e.g., after recovery)."""
        with self._lock:
            self.slow_response_count = 0
            self.timeout_count = 0
            self.normal_response_count = 0
            self.recent_times_ms.clear()
            self.last_issue_time = None


# Thread pool for executing libvirt operations with timeout
# Using a single worker to avoid overwhelming slow hypervisors
_timeout_executor = ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="libvirt_timeout"
)


def _shutdown_timeout_executor():
    """Shutdown the timeout executor gracefully."""
    try:
        _timeout_executor.shutdown(wait=False)
    except Exception:
        pass  # Ignore errors during shutdown


# Register shutdown handler for graceful cleanup
atexit.register(_shutdown_timeout_executor)


def execute_with_timeout(
    func: Callable[..., Any],
    args: tuple = (),
    kwargs: dict = None,
    timeout: float = LIBVIRT_OPERATION_TIMEOUT,
    operation_name: str = "unknown",
    hyp_id: str = "unknown",
) -> Any:
    """Execute a function with a timeout.

    Uses ThreadPoolExecutor to run the function in a separate thread
    and waits for the result with a timeout.

    Note: This does NOT kill the underlying libvirt call if it times out.
    The call will continue running in the background. The purpose is to
    detect slow hypervisors and mark them as degraded, not to abort calls.

    Args:
        func: Function to execute
        args: Positional arguments for func
        kwargs: Keyword arguments for func
        timeout: Maximum time to wait (seconds)
        operation_name: Name of operation for logging/errors
        hyp_id: Hypervisor ID for logging/errors

    Returns:
        The result of func(*args, **kwargs)

    Raises:
        LibvirtTimeoutError: If the operation times out
        Exception: Any exception raised by func
    """
    if kwargs is None:
        kwargs = {}

    future = _timeout_executor.submit(func, *args, **kwargs)

    try:
        result = future.result(timeout=timeout)
        return result
    except FuturesTimeoutError:
        # Don't cancel - let the operation complete in background
        # We just want to detect the timeout
        raise LibvirtTimeoutError(operation_name, timeout, hyp_id)
