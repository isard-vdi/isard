#
#   Copyright © 2024 Pau Abril
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Sessions service operations (gRPC backend).

This module defines the *interface* — ``get`` / ``get_user_session_id`` /
``revoke_user_session`` — used by every code path that needs to consult the
sessions service. The concrete gRPC stub is wired up at service startup
via ``configure_sessions_client(provider)``.

Why dependency injection: this module lives in ``isardvdi_common`` and is
imported transitively by every service in the monorepo (apiv4, engine,
change-handler, webapp, notifier, scheduler) through the shared user /
auth helpers. Only apiv4 actually calls these functions at runtime;
the others import them but never reach the network. Before this
refactor the module created a sessions gRPC channel at *module load
time*, so every service paid the cost of opening a TCP channel to
``isard-sessions`` whether it would use it or not — and apiv4
additionally tripped a SIGSEGV in gevent's libev corecext because the
factory module unconditionally called ``grpc.experimental.gevent.init_gevent()``
without the required ``monkey.patch_all()`` precondition (see
``apiv4.connections.grpc_client`` for the full incident analysis).

Splitting the interface from the backend keeps gRPC concerns out of
the import path of services that don't need them, and removes the
all-services blast radius of a misconfigured gRPC poller.
"""

from typing import Callable, Optional

from isardvdi_common.helpers.error_factory import Error

# Public error sentinels — defined at module scope so ``except Error as e:
# if e is expired_session: ...`` continues to work in callers (e.g.
# ``lib.users.users.user.UsersProcessed.user_config``).
no_session = Error("unauthorized", "No session provided")
expired_session = Error("unauthorized", "Session expired")
invalid_session = Error("internal_server", "Invalid session")
invalid_user = Error("unauthorized", "Invalid user")


# Provider hook. apiv4's lifespan startup registers a callable that
# returns a long-lived sessions gRPC stub (one channel per worker).
# Other services never register and never call any of the functions
# below, so the unconfigured state is invisible to them.
_sessions_client_provider: Optional[Callable[[], object]] = None


def configure_sessions_client(provider: Callable[[], object]) -> None:
    """Register a factory returning the sessions gRPC stub.

    Call once at service startup, before any request is served. The
    provider is invoked each time a session operation runs, so callers
    typically memoize a single stub in the closure (see apiv4's
    lifespan setup) rather than rebuilding the channel on every call.
    """
    global _sessions_client_provider
    _sessions_client_provider = provider


def _client():
    if _sessions_client_provider is None:
        raise RuntimeError(
            "sessions client not configured: call "
            "isardvdi_common.connections.api_sessions.configure_sessions_client(provider) "
            "during service startup before invoking session operations."
        )
    return _sessions_client_provider()


def get(session_id, remote_addr):
    # Lazy imports — keep grpc/protobuf out of the module's import path
    # so non-grpc services (engine, change-handler, …) don't pay the
    # cost. apiv4 imports grpc transitively elsewhere, so this is free
    # for the only caller that actually executes this code.
    import grpc
    from isardvdi_protobuf.sessions.v1 import sessions_pb2

    if not session_id:
        raise no_session

    try:
        return _client().Get(
            sessions_pb2.GetRequest(id=session_id, remote_addr=remote_addr)
        )

    except grpc.RpcError as rpc_error:
        if rpc_error.code() in [
            grpc.StatusCode.NOT_FOUND,
            grpc.StatusCode.UNAUTHENTICATED,
        ]:
            raise expired_session

        raise invalid_session


def get_user_session_id(user_id):
    import grpc
    from isardvdi_protobuf.sessions.v1 import sessions_pb2

    try:
        return _client().GetUserSession(
            sessions_pb2.GetUserSessionRequest(user_id=user_id)
        )

    except grpc.RpcError as rpc_error:
        if rpc_error.code() in [
            grpc.StatusCode.NOT_FOUND,
        ]:
            raise expired_session
        elif rpc_error.code() in [
            grpc.StatusCode.INVALID_ARGUMENT,
        ]:
            raise invalid_user

        raise invalid_session


def revoke_user_session(user_id):
    import grpc
    from isardvdi_protobuf.sessions.v1 import sessions_pb2

    try:
        try:
            session_id = get_user_session_id(user_id).id
        except Error as e:
            if e in [expired_session, invalid_user]:
                return
            raise e

        return _client().Revoke(sessions_pb2.RevokeRequest(id=session_id))

    except grpc.RpcError as rpc_error:
        if rpc_error.code() in [
            grpc.StatusCode.NOT_FOUND,
        ]:
            pass

        raise invalid_session
