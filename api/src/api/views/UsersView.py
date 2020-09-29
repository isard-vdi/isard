# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
from api import app
import logging as log
import traceback

from uuid import uuid4
import time,json
import sys,os
from flask import request
from ..libv2.apiv2_exc import *
from ..libv2.quotas_exc import *

#from ..libv2.telegram import tsend
def tsend(txt):
    None
from ..libv2.carbon import Carbon
carbon = Carbon()

from ..libv2.quotas import Quotas
quotas = Quotas()

from ..libv2.api_users import ApiUsers
users = ApiUsers()

@app.route('/api/v2', methods=['GET'])
def api_v2_test():
    return "IsardVDI api v2", 200, {'ContentType': 'application/json'}

@app.route('/api/v2/login', methods=['POST'])
def api_v2_login():
    try:
        id = request.form.get('id', type = str)
        passwd = request.form.get('passwd', type = str)
    except Exception as e:
        return json.dumps({"code":8,"msg":"Incorrect access. exception: " + error }), 401, {'ContentType': 'application/json'}
    if id == None or passwd == None:
        log.error("Incorrect access parameters. Check your query.")
        return json.dumps({"code":8,"msg":"Incorrect access parameters. Check your query." }), 401, {'ContentType': 'application/json'}

    try:
        users.Login(id,passwd)
        return json.dumps({}), 200, {'ContentType': 'application/json'}
    except UserLoginFailed:
        log.error("User "+id+" login failed.")
        return json.dumps({"code":1,"msg":"User login failed"}), 403, {'ContentType': 'application/json'}
    except Exception as e:
        error = traceback.format_exc()
        return json.dumps({"code":9,"msg":"UserExists general exception: " + error }), 401, {'ContentType': 'application/json'}

@app.route('/api/v2/category/<id>', methods=['GET'])
def api_v2_category(id):
    try:
        data = users.CategoryGet(id)
        return json.dumps(data), 200, {'ContentType': 'application/json'}
    except CategoryNotFound:
        return json.dumps({"code":1,"msg":"Category "+id+" not exists in database"}), 404, {'ContentType': 'application/json'}

    except Exception as e:
        error = traceback.format_exc()
        return json.dumps({"code":9,"msg":"Register general exception: " + error }), 500, {'ContentType': 'application/json'}

@app.route('/api/v2/register', methods=['POST'])
def api_v2_register():
    try:
        code = request.form.get('code', type = str)
    except Exception as e:
        return json.dumps({"code":8,"msg":"Incorrect access. exception: " + error }), 401, {'ContentType': 'application/json'}

    try:
        data = users.CodeSearch(code)
        return json.dumps(data), 200, {'ContentType': 'application/json'}
    except CodeNotFound:
        log.error("Code not in database.")
        return json.dumps({"code":1,"msg":"Code "+code+" not exists in database"}), 404, {'ContentType': 'application/json'}
    except Exception as e:
        error = traceback.format_exc()
        return json.dumps({"code":9,"msg":"Register general exception: " + error }), 401, {'ContentType': 'application/json'}

@app.route('/api/v2/user/<id>', methods=['GET'])
def api_v2_user_exists(id=False):
    if id == False:
        log.error("Incorrect access parameters. Check your query.")
        return json.dumps({"code":8,"msg":"Incorrect access parameters. Check your query." }), 401, {'ContentType': 'application/json'}

    try:
        user=users.Exists(id)
        return json.dumps(user), 200, {'ContentType': 'application/json'}
    except UserNotFound:
        log.error("User "+id+" not in database.")
        return json.dumps({"code":1,"msg":"User not exists in database"}), 404, {'ContentType': 'application/json'}
    except Exception as e:
        error = traceback.format_exc()
        return json.dumps({"code":9,"msg":"UserExists general exception: " + error }), 401, {'ContentType': 'application/json'}

