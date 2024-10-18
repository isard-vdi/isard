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


import grpc
from isardvdi_common.api_exceptions import Error
from sessions.v1 import sessions_pb2

from api import app

## Session errors
no_session = Error("unauthorized", "No session provided")
expired_session = Error("unauthorized", "Session expired")
invalid_session = Error("internal_server", "Invalid session")
invalid_user = Error("unauthorized", "Invalid user")


def get(session_id, remote_addr):
    if not session_id:
        raise no_session

    try:
        return app.sessions_client.Get(
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
    try:
        return app.sessions_client.GetUserSession(
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
    try:
        try:
            session_id = get_user_session_id(user_id).id
        except Error as e:
            if e in [expired_session, invalid_user]:
                return
            raise e

        return app.sessions_client.Revoke(sessions_pb2.RevokeRequest(id=session_id))

    except grpc.RpcError as rpc_error:
        if rpc_error.code() in [
            grpc.StatusCode.NOT_FOUND,
        ]:
            pass

        raise invalid_session
