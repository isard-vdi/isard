# Copyright 2025 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import json
import logging
import os
import socket
import time

import redis
from isardvdi_common.connections.redis_blocking import STREAM_BLOCK_MS, blocking_client
from isardvdi_common.connections.redis_urls import changefeed_url

log = logging.getLogger("engine")

STREAM_MAXLEN = 10000

# How much of a rejected message to put in the log. Enough to identify the row
# and the kind of change, short enough not to dump a whole document per failure.
PAYLOAD_LOG_CHARS = 500


def _payload_summary(fields):
    """The message body, trimmed, for the log line of a dropped message.

    A dropped change is only diagnosable if the log says WHICH one it was, so
    this never raises: a summary that fails to build must not replace the
    handler's traceback with its own.
    """
    try:
        raw = fields.get("data", "")
        return raw[:PAYLOAD_LOG_CHARS] + ("..." if len(raw) > PAYLOAD_LOG_CHARS else "")
    except Exception:
        return "<unavailable>"


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
            self._redis = blocking_client(
                changefeed_url(), block_ms=STREAM_BLOCK_MS, decode_responses=True
            )
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
                                "Dropping pending message %s from %s (group %s): "
                                "the handler failed and the change is lost. Payload: %s",
                                msg_id,
                                stream_name,
                                self.group,
                                _payload_summary(fields),
                            )
                        finally:
                            # Acked either way on purpose: a message the handler
                            # cannot process would be redelivered forever and
                            # wedge the consumer. The log above makes it visible.
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
                    try:
                        results = r.xreadgroup(
                            self.group,
                            self.consumer,
                            {s: ">" for s in self.streams},
                            count=10,
                            block=STREAM_BLOCK_MS,
                        )
                    except redis.TimeoutError:
                        # The server may have delivered before the deadline, and
                        # `>` never returns a delivered entry again.
                        log.warning(
                            f"Read of {self.streams} exceeded its socket deadline "
                            f"with a {STREAM_BLOCK_MS}ms block; replaying pending"
                        )
                        self._process_pending(handler)
                        continue
                    if not results:
                        continue
                    for stream_name, messages in results:
                        for msg_id, fields in messages:
                            try:
                                data = json.loads(fields["data"])
                                handler(data)
                            except Exception:
                                log.exception(
                                    "Dropping message %s from %s (group %s): the "
                                    "handler failed and the change is lost. Payload: %s",
                                    msg_id,
                                    stream_name,
                                    self.group,
                                    _payload_summary(fields),
                                )
                            finally:
                                # As in _process_pending: acking a rejected
                                # message keeps the consumer moving, but never
                                # silently.
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
