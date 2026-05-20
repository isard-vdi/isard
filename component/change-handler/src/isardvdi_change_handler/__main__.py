#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Miriam Melina Gamboa Valdez
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import json
import logging as log
import traceback
from os import environ

import redis.asyncio as aioredis
from changefeed_subscribers import TABLE_TO_SUBSCRIBER
from isardvdi_common.connections.redis_urls import changefeed_url, socketio_url
from socketio import AsyncRedisManager

from .handlers.base import BaseHandler
from .handlers.bookings import BookingsHandler
from .handlers.categories import CategoriesHandler
from .handlers.deployments import DeploymentsHandler
from .handlers.domains import DomainsHandler
from .handlers.groups import GroupsHandler
from .handlers.hypervisors import HypervisorsHandler
from .handlers.media import MediaHandler
from .handlers.recycle_bin import RecycleBinHandler
from .handlers.resource_planner import ResourcePlannerHandler
from .handlers.resources import ResourcesHandler
from .handlers.targets import TargetsHandler
from .handlers.users import UsersHandler
from .handlers.vgpus import VgpusHandler
from .streams import task_results_consumer

redis_manager = AsyncRedisManager(socketio_url(), write_only=True)


async def dispatch_message(data: dict, handler_map: dict, logger: log.Logger) -> None:
    """Resolve the subscriber for ``data["table"]``, deserialise the
    typed envelope, and forward ``envelope.change`` to the matching
    handler. Logs and swallows every error so a single bad payload
    cannot kill the listen loop. Extracted from ``listen_to_redis``
    so the dispatch contract can be unit-tested without Redis.
    """
    table = data.get("table")
    subscriber = TABLE_TO_SUBSCRIBER.get(table)
    if subscriber is None:
        logger.warning(f"No subscriber registered for table: {table}; skipping")
        return
    try:
        envelope = subscriber.parse_dict(data)
    except Exception as e:
        logger.error(f"Failed to deserialize {table} envelope: {e}; data={data!r}")
        return

    change = envelope.change
    logger.info(f"[{table}] Received change: {change}")

    handler = handler_map.get(table)
    if not handler:
        logger.warning(f"No handler registered for table: {table}")
        return

    try:
        await handler.handle(change)
    except Exception as e:
        logger.error(traceback.format_exc())
        logger.error(f"Handler for {table} failed: {e}")


# Handler map: Redis-pubsub channel -> handler that emits SocketIO events.
#
# Many entries below (graphics, videos, interfaces, qos_net, qos_disk,
# remotevpn, boots, scheduler_jobs, hypervisors, vgpus, user_storage,
# users_migrations, targets, resource_planner, bookings) only emit to the
# `/administrators` namespace and are consumed by the Flask webapp admin
# for its datatable live-refresh. Vue 3 does not yet subscribe to those
# events; keep them wired so the admin UI stays reactive and so Vue 3 has
# the stream ready when it ports the matching admin views.
handler_map = {
    "deployments": DeploymentsHandler(redis_manager, "deployments"),
    "media": MediaHandler(redis_manager, "media"),
    "recycle_bin": RecycleBinHandler(redis_manager, "recycle_bin"),
    "targets": TargetsHandler(redis_manager, "targets"),
    "resource_planner": ResourcePlannerHandler(redis_manager, "plannings"),
    "bookings": BookingsHandler(redis_manager, "bookings"),
    "domains": DomainsHandler(redis_manager, "domains"),
    "graphics": ResourcesHandler(redis_manager, "graphics"),
    "videos": ResourcesHandler(redis_manager, "videos"),
    "interfaces": ResourcesHandler(redis_manager, "interfaces"),
    "qos_net": ResourcesHandler(redis_manager, "qos_net"),
    "qos_disk": ResourcesHandler(redis_manager, "qos_disk"),
    "remotevpn": ResourcesHandler(redis_manager, "remotevpn"),
    "boots": ResourcesHandler(redis_manager, "boots"),
    "users": UsersHandler(redis_manager, "users"),
    "categories": CategoriesHandler(redis_manager, "categories"),
    "groups": GroupsHandler(redis_manager, "groups"),
    "scheduler_jobs": BaseHandler(redis_manager, "scheduler_jobs"),
    "hypervisors": HypervisorsHandler(redis_manager, "hypervisors"),
    "vgpus": VgpusHandler(redis_manager, "vgpus"),
    "user_storage": BaseHandler(redis_manager, "user_storage"),
    "users_migrations": BaseHandler(redis_manager, "users_migrations"),
}


def _configure_logging():
    """Configure root logging for the change-handler process.

    Called once from :func:`main` before any coroutine starts so both
    the pub/sub listener and the new task-results stream consumer
    share the same format and level.
    """
    logging_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    if environ.get("DEBUG_WEBSOCKETS", "") == "true":
        log.warning("Running in development mode, setting log level to DEBUG.")
        log.basicConfig(
            level=log.DEBUG,
            format=logging_format,
            handlers=[log.StreamHandler()],  # Ensures output goes to stdout
            force=True,  # Override any existing logging configuration
        )
        log.debug("Debug mode enabled, logging at DEBUG level.")
    else:
        log.warning("Running in production mode, setting log level to INFO.")
        log.basicConfig(
            level=log.INFO,
            format=logging_format,
            handlers=[log.StreamHandler()],  # Ensures output goes to stdout
            force=True,  # Override any existing logging configuration
        )


async def listen_to_redis():
    # Create a logger instance
    logger = log.getLogger(__name__)

    while True:
        redis = None
        pubsub = None
        try:
            redis = aioredis.from_url(changefeed_url(), decode_responses=True)
            await redis.ping()
            logger.warning(
                "Connected to Redis successfully."
            )  # Use logger instead of log

            pubsub = redis.pubsub(ignore_subscribe_messages=True)
            await pubsub.subscribe(*handler_map.keys())

            logger.info(f"Subscribed to {handler_map.keys()} channels in Redis.")

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                try:
                    data = json.loads(message["data"])
                except Exception as e:
                    logger.error(f"Failed to parse Redis message: {e}")
                    continue

                await dispatch_message(data, handler_map, logger)
        except Exception as e:
            logger.warning(f"Redis connection error: {e}")
        finally:
            if pubsub:
                try:
                    await pubsub.unsubscribe()
                    await pubsub.close()
                except Exception:
                    pass
            if redis:
                try:
                    await redis.aclose()
                except Exception:
                    pass

            logger.warning("Reconnecting to Redis in 5 seconds...")
            await asyncio.sleep(5)


async def main():
    """Run the changefeed pub/sub listener and the
    ``stream:task-results`` consumer concurrently.

    The task-results consumer is the canonical emitter of the ``task``
    SocketIO event and the canonical executor of the chain-handler
    bodies that used to live on core_worker. It is started
    unconditionally — the dark-mode flag introduced in MR-1 was
    retired in MR-3 once core_worker was deleted.
    """
    _configure_logging()
    await asyncio.gather(
        listen_to_redis(),
        task_results_consumer.run(redis_manager),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Shutting down change-handler.")
