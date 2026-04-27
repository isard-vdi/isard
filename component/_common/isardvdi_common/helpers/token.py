#
#   Copyright © 2023 Josep Maria Viñolas Auquer
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

import logging as log
import os

import jwt
from isardvdi_common.helpers.api_logs_users import LogsUsers
from isardvdi_common.helpers.error_factory import Error
from rethinkdb import r


class Token:
    @classmethod
    def get_header_jwt_payload(cls):
        return cls.get_token_payload(cls.get_token_auth_header())

    @classmethod
    def get_auto_register_jwt_payload(cls):
        return cls.get_token_payload(cls.get_token_header("Register-Claims"))

    @classmethod
    def get_token_auth_header(cls):
        return cls.get_token_header("Authorization")

    @staticmethod
    def get_expired_user_data(token):
        try:
            claims = jwt.decode(token, options={"verify_signature": False})
        except Exception:
            return None
        try:
            if claims.get("kid") == "isardvdi":
                return claims.get("data")
            elif claims.get("kid") == "isardvdi-viewer" and claims.get("data").get(
                "desktop_id"
            ):
                return claims.get("data")
            else:
                # Not a system secret
                return None
        except Exception as e:
            log.debug(e)
        return None

    @classmethod
    def log_user(cls, payload):
        try:
            LogsUsers(payload)
        except Exception as e:
            log.warning("Unable to update user logs")

    @classmethod
    def get_token_payload(cls, token):
        payload = cls.get_jwt_payload(token)
        if payload.get("data", False):
            cls.log_user(payload)
            return payload["data"]
        return payload

    @classmethod
    def get_jwt_payload(cls, token=None):
        if not token:
            token = cls.get_token_auth_header()
        try:
            claims = jwt.decode(token, options={"verify_signature": False})
        except Exception:
            raise Error(
                "unauthorized",
                "Bad token format",
            )
        try:
            if claims.get("kid") == "isardvdi":
                secret = os.environ.get("API_ISARDVDI_SECRET")
            elif claims.get("kid") == "isardvdi-viewer":
                secret = os.environ.get("API_ISARDVDI_SECRET")
                if not claims.get("data").get("desktop_id"):
                    raise Error(
                        "unauthorized",
                        "Not authorized viewer token",
                    )
            elif claims.get("kid") == "isardvdi-hypervisors":
                secret = os.environ.get("API_HYPERVISORS_SECRET")
            else:
                # Not a system secret
                raise Error(
                    "unauthorized",
                    "Bad token Key ID",
                )
        except Exception:
            raise Error(
                "unauthorized",
                "Unable to parse authentication token",
            )

        try:
            # Allow 60s of clock skew between service callers (e.g. remote
            # backupninja hosts) and the API server. Service tokens are only
            # valid for 120s, so leeway can never extend validity beyond a few
            # minutes.
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                options=dict(verify_aud=False, verify_sub=False, verify_exp=True),
                leeway=60,
            )
        except jwt.ExpiredSignatureError:
            raise Error(
                "unauthorized",
                "Token expired",
                description_code="token_expired",
                data=cls.get_expired_user_data(token),
            )
        except (jwt.InvalidAudienceError, jwt.InvalidIssuerError):
            raise Error(
                "unauthorized",
                "Incorrect claims, please check the audience and issuer",
            )
        except jwt.InvalidTokenError:
            raise Error(
                "unauthorized",
                "Error when decoding token",
            )
        except Exception:
            raise Error(
                "unauthorized",
                "Unable to parse authentication token",
            )
        return payload

    @classmethod
    def get_user_migration_payload(cls, token):
        payload = cls.get_jwt_payload(token)

        if payload.get("type", "") != "user-migration":
            raise Error(
                "forbidden",
                "Token is not a migration token",
                description_code="token_invalid",
            )

        return payload

    @classmethod
    def get_unverified_external_jwt_payload(cls):
        token = cls.get_token_auth_header()
        try:
            claims = jwt.decode(token, options={"verify_signature": False})
            if (
                not claims.get("kid")
                or not claims.get("category_id")
                or not claims.get("role_id") == "manager"
                or not claims.get("type") == "external"
                or not claims.get("domain")
            ):
                raise Error(
                    "unauthorized",
                    "Unable to parse authentication token",
                )
        except Exception:
            raise Error(
                "unauthorized",
                "Bad token format",
            )
        return {
            "token": token,
            "kid": claims.get("kid"),
            "category_id": claims.get("category_id"),
            "role_id": claims.get("role_id"),
            "domain": claims.get("domain"),
        }

    @classmethod
    def verify_external_jwt(cls, token, secret):
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                options=dict(verify_aud=False, verify_sub=False, verify_exp=True),
                leeway=60,
            )
        except jwt.ExpiredSignatureError:
            raise Error(
                "unauthorized",
                "Token expired",
                description_code="token_expired",
                data=cls.get_expired_user_data(token),
            )
        except (jwt.InvalidAudienceError, jwt.InvalidIssuerError):
            raise Error(
                "unauthorized",
                "Incorrect claims, please check the audience and issuer",
            )
        except jwt.InvalidTokenError:
            raise Error(
                "unauthorized",
                "Error when decoding token",
            )
        except Exception:
            raise Error(
                "unauthorized",
                "Unable to parse authentication token",
            )
        return payload
