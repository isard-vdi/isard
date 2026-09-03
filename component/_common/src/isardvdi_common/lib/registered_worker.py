"""RQ worker that repairs its own discovery registration from the heartbeat."""

import time
from typing import Optional

from redis.client import Pipeline
from rq import Worker, worker_registration

# Bounds the invisibility well under the 600 s maintenance sweep that makes it
# permanent, without adding a round trip to every 3 s heartbeat.
REGISTRATION_CHECK_INTERVAL = 30


class SelfRegisteringWorkerMixin:
    """Must precede ``Worker`` in the MRO so this ``heartbeat`` wraps RQ's."""

    def heartbeat(
        self, timeout: Optional[int] = None, pipeline: Optional[Pipeline] = None
    ) -> None:
        super().heartbeat(timeout, pipeline)
        self._ensure_registered()

    def _ensure_registered(self) -> None:
        """Re-join the discovery sets if we have fallen out of them."""
        try:
            # Not set in __init__: subclasses and tests skip Worker.__init__.
            elapsed_since = time.monotonic() - getattr(
                self, "_last_registration_check", float("-inf")
            )
            if elapsed_since < REGISTRATION_CHECK_INTERVAL:
                return
            self._last_registration_check = time.monotonic()

            if self.connection.sismember(self.redis_workers_keys, self.key):
                return

            self.log.warning(
                "Worker %s: absent from %s, re-registering",
                self.name,
                self.redis_workers_keys,
            )
            with self.connection.pipeline() as pipeline:
                # Not register_birth(): it DELETEs the key and raises when the key
                # exists without a death field, which is the state being repaired.
                pipeline.hset(self.key, mapping=self.serialize())
                # serialize() omits state (rq 2.10.0); RQ writes it via set_state.
                pipeline.hset(self.key, "state", self.get_state())
                worker_registration.register(self, pipeline)
                pipeline.expire(self.key, self.worker_ttl + 60)
                pipeline.execute()
        except Exception:
            # heartbeat() runs on the dequeue hot path: never propagate.
            self.log.warning(
                "Worker %s: registration check failed, retrying next window",
                getattr(self, "name", "?"),
                exc_info=True,
            )


class RegisteredWorker(SelfRegisteringWorkerMixin, Worker):
    """Stock RQ ``Worker`` that heals its own registration."""
