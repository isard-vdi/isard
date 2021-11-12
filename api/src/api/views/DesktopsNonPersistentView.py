# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
import os
import sys
import time
import traceback
from uuid import uuid4

from flask import request

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.apiv2_exc import *
from ..libv2.quotas import Quotas
from ..libv2.quotas_exc import *

quotas = Quotas()

from ..libv2.api_desktops_nonpersistent import ApiDesktopsNonPersistent

desktops = ApiDesktopsNonPersistent()

from .decorators import (
    allowedTemplateId,
    has_token,
    is_admin,
    ownsCategoryId,
    ownsDomainId,
    ownsUserId,
)


@app.route("/api/v3/desktop", methods=["POST"])
@has_token
def api_v3_desktop_new(payload):
    try:
        user_id = payload["user_id"]
        template_id = request.form.get("template", type=str)
    except Exception as e:
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "bad_request",
                    "msg": "Incorrect access. Exception: " + error,
                }
            ),
            400,
            {"Content-Type": "application/json"},
        )
    if user_id == None or template_id == None:
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {
                    "error": "bad_request",
                    "msg": "Incorrect access parameters. Check your query.",
                }
            ),
            400,
            {"Content-Type": "application/json"},
        )

    if not allowedTemplateId(payload, template_id):
        return (
            json.dumps({"error": "forbidden", "msg": "Forbidden template"}),
            403,
            {"Content-Type": "application/json"},
        )
    # Leave only one nonpersistent desktop from this template
    try:
        desktops.DeleteOthers(user_id, template_id)

    except DesktopNotFound:
        try:
            quotas.DesktopCreateAndStart(user_id)
        except QuotaUserNewDesktopExceeded:
            log.error("Quota for user " + user_id + " to create a desktop exceeded")
            return (
                json.dumps(
                    {
                        "error": "desktop_new_user_quota_exceeded",
                        "msg": "DesktopNew user desktop quota CREATE exceeded",
                    }
                ),
                507,
                {"Content-Type": "application/json"},
            )
        except QuotaGroupNewDesktopExceeded:
            log.error(
                "Quota for user "
                + user_id
                + " to create a desktop in his group limits is exceeded"
            )
            return (
                json.dumps(
                    {
                        "error": "desktop_new_group_quota_exceeded",
                        "msg": "DesktopNew group desktop limits CREATE exceeded",
                    }
                ),
                507,
                {"Content-Type": "application/json"},
            )
        except QuotaCategoryNewDesktopExceeded:
            log.error(
                "Quota for user "
                + user_id
                + " to create a desktop in his category limits is exceeded"
            )
            return (
                json.dumps(
                    {
                        "error": "desktop_new_category_quota_exceeded",
                        "msg": "DesktopNew category desktop limits CREATE exceeded",
                    }
                ),
                507,
                {"Content-Type": "application/json"},
            )

        except QuotaUserConcurrentExceeded:
            log.error("Quota for user " + user_id + " to start a desktop is exceeded")
            return (
                json.dumps(
                    {
                        "error": "desktop_start_user_quota_exceeded",
                        "msg": "DesktopNew user quota CONCURRENT exceeded",
                    }
                ),
                507,
                {"Content-Type": "application/json"},
            )
        except QuotaGroupConcurrentExceeded:
            log.error(
                "Quota for user "
                + user_id
                + " to start a desktop in his group is exceeded"
            )
            return (
                json.dumps(
                    {
                        "error": "desktop_start_group_quota_exceeded",
                        "msg": "DesktopNew user group limits CONCURRENT exceeded",
                    }
                ),
                507,
                {"Content-Type": "application/json"},
            )
        except QuotaCategoryConcurrentExceeded:
            log.error(
                "Quota for user "
                + user_id
                + " to start a desktop is his category exceeded"
            )
            return (
                json.dumps(
                    {
                        "error": "desktop_start_category_quota_exceeded",
                        "msg": "DesktopNew user category limits CONCURRENT exceeded",
                    }
                ),
                507,
                {"Content-Type": "application/json"},
            )

        except QuotaUserVcpuExceeded:
            log.error("Quota for user " + user_id + " to allocate vCPU is exceeded")
            return (
                json.dumps(
                    {
                        "error": "desktop_start_vcpu_quota_exceeded",
                        "msg": "DesktopNew user quota vCPU allocation exceeded",
                    }
                ),
                507,
                {"Content-Type": "application/json"},
            )
        except QuotaGroupVcpuExceeded:
            log.error(
                "Quota for user "
                + user_id
                + " to allocate vCPU in his group is exceeded"
            )
            return (
                json.dumps(
                    {
                        "error": "desktop_start_group_vcpu_quota_exceeded",
                        "msg": "DesktopNew user group limits vCPU allocation exceeded",
                    }
                ),
                507,
                {"Content-Type": "application/json"},
            )
        except QuotaCategoryVcpuExceeded:
            log.error(
                "Quota for user "
                + user_id
                + " to allocate vCPU in his category is exceeded"
            )
            return (
                json.dumps(
                    {
                        "error": "desktop_start_category_vcpu_quota_exceeded",
                        "msg": "DesktopNew user category limits vCPU allocation exceeded",
                    }
                ),
                507,
                {"Content-Type": "application/json"},
            )

        except QuotaUserMemoryExceeded:
            log.error("Quota for user " + user_id + " to allocate MEMORY is exceeded")
            return (
                json.dumps(
                    {
                        "error": "desktop_start_memory_quota_exceeded",
                        "msg": "DesktopNew user quota MEMORY allocation exceeded",
                    }
                ),
                507,
                {"Content-Type": "application/json"},
            )
        except QuotaGroupMemoryExceeded:
            log.error(
                "Quota for user "
                + user_id
                + " for creating another desktop is exceeded"
            )
            return (
                json.dumps(
                    {
                        "error": "desktop_start_group_memory_quota_exceeded",
                        "msg": "DesktopNew user group limits MEMORY allocation exceeded",
                    }
                ),
                507,
                {"Content-Type": "application/json"},
            )
        except QuotaCategoryMemoryExceeded:
            log.error(
                "Quota for user "
                + user_id
                + " category for desktop MEMORY allocation is exceeded"
            )
            return (
                json.dumps(
                    {
                        "error": "desktop_start_category_memory_quota_exceeded",
                        "msg": "DesktopNew user category limits MEMORY allocation exceeded",
                    }
                ),
                507,
                {"Content-Type": "application/json"},
            )

        except Exception as e:
            error = traceback.format_exc()
            return (
                json.dumps(
                    {
                        "error": "quota_general_exception",
                        "msg": "DesktopNew quota check general exception: " + error,
                    }
                ),
                500,
                {"Content-Type": "application/json"},
            )

    except DesktopNotStarted:
        try:
            quotas.DesktopStart(user_id)
        except QuotaUserConcurrentExceeded:
            log.error("Quota for user " + user_id + " to start a desktop is exceeded")
            return (
                json.dumps(
                    {
                        "error": "desktop_start_user_quota_exceeded",
                        "msg": "DesktopNew user quota CONCURRENT exceeded",
                    }
                ),
                507,
                {"Content-Type": "application/json"},
            )
        except QuotaGroupConcurrentExceeded:
            log.error(
                "Quota for user "
                + user_id
                + " to start a desktop in his group is exceeded"
            )
            return (
                json.dumps(
                    {
                        "error": "desktop_start_group_quota_exceeded",
                        "msg": "DesktopNew user group limits CONCURRENT exceeded",
                    }
                ),
                507,
                {"Content-Type": "application/json"},
            )
        except QuotaCategoryConcurrentExceeded:
            log.error(
                "Quota for user "
                + user_id
                + " to start a desktop is his category exceeded"
            )
            return (
                json.dumps(
                    {
                        "error": "desktop_start_category_quota_exceeded",
                        "msg": "DesktopNew user category limits CONCURRENT exceeded",
                    }
                ),
                507,
                {"Content-Type": "application/json"},
            )

        except QuotaUserVcpuExceeded:
            log.error("Quota for user " + user_id + " to allocate vCPU is exceeded")
            return (
                json.dumps(
                    {
                        "error": "desktop_start_vcpu_quota_exceeded",
                        "msg": "DesktopNew user quota vCPU allocation exceeded",
                    }
                ),
                507,
                {"Content-Type": "application/json"},
            )
        except QuotaGroupVcpuExceeded:
            log.error(
                "Quota for user "
                + user_id
                + " to allocate vCPU in his group is exceeded"
            )
            return (
                json.dumps(
                    {
                        "error": "desktop_start_group_vcpu_quota_exceeded",
                        "msg": "DesktopNew user group limits vCPU allocation exceeded",
                    }
                ),
                507,
                {"Content-Type": "application/json"},
            )
        except QuotaCategoryVcpuExceeded:
            log.error(
                "Quota for user "
                + user_id
                + " to allocate vCPU in his category is exceeded"
            )
            return (
                json.dumps(
                    {
                        "error": "desktop_start_category_vcpu_quota_exceeded",
                        "msg": "DesktopNew user category limits vCPU allocation exceeded",
                    }
                ),
                507,
                {"Content-Type": "application/json"},
            )

        except QuotaUserMemoryExceeded:
            log.error("Quota for user " + user_id + " to allocate MEMORY is exceeded")
            return (
                json.dumps(
                    {
                        "error": "desktop_start_memory_quota_exceeded",
                        "msg": "DesktopNew user quota MEMORY allocation exceeded",
                    }
                ),
                507,
                {"Content-Type": "application/json"},
            )
        except QuotaGroupMemoryExceeded:
            log.error(
                "Quota for user "
                + user_id
                + " for creating another desktop is exceeded"
            )
            return (
                json.dumps(
                    {
                        "error": "desktop_start_group_memory_quota_exceeded",
                        "msg": "DesktopNew user group limits MEMORY allocation exceeded",
                    }
                ),
                507,
                {"Content-Type": "application/json"},
            )
        except QuotaCategoryMemoryExceeded:
            log.error(
                "Quota for user "
                + user_id
                + " category for desktop MEMORY allocation is exceeded"
            )
            return (
                json.dumps(
                    {
                        "error": "desktop_start_category_memory_quota_exceeded",
                        "msg": "DesktopNew user category limits MEMORY allocation exceeded",
                    }
                ),
                507,
                {"Content-Type": "application/json"},
            )

        except Exception as e:
            error = traceback.format_exc()
            return (
                json.dumps(
                    {
                        "error": "quota_general_exception",
                        "msg": "DesktopNew quota check general exception: " + error,
                    }
                ),
                500,
                {"Content-Type": "application/json"},
            )

    except Exception as e:
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "DesktopNew previous checks general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )

    # So now we have checked if desktop exists and if we can create and/or start it

    try:
        desktop_id = desktops.New(user_id, template_id)
        return json.dumps({"id": desktop_id}), 200, {"Content-Type": "application/json"}
    except UserNotFound:
        log.error(
            "Desktop for user "
            + user_id
            + " from template "
            + template_id
            + ", user not found"
        )
        return (
            json.dumps(
                {
                    "error": "user_not_found",
                    "msg": "DesktopNew user not found",
                }
            ),
            404,
            {"Content-Type": "application/json"},
        )
    except TemplateNotFound:
        log.error(
            "Desktop for user "
            + user_id
            + " from template "
            + template_id
            + " template not found."
        )
        return (
            json.dumps(
                {
                    "error": "template_not_found",
                    "msg": "DesktopNew template not found",
                }
            ),
            404,
            {"Content-Type": "application/json"},
        )
    except DesktopNotCreated:
        log.error(
            "Desktop for user "
            + user_id
            + " from template "
            + template_id
            + " creation failed."
        )
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "DesktopNew not created",
                }
            ),
            404,
            {"Content-Type": "application/json"},
        )
    except DesktopActionTimeout:
        log.error(
            "Desktop for user "
            + user_id
            + " from template "
            + template_id
            + " start timeout."
        )
        return (
            json.dumps(
                {"error": "desktop_start_timeout", "msg": "DesktopNew start timeout"}
            ),
            504,
            {"Content-Type": "application/json"},
        )
    except DesktopActionFailed:
        log.error(
            "Desktop for user "
            + user_id
            + " from template "
            + template_id
            + " start failed."
        )
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "DesktopNew start failed",
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "DesktopNew general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/desktop/<desktop_id>", methods=["DELETE"])
@has_token
def api_v3_desktop_delete(payload, desktop_id=False):
    if desktop_id == False:
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {
                    "error": "bad_request",
                    "msg": "Incorrect access parameters. Check your query.",
                }
            ),
            400,
            {"Content-Type": "application/json"},
        )

    if not ownsDomainId(payload, desktop_id):
        return (
            json.dumps({"error": "forbidden", "msg": "Forbidden domain"}),
            403,
            {"Content-Type": "application/json"},
        )
    try:
        desktops.Delete(desktop_id)
        return json.dumps({}), 200, {"Content-Type": "application/json"}
    except DesktopNotFound:
        log.error("Desktop delete " + desktop_id + ", desktop not found")
        return (
            json.dumps(
                {"error": "desktop_not_found", "msg": "Desktop delete id not found"}
            ),
            404,
            {"Content-Type": "application/json"},
        )
    except DesktopDeleteFailed:
        log.error("Desktop delete " + desktop_id + ", desktop delete failed")
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "Desktop delete, deleting failed",
                }
            ),
            404,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "DesktopDelete general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )
