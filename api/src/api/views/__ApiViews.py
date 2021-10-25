# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
import os
import sys
import time
from uuid import uuid4

from flask import request

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.apiv2_exc import *
from ..libv2.quotas import Quotas
from ..libv2.quotas_exc import *

quotas = Quotas()


@app.route("/api/v3/category/<id>", methods=["GET"])
def api_v3_category(id):
    try:
        data = app.lib.CategoryGet(id)
        return json.dumps(data), 200, {"Content-Type": "application/json"}
    except CategoryNotFound:
        return (
            json.dumps(
                {"code": 1, "msg": "Category " + id + " not exists in database"}
            ),
            404,
            {"Content-Type": "application/json"},
        )

    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
        return (
            json.dumps({"code": 9, "msg": "Register general exception: " + str(e)}),
            500,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/register", methods=["POST"])
def api_v3_register():
    try:
        code = request.form.get("code", type=str)
    except Exception as e:
        return (
            json.dumps({"code": 8, "msg": "Incorrect access. exception: " + str(e)}),
            401,
            {"Content-Type": "application/json"},
        )

    try:
        data = app.lib.CodeSearch(code)
        return json.dumps(data), 200, {"Content-Type": "application/json"}
    except CodeNotFound:
        log.error("Code not in database.")
        return (
            json.dumps({"code": 1, "msg": "Code " + code + " not exists in database"}),
            404,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
        return (
            json.dumps({"code": 9, "msg": "Register general exception: " + str(e)}),
            401,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/user/<id>", methods=["GET"])
def api_v3_user_exists(id=False):
    if id == False:
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {"code": 8, "msg": "Incorrect access parameters. Check your query."}
            ),
            401,
            {"Content-Type": "application/json"},
        )

    try:
        app.lib.UserExists(id)
        return json.dumps({}), 200, {"Content-Type": "application/json"}
    except UserNotFound:
        log.error("User " + id + " not in database.")
        return (
            json.dumps({"code": 1, "msg": "User not exists in database"}),
            404,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
        return (
            json.dumps({"code": 9, "msg": "UserExists general exception: " + str(e)}),
            401,
            {"Content-Type": "application/json"},
        )


# Update user name
@app.route("/api/v3/user/<id>", methods=["PUT"])
def api_v3_user_update(id=False):
    if id == False:
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {"code": 8, "msg": "Incorrect access parameters. Check your query."}
            ),
            401,
            {"Content-Type": "application/json"},
        )

    try:
        name = request.form.get("name", type=str)
        email = request.form.get("email", type=str)
        photo = request.form.get("photo", type=str)
    except Exception as e:
        return (
            json.dumps({"code": 8, "msg": "Incorrect access. exception: " + str(e)}),
            401,
            {"Content-Type": "application/json"},
        )

    if photo == None:
        photo = ""

    if name == None or email == None:
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {"code": 8, "msg": "Incorrect access parameters. Check your query."}
            ),
            401,
            {"Content-Type": "application/json"},
        )
    try:
        app.lib.UserUpdate(id, name, email, photo)
        return json.dumps({}), 200, {"Content-Type": "application/json"}
    except UpdateFailed:
        log.error("User " + id + " update failed.")
        return (
            json.dumps({"code": 1, "msg": "User update failed"}),
            404,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
        return (
            json.dumps({"code": 9, "msg": "UserUpdate general exception: " + str(e)}),
            401,
            {"Content-Type": "application/json"},
        )


# Add user
@app.route("/api/v3/user", methods=["POST"])
def api_v3_user_insert():
    try:
        provider = request.form.get("provider", type=str)
        user_uid = request.form.get("user_uid", type=str)
        user_username = request.form.get("user_username", type=str)
        role_id = request.form.get("role", type=str)
        category_id = request.form.get("category", type=str)
        group_id = request.form.get("group", type=str)
        password = request.form.get("password", type=str)
    except Exception as e:
        return (
            json.dumps({"code": 8, "msg": "Incorrect access. exception: " + str(e)}),
            401,
            {"Content-Type": "application/json"},
        )
    if (
        user_username == None
        or role_id == None
        or category_id == None
        or group_id == None
    ):
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {"code": 8, "msg": "Incorrect access parameters. Check your query."}
            ),
            401,
            {"Content-Type": "application/json"},
        )
    if password == None:
        password = False

    try:
        quotas.UserCreate(category_id, group_id)
    except QuotaCategoryNewUserExceeded:
        log.error(
            "Quota for creating another user in category "
            + category_id
            + " is exceeded"
        )
        return (
            json.dumps(
                {"code": 11, "msg": "UserNew category quota for adding user exceeded"}
            ),
            507,
            {"Content-Type": "application/json"},
        )
    except QuotaGroupNewUserExceeded:
        log.error(
            "Quota for creating another user in group " + group_id + " is exceeded"
        )
        return (
            json.dumps(
                {"code": 11, "msg": "UserNew group quota for adding user exceeded"}
            ),
            507,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
        return (
            json.dumps(
                {"code": 9, "msg": "UserNew quota check general exception: " + str(e)}
            ),
            401,
            {"Content-Type": "application/json"},
        )

    try:
        user_id = app.lib.UserCreate(
            user_uid, user_username, provider, role_id, category_id, group_id, password
        )
        return json.dumps({"id": user_id}), 200, {"Content-Type": "application/json"}
    except UserExists:
        log.error("User " + user_username + " already exists.")
        return (
            json.dumps({"code": 1, "msg": "User already exists"}),
            404,
            {"Content-Type": "application/json"},
        )
    except RoleNotFound:
        log.error("Role " + role_username + " not found.")
        return (
            json.dumps({"code": 2, "msg": "Role not found"}),
            404,
            {"Content-Type": "application/json"},
        )
    except CategoryNotFound:
        log.error("Category " + category_id + " not found.")
        return (
            json.dumps({"code": 3, "msg": "Category not found"}),
            404,
            {"Content-Type": "application/json"},
        )
    except GroupNotFound:
        log.error("Group " + group_id + " not found.")
        return (
            json.dumps({"code": 4, "msg": "Group not found"}),
            404,
            {"Content-Type": "application/json"},
        )
    except NewUserNotInserted:
        log.error("User " + user_username + " could not be inserted into database.")
        return (
            json.dumps(
                {
                    "code": 5,
                    "msg": "User could not be inserted into database. Already exists!",
                }
            ),
            404,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
        return (
            json.dumps({"code": 9, "msg": "UserUpdate general exception: " + str(e)}),
            401,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/user/<user_id>", methods=["DELETE"])
def api_v3_user_delete(user_id):
    try:
        app.lib.UserDelete(user_id)
        return json.dumps({}), 200, {"Content-Type": "application/json"}
    except UserNotFound:
        log.error("User delete " + user_id + ", user not found")
        return (
            json.dumps({"code": 1, "msg": "User delete id not found"}),
            404,
            {"Content-Type": "application/json"},
        )
    except UserDeleteFailed:
        log.error("User delete " + user_id + ", user delete failed")
        return (
            json.dumps({"code": 2, "msg": "User delete failed"}),
            404,
            {"Content-Type": "application/json"},
        )
    except DesktopDeleteFailed:
        log.error("User delete for user " + user_id + ", desktop delete failed")
        return (
            json.dumps({"code": 5, "msg": "User delete, desktop deleting failed"}),
            404,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
        return (
            json.dumps({"code": 9, "msg": "UserDelete general exception: " + str(e)}),
            401,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/user/<id>/templates", methods=["GET"])
def api_v3_user_templates(id=False):
    if id == False:
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {"code": 8, "msg": "Incorrect access parameters. Check your query."}
            ),
            401,
            {"Content-Type": "application/json"},
        )

    try:
        templates = app.lib.UserTemplates(id)
        dropdown_templates = [
            {
                "id": t["id"],
                "name": t["name"],
                "icon": t["icon"],
                "description": t["description"],
            }
            for t in templates
        ]
        return json.dumps(dropdown_templates), 200, {"Content-Type": "application/json"}
    except UserNotFound:
        log.error("User " + id + " not in database.")
        return (
            json.dumps(
                {"code": 1, "msg": "UserTemplates: User not exists in database"}
            ),
            404,
            {"Content-Type": "application/json"},
        )
    except UserTemplatesError:
        log.error("Template list for user " + id + " failed.")
        return (
            json.dumps({"code": 2, "msg": "UserTemplates: list error"}),
            404,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
        return (
            json.dumps(
                {"code": 9, "msg": "UserTemplates general exception: " + str(e)}
            ),
            401,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/user/<id>/desktops", methods=["GET"])
def api_v3_user_desktops(id=False):
    if id == False:
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {"code": 8, "msg": "Incorrect access parameters. Check your query."}
            ),
            401,
            {"Content-Type": "application/json"},
        )

    try:
        desktops = app.lib.UserDesktops(id)
        dropdown_desktops = [
            {
                "id": d["id"],
                "name": d["name"],
                "status": d["status"],
                "icon": d["icon"],
                "description": d["description"],
            }
            for d in desktops
        ]
        return json.dumps(dropdown_desktops), 200, {"Content-Type": "application/json"}
    except UserNotFound:
        log.error("User " + id + " not in database.")
        return (
            json.dumps({"code": 1, "msg": "UserDesktops: User not exists in database"}),
            404,
            {"Content-Type": "application/json"},
        )
    except UserDesktopsError:
        log.error("Template list for user " + id + " failed.")
        return (
            json.dumps({"code": 2, "msg": "UserDesktops: list error"}),
            404,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
        return (
            json.dumps({"code": 9, "msg": "UserDesktops general exception: " + str(e)}),
            401,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/login", methods=["POST"])
def api_v3_login():
    try:
        id = request.form.get("id", type=str)
        passwd = request.form.get("passwd", type=str)
    except Exception as e:
        return (
            json.dumps({"code": 8, "msg": "Incorrect access. exception: " + str(e)}),
            401,
            {"Content-Type": "application/json"},
        )
    if id == None or passwd == None:
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {"code": 8, "msg": "Incorrect access parameters. Check your query."}
            ),
            401,
            {"Content-Type": "application/json"},
        )

    try:
        app.lib.Login(id, passwd)
        return json.dumps({}), 200, {"Content-Type": "application/json"}
    except UserLoginFailed:
        log.error("User " + id + " login failed.")
        return (
            json.dumps({"code": 1, "msg": "User login failed"}),
            403,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
        return (
            json.dumps({"code": 9, "msg": "UserExists general exception: " + str(e)}),
            401,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/desktop", methods=["POST"])
def api_v3_desktop_new():
    try:
        user_id = request.form.get("id", type=str)
        template = request.form.get("template", type=str)
    except Exception as e:
        return (
            json.dumps({"code": 8, "msg": "Incorrect access. exception: " + str(e)}),
            401,
            {"Content-Type": "application/json"},
        )
    if user_id == None or template == None:
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {"code": 8, "msg": "Incorrect access parameters. Check your query."}
            ),
            401,
            {"Content-Type": "application/json"},
        )

    try:
        quotas.DesktopCreateAndStart(user_id)
    except QuotaUserConcurrentExceeded:
        log.error(
            "Quota for user " + user_id + " for starting another desktop is exceeded"
        )
        return (
            json.dumps(
                {"code": 11, "msg": "DesktopNew user quota CONCURRENT exceeded"}
            ),
            507,
            {"Content-Type": "application/json"},
        )
    except QuotaCategoryConcurrentExceeded:
        log.error(
            "Quota for user "
            + user_id
            + " category for starting another desktop is exceeded"
        )
        return (
            json.dumps(
                {
                    "code": 11,
                    "msg": "DesktopNew user category quota CONCURRENT exceeded",
                }
            ),
            507,
            {"Content-Type": "application/json"},
        )
    except QuotaCategoryVcpuExceeded:
        log.error(
            "Quota for user "
            + user_id
            + " category for desktop vCPU allocation is exceeded"
        )
        return (
            json.dumps(
                {
                    "code": 11,
                    "msg": "DesktopNew user category quota vCPU allocation exceeded",
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
                    "code": 11,
                    "msg": "DesktopNew user category quota MEMORY allocation exceeded",
                }
            ),
            507,
            {"Content-Type": "application/json"},
        )
    except QuotaUserNewDesktopExceeded:
        log.error(
            "Quota for user " + user_id + " for creating another desktop is exceeded"
        )
        return (
            json.dumps(
                {"code": 11, "msg": "DesktopNew user category quota CREATE exceeded"}
            ),
            507,
            {"Content-Type": "application/json"},
        )
    except QuotaGroupNewDesktopExceeded:
        log.error(
            "Quota for user "
            + user_id
            + " group for creating another desktop is exceeded"
        )
        return (
            json.dumps(
                {"code": 11, "msg": "DesktopNew user category quota CREATE exceeded"}
            ),
            507,
            {"Content-Type": "application/json"},
        )
    except QuotaCategoryNewDesktopExceeded:
        log.error(
            "Quota for user "
            + user_id
            + " category for creating another desktop is exceeded"
        )
        return (
            json.dumps(
                {"code": 11, "msg": "DesktopNew user category quota CREATE exceeded"}
            ),
            507,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
        return (
            json.dumps(
                {
                    "code": 9,
                    "msg": "DesktopNew quota check general exception: " + str(e),
                }
            ),
            401,
            {"Content-Type": "application/json"},
        )

    try:
        now = time.time()
        desktop_id = app.lib.DesktopNewNonpersistent(user_id, template)
        return json.dumps({"id": desktop_id}), 200, {"Content-Type": "application/json"}
    except UserNotFound:
        log.error(
            "Desktop for user "
            + user_id
            + " from template "
            + template
            + ", user not found"
        )
        return (
            json.dumps({"code": 1, "msg": "DesktopNew user not found"}),
            404,
            {"Content-Type": "application/json"},
        )
    except TemplateNotFound:
        log.error(
            "Desktop for user "
            + user_id
            + " from template "
            + template
            + " template not found."
        )
        return (
            json.dumps({"code": 2, "msg": "DesktopNew template not found"}),
            404,
            {"Content-Type": "application/json"},
        )
    except DesktopNotCreated:
        log.error(
            "Desktop for user "
            + user_id
            + " from template "
            + template
            + " creation failed."
        )
        return (
            json.dumps({"code": 1, "msg": "DesktopNew not created"}),
            404,
            {"Content-Type": "application/json"},
        )
    except DesktopActionTimeout:
        log.error(
            "Desktop for user "
            + user_id
            + " from template "
            + template
            + " start timeout."
        )
        return (
            json.dumps({"code": 2, "msg": "DesktopNew start timeout"}),
            404,
            {"Content-Type": "application/json"},
        )
    except DesktopActionFailed:
        log.error(
            "Desktop for user "
            + user_id
            + " from template "
            + template
            + " start failed."
        )
        return (
            json.dumps({"code": 3, "msg": "DesktopNew start failed"}),
            404,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
        return (
            json.dumps({"code": 9, "msg": "DesktopNew general exception: " + str(e)}),
            401,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/desktop/<desktop_id>/viewer/<protocol>", methods=["GET"])
def api_v3_desktop_viewer(desktop_id=False, protocol=False):
    if desktop_id == False or protocol == False:
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {"code": 8, "msg": "Incorrect access parameters. Check your query."}
            ),
            401,
            {"Content-Type": "application/json"},
        )

    try:
        viewer = app.lib.DesktopViewer(desktop_id, protocol)
        return json.dumps({"viewer": viewer}), 200, {"Content-Type": "application/json"}
    except DesktopNotFound:
        log.error(
            "Viewer for desktop "
            + desktop_id
            + " with protocol "
            + protocol
            + ", desktop not found"
        )
        return (
            json.dumps({"code": 1, "msg": "Desktop viewer id not found"}),
            404,
            {"Content-Type": "application/json"},
        )
    except DesktopNotStarted:
        log.error(
            "Viewer for desktop "
            + desktop_id
            + " with protocol "
            + protocol
            + ", desktop not started"
        )
        return (
            json.dumps({"code": 2, "msg": "Desktop viewer is not started"}),
            404,
            {"Content-Type": "application/json"},
        )
    except NotAllowed:
        log.error(
            "Viewer for desktop "
            + desktop_id
            + " with protocol "
            + protocol
            + ", viewer access not allowed"
        )
        return (
            json.dumps({"code": 3, "msg": "Desktop viewer id not owned by user"}),
            404,
            {"Content-Type": "application/json"},
        )
    except ViewerProtocolNotFound:
        log.error(
            "Viewer for desktop "
            + desktop_id
            + " with protocol "
            + protocol
            + ", viewer protocol not found"
        )
        return (
            json.dumps({"code": 4, "msg": "Desktop viewer protocol not found"}),
            404,
            {"Content-Type": "application/json"},
        )
    except ViewerProtocolNotImplemented:
        log.error(
            "Viewer for desktop "
            + desktop_id
            + " with protocol "
            + protocol
            + ", viewer protocol not implemented"
        )
        return (
            json.dumps({"code": 5, "msg": "Desktop viewer protocol not implemented"}),
            404,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
        return (
            json.dumps(
                {"code": 9, "msg": "DesktopViewer general exception: " + str(e)}
            ),
            401,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/desktop/<desktop_id>", methods=["DELETE"])
def api_v3_desktop_delete(desktop_id=False):
    if desktop_id == False:
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {"code": 8, "msg": "Incorrect access parameters. Check your query."}
            ),
            401,
            {"Content-Type": "application/json"},
        )

    try:
        now = time.time()
        app.lib.DesktopDelete(desktop_id)
        return json.dumps({}), 200, {"Content-Type": "application/json"}
    except DesktopNotFound:
        log.error("Desktop delete " + desktop_id + ", desktop not found")
        return (
            json.dumps({"code": 1, "msg": "Desktop delete id not found"}),
            404,
            {"Content-Type": "application/json"},
        )
    except DesktopDeleteFailed:
        log.error("Desktop delete " + desktop_id + ", desktop delete failed")
        return (
            json.dumps({"code": 5, "msg": "Desktop delete deleting failed"}),
            404,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
        return (
            json.dumps(
                {"code": 9, "msg": "DesktopDelete general exception: " + str(e)}
            ),
            401,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/persistent_desktop", methods=["POST"])
def api_v3_persistent_desktop_new():
    try:
        name = request.form.get("name", type=str)
        user_id = request.form.get("user_id", type=str)
        memory = request.form.get("memory", type=float)
        vcpus = request.form.get("vcpus", type=int)

        template_id = request.form.get("template_id", type=str)
        xml_id = request.form.get("xml_id", type=str)

        disk_size = request.form.get("disk_size", type=str)
    except Exception as e:
        return (
            json.dumps({"code": 8, "msg": "Incorrect access. exception: " + str(e)}),
            401,
            {"Content-Type": "application/json"},
        )

    if user_id == None or name == None or vcpus == None or memory == None:
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {"code": 8, "msg": "Incorrect access parameters. Check your query."}
            ),
            401,
            {"Content-Type": "application/json"},
        )

    try:
        quotas.DesktopCreate(user_id)
    except QuotaUserNewDesktopExceeded:
        log.error(
            "Quota for user " + user_id + " for creating another desktop is exceeded"
        )
        return (
            json.dumps(
                {
                    "code": 11,
                    "msg": "PersistentDesktopNew user category quota CREATE exceeded",
                }
            ),
            507,
            {"Content-Type": "application/json"},
        )
    except QuotaGroupNewDesktopExceeded:
        log.error(
            "Quota for user "
            + user_id
            + " group for creating another desktop is exceeded"
        )
        return (
            json.dumps(
                {
                    "code": 11,
                    "msg": "PersistentDesktopNew user category quota CREATE exceeded",
                }
            ),
            507,
            {"Content-Type": "application/json"},
        )
    except QuotaCategoryNewDesktopExceeded:
        log.error(
            "Quota for user "
            + user_id
            + " category for creating another desktop is exceeded"
        )
        return (
            json.dumps(
                {
                    "code": 11,
                    "msg": "PersistentDesktopNew user category quota CREATE exceeded",
                }
            ),
            507,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
        return (
            json.dumps(
                {
                    "code": 9,
                    "msg": "PersistentDesktopNew quota check general exception: "
                    + str(e),
                }
            ),
            401,
            {"Content-Type": "application/json"},
        )

    try:
        now = time.time()
        # desktop_id = app.lib.DesktopNewPersistent(name, user_id,memory,vcpus,xml_id=xml_id, disk_size=disk_size)
        desktop_id = app.lib.DesktopNewPersistent(
            name,
            user_id,
            memory,
            vcpus,
            from_template_id=template_id,
            disk_size=disk_size,
        )
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
            json.dumps({"code": 1, "msg": "PersistentDesktopNew user not found"}),
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
            json.dumps({"code": 2, "msg": "PersistentDesktopNew template not found"}),
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
            json.dumps({"code": 1, "msg": "PersistentDesktopNew not created"}),
            404,
            {"Content-Type": "application/json"},
        )
    ### Needs more!
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
        return (
            json.dumps(
                {"code": 9, "msg": "PersistentDesktopNew general exception: " + str(e)}
            ),
            401,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/template", methods=["POST"])
def api_v3_template_new():
    try:
        name = request.form.get("name", type=str)
        user_id = request.form.get("user_id", type=str)
        desktop_id = request.form.get("desktop_id", type=str)
    except Exception as e:
        return (
            json.dumps({"code": 8, "msg": "Incorrect access. exception: " + str(e)}),
            401,
            {"Content-Type": "application/json"},
        )

    if user_id == None or name == None or desktop_id == None:
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {"code": 8, "msg": "Incorrect access parameters. Check your query."}
            ),
            401,
            {"Content-Type": "application/json"},
        )

    try:
        quotas.DesktopCreate(user_id)
    except QuotaUserNewDesktopExceeded:
        log.error(
            "Quota for user " + user_id + " for creating another desktop is exceeded"
        )
        return (
            json.dumps(
                {"code": 11, "msg": "TemplateNew user category quota CREATE exceeded"}
            ),
            507,
            {"Content-Type": "application/json"},
        )
    except QuotaGroupNewDesktopExceeded:
        log.error(
            "Quota for user "
            + user_id
            + " group for creating another desktop is exceeded"
        )
        return (
            json.dumps(
                {"code": 11, "msg": "TemplateNew user category quota CREATE exceeded"}
            ),
            507,
            {"Content-Type": "application/json"},
        )
    except QuotaCategoryNewDesktopExceeded:
        log.error(
            "Quota for user "
            + user_id
            + " category for creating another desktop is exceeded"
        )
        return (
            json.dumps(
                {"code": 11, "msg": "TemplateNew user category quota CREATE exceeded"}
            ),
            507,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
        return (
            json.dumps(
                {
                    "code": 9,
                    "msg": "TemplateNew quota check general exception: " + str(e),
                }
            ),
            401,
            {"Content-Type": "application/json"},
        )

    try:
        now = time.time()
        # desktop_id = app.lib.DesktopNewPersistent(name, user_id,memory,vcpus,xml_id=xml_id, disk_size=disk_size)
        template_id = app.lib.TemplateNew(name, user_id, desktop_id)
        return (
            json.dumps({"id": template_id}),
            200,
            {"Content-Type": "application/json"},
        )
    except UserNotFound:
        log.error(
            "Template for user "
            + user_id
            + " from desktop "
            + desktop_id
            + ", user not found"
        )
        return (
            json.dumps({"code": 1, "msg": "TemplateNew user not found"}),
            404,
            {"Content-Type": "application/json"},
        )
    except TemplateNotFound:
        log.error(
            "Template for user "
            + user_id
            + " from desktop "
            + desktop_id
            + " template not found."
        )
        return (
            json.dumps({"code": 2, "msg": "TemplateNew template not found"}),
            404,
            {"Content-Type": "application/json"},
        )
    except DesktopNotCreated:
        log.error(
            "Template for user "
            + user_id
            + " from desktop "
            + desktop_id
            + " creation failed."
        )
        return (
            json.dumps({"code": 1, "msg": "TemplateNew not created"}),
            404,
            {"Content-Type": "application/json"},
        )
    ### Needs more!
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
        return (
            json.dumps({"code": 9, "msg": "TemplateNew general exception: " + str(e)}),
            401,
            {"Content-Type": "application/json"},
        )

    # except DesktopActionTimeout:
    #    log.error("Desktop delete "+desktop_id+", desktop stop timeout")
    #    return json.dumps({"code":2,"msg":"Desktop delete stopping timeout"}), 404, {'Content-Type': 'application/json'}
    # except DesktopActionFailed:
    #    log.error("Desktop delete "+desktop_id+", desktop stop failed")
    #    return json.dumps({"code":3,"msg":"Desktop delete stopping failed"}), 404, {'Content-Type': 'application/json'}
    # except DesktopDeleteTimeout:
    #    log.error("Desktop delete "+desktop_id+", desktop delete timeout")
    #    return json.dumps({"code":4,"msg":"Desktop delete deleting timeout"}), 404, {'Content-Type': 'application/json'}
