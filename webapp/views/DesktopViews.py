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

@app.route('/desktops')
@login_required
def desktops():
    return render_template('pages/desktops.html', title="Desktops", nav="Desktops")

@app.route('/desktops/get')
@login_required
def desktops_get():
    return json.dumps(app.isardapi.get_user_domains(current_user.username)), 200, {'ContentType': 'application/json'}
    # ~ if kind=='category': 
        # ~ return json.dumps(app.isardapi.get_category_domains(current_user.category)), 200, {'ContentType': 'application/json'}
    # ~ if kind=='group':
        # ~ return json.dumps(app.isardapi.get_group_domains(current_user.group)), 200, {'ContentType': 'application/json'}
    # ~ return url_for('desktops')

@app.route('/desktops/download_viewer/<os>/<id>')
@login_required
@ownsid
def viewer_download(os,id):
    try:
        extension,mimetype,consola=app.isardapi.get_viewer_ticket(id,os)
        return Response(consola, 
                    mimetype=mimetype,
                    headers={"Content-Disposition":"attachment;filename=consola."+extension})
    except Exception as e:
        print('Download viewer error:'+str(e))
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
@app.route('/domains/update', methods=['POST'])
@login_required
@ownsid
def domains_update():
    if request.method == 'POST':
        try:
            args = request.get_json(force=True)
        except:
            args = request.form.to_dict()
        try:
            if float(app.isardapi.get_user_quotas(current_user.username)['rqp']) >= 100:
                 return json.dumps('Quota for starting domains full.'), 500, {'ContentType':'application/json'}
            if app.isardapi.update_table_value('domains', args['pk'], args['name'], args['value']):
                return json.dumps('Updated'), 200, {'ContentType':'application/json'}
            else:
                return json.dumps('This is not a valid value.'), 500, {'ContentType':'application/json'}
        except Exception as e:
            return json.dumps('Wrong parameters.'), 500, {'ContentType':'application/json'}




# ~ @app.route('/domains/genealogy', methods=['POST'])
# ~ @login_required
# ~ @ownsid
# ~ def domains_genealogy():
    # ~ domain=app.isardapi.get_domain(request.get_json(force=True)['pk'], human_size=False)
    # ~ if 'disks_info' not in domain.keys():
        # ~ return json.dumps({'wasted':0,'free':0,'wasted_hs':0,'free_hs':0,'genealogy':[],'gen_ids':[]})
    # ~ gen=domain['disks_info']
    # ~ gen_human=app.isardapi.get_domain(request.get_json(force=True)['pk'], human_size=True)['disks_info']
    # ~ wasted=0
    # ~ try:
        # ~ for i,v in enumerate(gen):
            # ~ gen_human[i]['size_percentage']="%.0f" % round(gen[i]['actual-size']*100/gen[i]['virtual-size'],0),
            # ~ wasted+=gen[i]['actual-size']
        # ~ gen_ids=app.isardapi.get_backing_ids(request.get_json(force=True)['pk'])
    # ~ except Exception as e:
        # ~ return json.dumps({'wasted':0,'free':0,'wasted_hs':0,'free_hs':0,'genealogy':[],'gen_ids':[]})
    # ~ return json.dumps({'wasted':wasted,'free':gen[0]['virtual-size']-wasted,'wasted_hs':app.isardapi.human_size(wasted),'free_hs':app.isardapi.human_size(gen[0]['virtual-size']-wasted),'genealogy':gen_human,'gen_ids':gen_ids})


# ~ @app.route('/domains/derivates', methods=['POST'])
# ~ @login_required
# ~ @ownsid
# ~ def domains_derivates():
    # ~ return json.dumps(app.isardapi.get_domain_derivates(request.get_json(force=True)['pk']))





        
# ~ @app.route('/domain/alloweds', methods=['POST'])
# ~ @login_required
# ~ @ownsid
# ~ def domain_alloweds():
    # ~ return json.dumps(app.isardapi.f.unflatten_dict(app.isardapi.get_domain(request.get_json(force=True)['pk']))['allowed'])

# Gets all allowed for a domain
@app.route('/domain/alloweds/select2', methods=['POST'])
@login_required
def domain_alloweds_select2():
    allowed=request.get_json(force=True)['allowed']
    return json.dumps(app.isardapi.get_alloweds_select2(allowed))
       