# Update user name
@app.route('/api/v2/user/<id>', methods=['PUT'])
def api_v2_user_update(id=False):
    if id == False:
        log.error("Incorrect access parameters. Check your query.")
        return json.dumps({"code":8,"msg":"Incorrect access parameters. Check your query." }), 401, {'ContentType': 'application/json'}

    try:
        name = request.form.get('name', False)
        email = request.form.get('email', False)
        photo = request.form.get('photo', False)
    except Exception as e:
        return json.dumps({"code":8,"msg":"Incorrect access. exception: " + error }), 401, {'ContentType': 'application/json'}

    if name == False and email == False and photo == False:
        log.error("Incorrect access parameters. Check your query.")
        return json.dumps({"code":8,"msg":"Incorrect access parameters. Check your query. At least one parameter should be specified." }), 401, {'ContentType': 'application/json'}
    try:
        users.Update(id,user_name=name,user_email=email,user_photo=photo)
        return json.dumps({}), 200, {'ContentType': 'application/json'}
    except UpdateFailed:
        log.error("User "+id+" update failed.")
        return json.dumps({"code":1,"msg":"User update failed"}), 404, {'ContentType': 'application/json'}
    except Exception as e:
        error = traceback.format_exc()
        return json.dumps({"code":9,"msg":"UserUpdate general exception: " + error }), 401, {'ContentType': 'application/json'}

# Add user
@app.route('/api/v2/user', methods=['POST'])
def api_v2_user_insert():
    try:
        # Required
        provider = request.form.get('provider', type = str)
        user_uid = request.form.get('user_uid', type = str)
        user_username = request.form.get('user_username', type = str)
        role_id = request.form.get('role', type = str)
        category_id = request.form.get('category', type = str)
        group_id = request.form.get('group', type = str)

        # Optional
        name=request.form.get('name', user_username, type = str)
        password = request.form.get('password', False, type = str)
        encrypted_password = request.form.get('encrypted_password', False, type = str)
        photo = request.form.get('photo', '', type = str)
        email = request.form.get('email', '', type = str)
    except Exception as e:
        return json.dumps({"code":8,"msg":"Incorrect access. exception: " + error }), 401, {'ContentType': 'application/json'}
    if provider == None or user_username == None or role_id == None or category_id == None or group_id == None:
        log.error("Incorrect access parameters. Check your query.")
        return json.dumps({"code":8,"msg":"Incorrect access parameters. Check your query." }), 401, {'ContentType': 'application/json'}
    if password == None: password = False

    try:
        quotas.UserCreate(category_id,group_id)
    except QuotaCategoryNewUserExceeded:
        log.error("Quota for creating another user in category "+category_id+" is exceeded")
        return json.dumps({"code":11,"msg":"UserNew category quota for adding user exceeded"}), 507, {'ContentType': 'application/json'}
    except QuotaGroupNewUserExceeded:
        log.error("Quota for creating another user in group "+group_id+" is exceeded")
        return json.dumps({"code":11,"msg":"UserNew group quota for adding user exceeded"}), 507, {'ContentType': 'application/json'}
    except Exception as e:
        error = traceback.format_exc()
        return json.dumps({"code":9,"msg":"UserNew quota check general exception: " + error }), 401, {'ContentType': 'application/json'}


    try:
        user_id=users.Create( provider, \
                                    category_id, \
                                    user_uid, \
                                    user_username, \
                                    name, \
                                    role_id, \
                                    group_id, \
                                    password, \
                                    encrypted_password, \
                                    photo, \
                                    email)
        return json.dumps({'id':user_id}), 200, {'ContentType': 'application/json'}
    except UserExists:
        log.error("User "+user_username+" already exists.")
        return json.dumps({"code":1,"msg":"User already exists"}), 404, {'ContentType': 'application/json'}
    except RoleNotFound:
        log.error("Role "+role_username+" not found.")
        return json.dumps({"code":2,"msg":"Role not found"}), 404, {'ContentType': 'application/json'}
    except CategoryNotFound:
        log.error("Category "+category_id+" not found.")
        return json.dumps({"code":3,"msg":"Category not found"}), 404, {'ContentType': 'application/json'}
    except GroupNotFound:
        log.error("Group "+group_id+" not found.")
        return json.dumps({"code":4,"msg":"Group not found"}), 404, {'ContentType': 'application/json'}
    except NewUserNotInserted:
        log.error("User "+user_username+" could not be inserted into database.")
        return json.dumps({"code":5,"msg":"User could not be inserted into database. Already exists!"}), 404, {'ContentType': 'application/json'}
    except Exception as e:
        error = traceback.format_exc()
        return json.dumps({"code":9,"msg":"UserUpdate general exception: " + error }), 401, {'ContentType': 'application/json'}

