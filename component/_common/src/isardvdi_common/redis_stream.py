# Copyright 2025 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import json
import logging
import os
import socket
import time

import redis
from isardvdi_common.connections.redis_urls import changefeed_url

log = logging.getLogger("engine")

STREAM_BLOCK_MS = 5000
STREAM_MAXLEN = 10000


class RedisStreamConsumer:
    """Synchronous Redis Stream consumer with consumer groups.

    Provides guaranteed delivery by reading via XREADGROUP and
    acknowledging each message after successful processing. On startup,
    any pending (unacknowledged) messages are re-delivered first.
    """

    def __init__(self, streams, group, consumer=None):
        """
        Args:
            streams: list of stream keys, e.g. ["stream:domains", "stream:engine"]
            group: consumer group name, e.g. "engine-domains"
            consumer: unique consumer name (defaults to hostname-pid)
        """
        self.streams = streams
        self.group = group
        self.consumer = consumer or f"{socket.gethostname()}-{os.getpid()}"
        self._redis = None

    def _connect(self):
        if self._redis is None:
            self._redis = redis.from_url(changefeed_url(), decode_responses=True)
        return self._redis

    def _ensure_groups(self):
        r = self._connect()
        for stream in self.streams:
            try:
                r.xgroup_create(stream, self.group, id="0", mkstream=True)
                log.info(f"Created consumer group '{self.group}' on '{stream}'")
            except redis.ResponseError as e:
                if "BUSYGROUP" in str(e):
                    pass  # Group already exists
                else:
                    raise

    def _process_pending(self, handler):
        """Process any pending (unacknowledged) messages from previous runs."""
        r = self._connect()
        for stream in self.streams:
            while True:
                pending = r.xreadgroup(
                    self.group,
                    self.consumer,
                    {stream: "0"},
                    count=100,
                    block=None,
                )
                if not pending:
                    break
                for stream_name, messages in pending:
                    if not messages:
                        break
                    for msg_id, fields in messages:
                        try:
                            data = json.loads(fields["data"])
                            handler(data)
                        except Exception:
                            log.exception(
                                f"Error processing pending message {msg_id} from {stream_name}"
                            )
                        r.xack(stream_name, self.group, msg_id)
                else:
                    continue
                break

    def run(self, handler, stop_event=None):
        """Block and consume messages, calling handler(data) for each.

        Args:
            handler: callable(dict) — receives {"table": ..., "change": {"old_val": ..., "new_val": ...}}
            stop_event: optional threading.Event to signal shutdown
        """
        backoff = 1
        while True:
            try:
                self._ensure_groups()
                log.info(
                    f"Processing pending messages for group '{self.group}' on {self.streams}"
                )
                self._process_pending(handler)
                log.info(
                    f"Listening on streams {self.streams} as group '{self.group}' consumer '{self.consumer}'"
                )
                backoff = 1
                r = self._connect()

                while not (stop_event and stop_event.is_set()):
                    results = r.xreadgroup(
                        self.group,
                        self.consumer,
                        {s: ">" for s in self.streams},
                        count=10,
                        block=STREAM_BLOCK_MS,
                    )
                    if not results:
                        continue
                    for stream_name, messages in results:
                        for msg_id, fields in messages:
                            try:
                                data = json.loads(fields["data"])
                                handler(data)
                            except Exception:
                                log.exception(
                                    f"Error processing message {msg_id} from {stream_name}"
                                )
                            r.xack(stream_name, self.group, msg_id)

            except (redis.ConnectionError, redis.TimeoutError, OSError) as e:
                log.warning(
                    f"Redis connection error: {e}. Reconnecting in {backoff}s..."
                )
                self._redis = None
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)
            except Exception:
                log.exception("Unexpected error in stream consumer")
                self._redis = None
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)

            if stop_event and stop_event.is_set():
                log.info(f"Stream consumer '{self.group}' shutting down")
                return