# We should remove this
@app.route('/desktops/filterTemplate/<kind>', methods=['GET'])
@app.route('/desktops/filterTemplate/<kind>/category/<category>', methods=['GET'])
@app.route('/desktops/filterTemplate/<kind>/group/<group>', methods=['GET'])
@app.route('/desktops/filterTemplate/<kind>/user/<user>', methods=['GET'])
@login_required
def filterTemplate(kind,category=False,group=False,user=False):
    #~ dict={'kind':kind}
    custom_filter={}
    #~ if kind == 'user_template': 
        #~ custom_filter['user']=current_user.username
    #~ else:
    if category:
        custom_filter['category']=category
    if group:
        custom_filter['group']=group
    if user:
        custom_filter['user']=user
    #~ domains = app.isardapi.get_templates(dict)
    #~ return Response(json.dumps(domains), mimetype='application/json')
    return Response(json.dumps(app.isardapi.get_alloweds_domains(current_user.username,kind, custom_filter)), mimetype='application/json')
    #~ return Response(json.dumps(app.isardapi.get_all_alloweds_table(current_user.username,kind, custom_filter)), mimetype='application/json')

# Get all templates allowed for current_user
@app.route('/desktops/getAllTemplates', methods=['GET'])
@login_required
def getAllTemplates():
    custom_filter={}
    return Response(json.dumps(app.isardapi.get_all_alloweds_domains(current_user.username)), mimetype='application/json')

# Gets users, categories and groups
@app.route('/desktops/getDistinc/<field>/<kind>', methods=['GET'])
@login_required
def getDistinct(field,kind):
    data=app.isardapi.get_distinc_field(current_user.username, field, kind)
    return Response(json.dumps(data), mimetype='application/json')

# Gets 
@app.route('/desktops/templateUpdate/<id>', methods=['GET'])
@login_required
def templateUpdate(id):
    hardware=app.isardapi.get_domain(id)
    return Response(json.dumps(hardware),  mimetype='application/json')

# Will get allowed resources for current_user         
# ~ @app.route('/domains/hardware/allowed', methods=['GET'])
# ~ @login_required
# ~ def domains_hardware_allowed():
    # ~ dict={}
    # ~ dict['nets']=app.isardapi.get_alloweds(current_user.username,'interfaces',pluck=['id','name','description'],order='name')
    # ~ #~ dict['disks']=app.isardapi.get_alloweds(current_user.username,'disks',pluck=['id','name','description'],order='name')
    # ~ dict['graphics']=app.isardapi.get_alloweds(current_user.username,'graphics',pluck=['id','name','description'],order='name')
    # ~ dict['videos']=app.isardapi.get_alloweds(current_user.username,'videos',pluck=['id','name','description'],order='name')
    # ~ dict['boots']=app.isardapi.get_alloweds(current_user.username,'boots',pluck=['id','name','description'],order='name')
    # ~ dict['hypervisors_pools']=app.isardapi.get_alloweds(current_user.username,'hypervisors_pools',pluck=['id','name','description'],order='name')
    # ~ dict['forced_hyps']=[]
    # ~ if current_user.role == 'admin':
        # ~ dict['forced_hyps']=app.adminapi.get_admin_table('hypervisors',['id','hostname','description','status'])
    # ~ dict['forced_hyps'].insert(0,{'id':'default','hostname':'Auto','description':'Hypervisor pool default'})
    # ~ dict['user']=app.isardapi.get_user(current_user.username)
    # ~ return json.dumps(dict)

# Get hardware for domain
# ~ @app.route('/domains/hardware', methods=['POST'])
# ~ @login_required
# ~ @ownsid
# ~ def domains_hadware():
    # ~ try:
        # ~ hs=request.get_json(force=True)['hs']
    # ~ except:
        # ~ hs=False
    # ~ try:
        # ~ return json.dumps(app.isardapi.get_domain(request.get_json(force=True)['pk'], human_size=hs, flatten=False))
    # ~ except:
        # ~ return json.dumps([])






   
# ~ @app.route('/chain', methods=['POST'])
# ~ @login_required
# ~ def chain():
    # ~ if request.method == 'POST':
        # ~ return json.dumps(app.isardapi.get_domain_backing_images(request.get_json(force=True)['id']))
    # ~ return False
           
        
        