@app.route('/api/v2/user/<user_id>', methods=['DELETE'])
def api_v2_user_delete(user_id):
    try:
        users.Delete(user_id)
        return json.dumps({}), 200, {'ContentType': 'application/json'}
    except UserNotFound:
        log.error("User delete "+user_id+", user not found")
        return json.dumps({"code":1,"msg":"User delete id not found"}), 404, {'ContentType': 'application/json'}
    except UserDeleteFailed:
        log.error("User delete "+user_id+", user delete failed")
        return json.dumps({"code":2,"msg":"User delete failed"}), 404, {'ContentType': 'application/json'}
    except DesktopDeleteFailed:
        log.error("User delete for user "+user_id+", desktop delete failed")
        return json.dumps({"code":5,"msg":"User delete, desktop deleting failed"}), 404, {'ContentType': 'application/json'}
    except Exception as e:
        error = traceback.format_exc()
        return json.dumps({"code":9,"msg":"UserDelete general exception: " + error }), 401, {'ContentType': 'application/json'}

@app.route('/api/v2/user/<id>/templates', methods=['GET'])
def api_v2_user_templates(id=False):
    if id == False:
        log.error("Incorrect access parameters. Check your query.")
        return json.dumps({"code":8,"msg":"Incorrect access parameters. Check your query." }), 401, {'ContentType': 'application/json'}

    """ try:
        quotas.DesktopCreateAndStart(id)
    except QuotaUserNewDesktopExceeded:
        log.error("Quota for user "+id+" to create a desktop exceeded")
        return json.dumps({"code":11,"msg":"DestopNew user desktop quota CREATE exceeded"}), 507, {'ContentType': 'application/json'}
    except QuotaGroupNewDesktopExceeded:
        log.error("Quota for user "+id+" to create a desktop in his group limits is exceeded")
        return json.dumps({"code":11,"msg":"DestopNew group desktop limits CREATE exceeded"}), 507, {'ContentType': 'application/json'}
    except QuotaCategoryNewDesktopExceeded:
        log.error("Quota for user "+id+" to create a desktop in his category limits is exceeded")
        return json.dumps({"code":11,"msg":"DestopNew category desktop limits CREATE exceeded"}), 507, {'ContentType': 'application/json'}

    except QuotaUserConcurrentExceeded:
        log.error("Quota for user "+id+" to start a desktop is exceeded")
        return json.dumps({"code":11,"msg":"DestopNew user quota CONCURRENT exceeded"}), 507, {'ContentType': 'application/json'}
    except QuotaGroupConcurrentExceeded:
        log.error("Quota for user "+id+" to start a desktop in his group is exceeded")
        return json.dumps({"code":11,"msg":"DestopNew user limits CONCURRENT exceeded"}), 507, {'ContentType': 'application/json'}
    except QuotaCategoryConcurrentExceeded:
        log.error("Quota for user "+id+" to start a desktop is his category exceeded")
        return json.dumps({"code":11,"msg":"DestopNew user category limits CONCURRENT exceeded"}), 507, {'ContentType': 'application/json'}
    
    except QuotaUserVcpuExceeded:
        log.error("Quota for user "+id+" to allocate vCPU is exceeded")
        return json.dumps({"code":11,"msg":"DestopNew user quota vCPU allocation exceeded"}), 507, {'ContentType': 'application/json'}
    except QuotaGroupVcpuExceeded:
        log.error("Quota for user "+id+" to allocate vCPU in his group is exceeded")
        return json.dumps({"code":11,"msg":"DestopNew user group limits vCPU allocation exceeded"}), 507, {'ContentType': 'application/json'}
    except QuotaCategoryVcpuExceeded:
        log.error("Quota for user "+id+" to allocate vCPU in his category is exceeded")
        return json.dumps({"code":11,"msg":"DestopNew user category limits vCPU allocation exceeded"}), 507, {'ContentType': 'application/json'}

    except QuotaUserMemoryExceeded:
        log.error("Quota for user "+id+" to allocate MEMORY is exceeded")
        return json.dumps({"code":11,"msg":"DestopNew user quota MEMORY allocation exceeded"}), 507, {'ContentType': 'application/json'}
    except QuotaGroupMemoryExceeded:
        log.error("Quota for user "+id+" for creating another desktop is exceeded")
        return json.dumps({"code":11,"msg":"DestopNew user group limits MEMORY allocation exceeded"}), 507, {'ContentType': 'application/json'}
    except QuotaCategoryMemoryExceeded:
        log.error("Quota for user "+id+" category for desktop MEMORY allocation is exceeded")
        return json.dumps({"code":11,"msg":"DestopNew user category limits MEMORY allocation exceeded"}), 507, {'ContentType': 'application/json'}

    except Exception as e:
        error = traceback.format_exc()
        return json.dumps({"code":9,"msg":"DesktopNew quota check general exception: " + error }), 401, {'ContentType': 'application/json'} """

    try:
        templates = users.Templates(id)
        dropdown_templates = [{'id':t['id'],'name':t['name'],'icon':t['icon'],'image':'','description':t['description']} for t in templates]
        return json.dumps(dropdown_templates), 200, {'ContentType': 'application/json'}
    except UserNotFound:
        log.error("User "+id+" not in database.")
        return json.dumps({"code":1,"msg":"UserTemplates: User not exists in database"}), 404, {'ContentType': 'application/json'}
    except UserTemplatesError:
        log.error("Template list for user "+id+" failed.")
        return json.dumps({"code":2,"msg":"UserTemplates: list error"}), 404, {'ContentType': 'application/json'}
    except Exception as e:
        error = traceback.format_exc()
        return json.dumps({"code":9,"msg":"UserTemplates general exception: " + error }), 401, {'ContentType': 'application/json'}

