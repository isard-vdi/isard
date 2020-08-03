# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8
from flask import render_template, Response, request, redirect, url_for
from flask_login import login_required, current_user
from .decorators import ownsid
from webapp import app
from ..lib.log import *

import rethinkdb as r
from ..lib.flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

import time, json

@app.route('/isard-admin/desktops')
@login_required
def desktops():
    return render_template('pages/desktops.html', title="Desktops", nav="Desktops")

@app.route('/isard-admin/desktops/get')
@login_required
def desktops_get():
    return json.dumps(app.isardapi.get_user_domains(current_user.id)), 200, {'ContentType': 'application/json'}

@app.route('/isard-admin/desktops/download_viewer/<os>/<id>')
@login_required
@ownsid
def viewer_download(os,id):
    try:
        extension,mimetype,consola=app.isardapi.get_viewer_ticket(id,os)
        return Response(consola, 
                    mimetype=mimetype,
                    headers={"Content-Disposition":"attachment;filename=consola."+extension})
    except Exception as e:
        log.error('Download viewer error:'+str(e))
        return Response('Error in viewer',mimetype='application/txt')
        
# ~ @app.route('/disposable/download_viewer/<os>/<id>')
# ~ def viewer_disposable_download(os,id):
    # ~ remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    # ~ if id.startswith('_disposable_'+remote_addr.replace('.','_')+'_'):
        # ~ extension,mimetype,consola=app.isardapi.get_viewer_ticket(id,os)
        # ~ return Response(consola, 
                        # ~ mimetype=mimetype,
                        # ~ headers={"Content-Disposition":"attachment;filename=consola."+extension})
                        
# ~ #~ Serves desktops and templates (domains)
@app.route('/isard-admin/domains/update', methods=['POST'])
@login_required
@ownsid
def domains_update():
    if request.method == 'POST':
        try:
            args = request.get_json(force=True)
        except:
            args = request.form.to_dict()
        try:
            exceeded = app.isardapi.check_quota_limits('NewConcurrent',current_user.id)
            if exceeded != False:  
                 return json.dumps('Quota for starting domains full. '+exceeded), 500, {'ContentType':'application/json'}
            if app.isardapi.update_table_value('domains', args['pk'], args['name'], args['value']):
                return json.dumps('Updated'), 200, {'ContentType':'application/json'}
            else:
                return json.dumps('This is not a valid value.'), 500, {'ContentType':'application/json'}
        except Exception as e:
            return json.dumps('Wrong parameters.'), 500, {'ContentType':'application/json'}


# Gets all allowed for a domain
@app.route('/isard-admin/domain/alloweds/select2', methods=['POST'])
@login_required
def domain_alloweds_select2():
    allowed=request.get_json(force=True)['allowed']
    return json.dumps(app.isardapi.get_alloweds_select2(allowed))
       

# We should remove this
# Not used?
@app.route('/isard-admin/desktops/filterTemplate/<kind>', methods=['GET'])
@app.route('/isard-admin/desktops/filterTemplate/<kind>/category/<category>', methods=['GET'])
@app.route('/isard-admin/desktops/filterTemplate/<kind>/group/<group>', methods=['GET'])
@app.route('/isard-admin/desktops/filterTemplate/<kind>/user/<user>', methods=['GET'])
@login_required
def filterTemplate(kind,category=False,group=False,user=False):
    custom_filter={}
    if category:
        custom_filter['category']=category
    if group:
        custom_filter['group']=group
    if user:
        custom_filter['user']=user
    return Response(json.dumps(app.isardapi.get_alloweds_domains(current_user.id,kind, custom_filter)), mimetype='application/json')

# Get all templates allowed for current_user
@app.route('/isard-admin/desktops/getAllTemplates', methods=['GET'])
@login_required
def getAllTemplates():
    templates = app.isardapi.get_all_alloweds_domains(current_user.id)
    templates = [t for t in templates if t['status']=='Stopped']
    if current_user.role != "admin":
        templates = [t for t in templates if t['category'] == current_user.category or t['category'] == 'default']
    return Response(json.dumps(templates), mimetype='application/json')

# Gets users, categories and groups
@app.route('/isard-admin/desktops/getDistinc/<field>/<kind>', methods=['GET'])
@login_required
def getDistinct(field,kind):
    data=app.isardapi.get_distinc_field(current_user.id, field, kind)
    return Response(json.dumps(data), mimetype='application/json')

# Gets 
@app.route('/isard-admin/desktops/templateUpdate/<id>', methods=['GET'])
@login_required
def templateUpdate(id):
    hardware=app.isardapi.get_domain(id)
    return Response(json.dumps(hardware),  mimetype='application/json')

