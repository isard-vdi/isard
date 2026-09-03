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

# A consumer name carries the pid, so a restarted process registers a new one
# and whatever the dead one held is claimable by nobody but a group-wide sweep.
RECLAIM_IDLE_MS = 60000
RECLAIM_EVERY_S = 30
RECLAIM_COUNT = 100
MAX_DELIVERIES = 5
DEAD_STREAM_MAXLEN = 10000
DEAD_CONSUMER_IDLE_MS = 12 * 60 * 60 * 1000


def dead_stream(stream):
    """Where an entry goes when it has been delivered too many times."""
    return f"{stream}:dead"


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
                        self._deliver(stream_name, msg_id, fields, handler)
                else:
                    continue
                break

    def _deliver(self, stream_name, msg_id, fields, handler):
        """Run the handler for one entry and ACK it, whatever it does.

        Acked either way on purpose: a message the handler cannot process would
        be redelivered forever and wedge the consumer. The log makes it visible.
        """
        r = self._connect()
        try:
            handler(json.loads(fields["data"]))
        except Exception:
            log.exception(
                "Dropping message %s from %s (group %s): the handler failed "
                "and the change is lost. Payload: %s",
                msg_id,
                stream_name,
                self.group,
                _payload_summary(fields),
            )
        finally:
            r.xack(stream_name, self.group, msg_id)

    def _reclaim_pending(self, handler):
        """Re-deliver entries a dead consumer of this group left un-ACKed.

        ``_process_pending`` reads ``{stream: "0"}``, which is only ever this
        consumer's own list, so a process killed between delivery and ACK
        orphans its entries under a consumer name no live process will ever use
        again. ``XAUTOCLAIM`` is group-wide and is the only thing that reaches
        them.
        """
        r = self._connect()
        for stream in self.streams:
            try:
                response = r.xautoclaim(
                    stream,
                    self.group,
                    self.consumer,
                    min_idle_time=RECLAIM_IDLE_MS,
                    count=RECLAIM_COUNT,
                )
            except Exception:
                log.exception("Reclaim of %s (group %s) failed", stream, self.group)
                continue
            entries = response[1] if len(response) >= 2 else []
            for msg_id, fields in entries:
                if not fields:
                    r.xack(stream, self.group, msg_id)
                    continue
                if self._delivery_count(stream, msg_id) > MAX_DELIVERIES:
                    self._dead_letter(stream, msg_id, fields)
                    continue
                self._deliver(stream, msg_id, fields, handler)

    def _delivery_count(self, stream, msg_id):
        """How many times redis has delivered this PEL entry. 0 if unreadable."""
        try:
            pending = self._connect().xpending_range(
                stream, self.group, min=msg_id, max=msg_id, count=1
            )
            if pending:
                return int(pending[0]["times_delivered"])
        except Exception:
            log.exception("Could not read the delivery count of %s", msg_id)
        return 0

    def _dead_letter(self, stream, msg_id, fields):
        """Park an entry that has survived too many deliveries, and ACK it.

        One that keeps being reclaimed is killing whatever picks it up, so it
        must stop being handed out; the copy is kept so the loss is inspectable.
        """
        r = self._connect()
        try:
            r.xadd(
                dead_stream(stream),
                fields,
                maxlen=DEAD_STREAM_MAXLEN,
                approximate=True,
            )
        except Exception:
            log.exception("Dead-letter of %s from %s failed", msg_id, stream)
            return
        r.xack(stream, self.group, msg_id)
        log.warning(
            "Dead-lettered %s from %s (group %s) after more than %s deliveries. "
            "Payload: %s",
            msg_id,
            stream,
            self.group,
            MAX_DELIVERIES,
            _payload_summary(fields),
        )

    def _reap_dead_consumers(self):
        """Drop the consumers left behind by previous processes.

        Only ones with nothing pending: one still holding entries belongs to
        the reclaim pass, and deleting it would drop its list rather than
        replay it.
        """
        r = self._connect()
        for stream in self.streams:
            try:
                for consumer in r.xinfo_consumers(stream, self.group):
                    name = consumer.get("name")
                    if not name or name == self.consumer:
                        continue
                    if int(consumer.get("pending") or 0) > 0:
                        continue
                    if int(consumer.get("idle") or 0) < DEAD_CONSUMER_IDLE_MS:
                        continue
                    r.xgroup_delconsumer(stream, self.group, name)
                    log.info("Reaped dead consumer '%s' from %s", name, stream)
            except Exception:
                log.warning("Could not reap dead consumers on %s", stream)

    def run(self, handler, stop_event=None):
        """Block and consume messages, calling handler(data) for each.

        Args:
            handler: callable(dict) — receives {"table": ..., "change": {"old_val": ..., "new_val": ...}}
            stop_event: optional threading.Event to signal shutdown
        """
        backoff = 1
        # Outside the reconnect loop: reconnecting more often than
        # RECLAIM_EVERY_S would otherwise mean never reclaiming at all.
        last_reclaim = time.monotonic()
        while True:
            try:
                self._ensure_groups()
                log.info(
                    f"Processing pending messages for group '{self.group}' on {self.streams}"
                )
                self._process_pending(handler)
                self._reclaim_pending(handler)
                self._reap_dead_consumers()
                last_reclaim = time.monotonic()
                log.info(
                    f"Listening on streams {self.streams} as group '{self.group}' consumer '{self.consumer}'"
                )
                backoff = 1
                r = self._connect()

                while not (stop_event and stop_event.is_set()):
                    if time.monotonic() - last_reclaim >= RECLAIM_EVERY_S:
                        self._reclaim_pending(handler)
                        self._reap_dead_consumers()
                        last_reclaim = time.monotonic()
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
                            self._deliver(stream_name, msg_id, fields, handler)

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