@app.route('/api/v2/user/<id>/desktops', methods=['GET'])
def api_v2_user_desktops(id=False):
    if id == False:
        log.error("Incorrect access parameters. Check your query.")
        return json.dumps({"code":8,"msg":"Incorrect access parameters. Check your query." }), 401, {'ContentType': 'application/json'}

    try:
        desktops = users.Desktops(id)
        dropdown_desktops = [{'id':d['id'],'name':d['name'],'state':d['status'],'type':d['type'],'template':d['from_template'],'viewers':d['viewers'],'icon':d['icon'],'image':d['image'],'description':d['description']} for d in desktops]
        return json.dumps(dropdown_desktops), 200, {'ContentType': 'application/json'}
    except UserNotFound:
        log.error("User "+id+" not in database.")
        return json.dumps({"code":1,"msg":"UserDesktops: User not exists in database"}), 404, {'ContentType': 'application/json'}
    except UserDesktopsError:
        log.error("Desktops list for user "+id+" failed.")
        return json.dumps({"code":2,"msg":"UserDesktops: list error"}), 404, {'ContentType': 'application/json'}
    except Exception as e:
        error = traceback.format_exc()
        return json.dumps({"code":9,"msg":"UserDesktops general exception: " + error }), 401, {'ContentType': 'application/json'}


# Add categorygroup
@app.route('/api/v2/categorygroup', methods=['POST'])
def api_v2_categorygroup_insert():
    try:
        # Required
        category_name = request.form.get('category_name', type = str)
        group_name = request.form.get('group_name', type = str)

        # Optional
        category_limits = request.form.get('category_limits', False)
        if category_limits == 'False': category_limits = False
        if category_limits != False: category_limits=json.loads(category_limits)
        category_quota = request.form.get('category_quota', False)
        if category_quota == 'False': category_quota = False
        if category_quota != False: category_quota=json.loads(category_quota)
        group_quota = request.form.get('group_quota', False)
        if group_quota == 'False': group_quota = False
        if group_quota != False: group_quota=json.loads(group_quota)

    ## We should check here if limits and quotas have a correct dict schema

    ##
    except Exception as e:
        error = traceback.format_exc()
        return json.dumps({"code":8,"msg":"Incorrect access. exception: " + error }), 401, {'ContentType': 'application/json'}
    if category_name == None:
        log.error("Incorrect access parameters. Check your query.")
        return json.dumps({"code":8,"msg":"Incorrect access parameters. Check your query." }), 401, {'ContentType': 'application/json'}

    try:
        users.CategoryGroupCreate( category_name, \
                                            group_name,
                                            category_limits=category_limits,
                                            category_quota=category_quota,
                                            group_quota=group_quota)
        return json.dumps({}), 200, {'ContentType': 'application/json'}
    except Exception as e:
        log.error("Category / Group create error.")
        error = traceback.format_exc()
        return json.dumps({"code":9,"msg":"General exception when creating category/group pair: "+error}), 401, {'ContentType': 'application/json'}


@app.route('/api/v2/categories', methods=['GET'])
def api_v2_categories():
    try:
        return json.dumps(users.CategoriesGet()), 200, {'ContentType': 'application/json'}
    except Exception as e:
        error = traceback.format_exc()
        return json.dumps({"code":9,"msg":"CategoriesGet general exception: " + error }), 401, {'ContentType': 'application/json'}
