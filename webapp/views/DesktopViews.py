# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8
from flask import render_template, Response, request, redirect, url_for, stream_with_context, flash
from webapp import app
from flask_login import login_required, login_user, logout_user, current_user
import time
import json

from ..lib.log import *

import rethinkdb as r
from ..lib.flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

from .decorators import ownsid


from flask_socketio import SocketIO, send, emit
#~ socketio= SocketIO(app)
#~ Global socketio

@app.route('/domain_messages', methods=['POST'])
@login_required
@ownsid
def domain_messages():
    if request.method == 'POST':
        return json.dumps(app.isardapi.get_domain_last_messages(request.get_json(force=True)['id']))
    return False

@app.route('/domain_events', methods=['POST'])
@login_required
@ownsid
def domain_events():
    if request.method == 'POST':
        return json.dumps(app.isardapi.get_domain_last_events(request.get_json(force=True)['id']))
    return False
   
@app.route('/chain', methods=['POST'])
@login_required
def chain():
    if request.method == 'POST':
        return json.dumps(app.isardapi.get_domain_backing_images(request.get_json(force=True)['id']))
    return False

@app.route('/derivates/<id>', methods=['GET', 'POST'])
@login_required
def derivates(id):
    if request.method == 'POST':
        return json.dumps(app.isardapi.get_domain_derivates(request.get_json(force=True)['id']))
    return json.dumps(app.isardapi.get_domain_derivates(id))
      
@app.route('/desktops')
@login_required
def desktops():
    return render_template('pages/desktops.html', title="Desktops", nav="Desktops")

@app.route('/desktops/get/')
@app.route('/desktops/get/<kind>')
@login_required
def desktops_get(kind='username'):
    if kind=='username':
        return json.dumps(app.isardapi.get_user_domains(current_user.username)), 200, {'ContentType': 'application/json'}
    if kind=='category': 
        return json.dumps(app.isardapi.get_category_domains(current_user.category)), 200, {'ContentType': 'application/json'}
    if kind=='group':
        return json.dumps(app.isardapi.get_group_domains(current_user.group)), 200, {'ContentType': 'application/json'}
    return url_for('desktops')

@app.route('/desktops/download_viewer/<os>/<id>')
@login_required
@ownsid
def viewer_download(os,id):
    #~ if type == 'file':
    # ~ viewer=app.isardapi.get_viewer_ticket(id,os)
    try:
        extension,mimetype,consola=app.isardapi.get_viewer_ticket(id,os)
        return Response(consola, 
                    mimetype=mimetype,
                    headers={"Content-Disposition":"attachment;filename=consola."+extension})
    except Exception as e:
        print('Download viewer error:'+str(e))
        return Response('Error in viewer',mimetype='application/txt')
    #~ if type == 'xpi':
        #~ dict=app.isardapi.get_spice_xpi(id)
        #~ return json.dumps(dict), 200, {'ContentType:':'application/json'}

    #~ if type == 'html5':
        #~ dict=app.isardapi.get_domain_spice(id)
        #~ ##### Change this when engine opens ports accordingly (without tls)
        #~ if dict['port'] or True:
            ###dict['port'] = "5"+ dict['port']
            #~ dict['port'] = dict['port'] if dict['port'] else dict['tlsport']
            #~ dict['port'] = "5"+ dict['port']
            #~ return json.dumps(dict), 200, {'ContentType:':'application/json'}
        #~ else:
            #~ return json.dumps('HTML5 incompatible with TLS port.'), 500, {'ContentType':'application/json'}
                    #~ {'host':domain['viewer']['hostname'],
                    #~ 'kind':domain['hardware']['graphics']['type'],
                    #~ 'port':False,
                    #~ 'tlsport':domain['viewer']['tlsport'],
                    #~ 'ca':viewer['certificate'],
                    #~ 'domain':viewer['domain'],
                    #~ 'passwd':domain['viewer']['passwd']}
        
@app.route('/disposable/download_viewer/<os>/<id>')
def viewer_disposable_download(os,id):
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    if id.startswith('_disposable_'+remote_addr.replace('.','_')+'_'):
        extension,mimetype,consola=app.isardapi.get_viewer_ticket(id,os)
        return Response(consola, 
                        mimetype=mimetype,
                        headers={"Content-Disposition":"attachment;filename=consola."+extension})
                        
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


#~ from pprint import pprint
#~ @app.route('/desktops_add', methods=['POST'])
#~ @login_required
#~ def desktops_add():
    #~ res=True
    #~ if request.method == 'POST':
        #~ if float(app.isardapi.get_user_quotas(current_user.username)['dqp']) >= 100:
            #~ flash('Quota for creating new desktops is full','danger')
            #~ return redirect(url_for('desktops'))
        #~ create_dict=app.isardapi.f.unflatten_dict(request.form)
        #~ pprint(create_dict)
        #~ create_dict.pop('templateFilterGroup', None)
        #~ create_dict.pop('templateFilterCategory',None)
        #~ create_dict.pop('templateFilterUser',None)
        #~ create_dict['hypervisors_pools']=[create_dict['hypervisors_pools']]
        #~ create_dict['hardware']['boot_order']=[create_dict['hardware']['boot_order']]
        #~ create_dict['hardware']['graphics']=[create_dict['hardware']['graphics']]
        #~ create_dict['hardware']['videos']=[create_dict['hardware']['videos']]
        #~ create_dict['hardware']['interfaces']=[create_dict['hardware']['interfaces']]
        #~ create_dict['hardware']['memory']=int(create_dict['hardware']['memory'])*1024
        #~ res=app.isardapi.new_domain_from_tmpl(current_user.username, create_dict)

        #~ if res is True:
            #~ flash('Desktop '+create_dict['name']+' created.','success')
            #~ return redirect(url_for('desktops'))
        #~ else:
            #~ flash('Could not create desktop. Maybe you have one with the same name?','danger')
            #~ return redirect(url_for('desktops'))

# ~ @app.route('/desktops_add_disposable', methods=['POST'])
# ~ def desktops_add_disposable():
    # ~ res=True
    # ~ if request.method == 'POST':
        # ~ remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
        # ~ template=request.get_json(force=True)['pk']
        # ~ ## Checking permissions
        # ~ disposables = app.isardapi.show_disposable(remote_addr)
        # ~ print([d['id'] for d in disposables['disposables'] if d['id']==template])
        # ~ if disposables and len([d['id'] for d in disposables['disposables'] if d['id']==template]):
            # ~ # {'active': True,
             # ~ # 'description': 'prova',
             # ~ # 'disposables': [{'description': '',
                              # ~ #~ 'id': '_biblioteca1',
                              # ~ #~ 'name': 'biblioteca1'}],
             # ~ # 'id': 'taller',
             # ~ # 'name': 'taller',
             # ~ # 'nets': ['10.200.108.0/24']}



        
            # ~ app.isardapi.new_domain_disposable_from_tmpl(remote_addr,template)
        # ~ # res=app.isardapi.new_domain_from_tmpl(current_user.username, create_dict)
        # ~ else:
            # ~ res=False
        # ~ if res is True:
            # ~ flash('Disposable desktop created.','success')
            # ~ print('Created desktop')
            # ~ return json.dumps('Updated'), 200, {'ContentType':'application/json'}
        # ~ else:
            # ~ flash('Could not update.','danger')
            # ~ print('Failed creating desktop')
            # ~ return json.dumps('Could not update.'), 500, {'ContentType':'application/json'}
                        
@app.route('/hardware', methods=['GET'])
@login_required
def hardware():
    dict={}
    dict['nets']=app.isardapi.get_alloweds(current_user.username,'interfaces',pluck=['id','name','description'],order='name')
    #~ dict['disks']=app.isardapi.get_alloweds(current_user.username,'disks',pluck=['id','name','description'],order='name')
    dict['graphics']=app.isardapi.get_alloweds(current_user.username,'graphics',pluck=['id','name','description'],order='name')
    dict['videos']=app.isardapi.get_alloweds(current_user.username,'videos',pluck=['id','name','description'],order='name')
    dict['boots']=app.isardapi.get_alloweds(current_user.username,'boots',pluck=['id','name','description'],order='name')
    dict['hypervisors_pools']=app.isardapi.get_alloweds(current_user.username,'hypervisors_pools',pluck=['id','name','description'],order='name')
    dict['forced_hyps']=[]
    if current_user.role == 'admin':
        dict['forced_hyps']=app.adminapi.get_admin_table('hypervisors',['id','hostname','description','status'])
    dict['forced_hyps'].insert(0,{'id':'default','hostname':'Auto','description':'Hypervisor pool default'})
    dict['user']=app.isardapi.get_user(current_user.username)
    return json.dumps(dict)

@app.route('/domain_genealogy', methods=['POST'])
@login_required
@ownsid
def domain_genealogy():
    domain=app.isardapi.get_domain(request.get_json(force=True)['pk'], human_size=False)
    if 'disks_info' not in domain.keys():
        return json.dumps({'wasted':0,'free':0,'wasted_hs':0,'free_hs':0,'genealogy':[],'gen_ids':[]})
    gen=domain['disks_info']
    gen_human=app.isardapi.get_domain(request.get_json(force=True)['pk'], human_size=True)['disks_info']
    wasted=0
    try:
        for i,v in enumerate(gen):
            gen_human[i]['size_percentage']="%.0f" % round(gen[i]['actual-size']*100/gen[i]['virtual-size'],0),
            wasted+=gen[i]['actual-size']
        #~ gen_ids=[]
        #~ print('kind: '+domain['kind'])
        #~ if domain['kind'] !='desktop':
        gen_ids=app.isardapi.get_backing_ids(request.get_json(force=True)['pk'])
    except Exception as e:
        return json.dumps({'wasted':0,'free':0,'wasted_hs':0,'free_hs':0,'genealogy':[],'gen_ids':[]})
    return json.dumps({'wasted':wasted,'free':gen[0]['virtual-size']-wasted,'wasted_hs':app.isardapi.human_size(wasted),'free_hs':app.isardapi.human_size(gen[0]['virtual-size']-wasted),'genealogy':gen_human,'gen_ids':gen_ids})

@app.route('/domain_derivates', methods=['POST'])
@login_required
@ownsid
def domain_derivates():
    return json.dumps(app.isardapi.get_domain_derivates(request.get_json(force=True)['pk']))


@app.route('/domain', methods=['POST'])
@login_required
def domain():
    try:
        hs=request.get_json(force=True)['hs']
    except:
        hs=False
    try:
        return json.dumps(app.isardapi.get_domain(request.get_json(force=True)['pk'], human_size=hs, flatten=False))
    except:
        return json.dumps([])

# ~ @app.route('/userhardwarequota', methods=['POST'])
# ~ @login_required
# ~ def domain():
    # ~ try:
        # ~ hs=request.get_json(force=True)['hs']
    # ~ except:
        # ~ hs=False
    # ~ try:
        # ~ return json.dumps(app.isardapi.user_hardware_quota(current_user.username, human_size=hs))
    # ~ except:
        # ~ return json.dumps([])
        
        
@app.route('/domain/alloweds', methods=['POST'])
@login_required
def domain_alloweds():
    return json.dumps(app.isardapi.f.unflatten_dict(app.isardapi.get_domain(request.get_json(force=True)['pk']))['allowed'])

@app.route('/domain/alloweds/select2', methods=['POST'])
@login_required
def domain_alloweds_select2():
    allowed=request.get_json(force=True)['allowed']
    return json.dumps(app.isardapi.get_alloweds_select2(allowed))
        
#~ @app.route('/desktops/template',methods=['POST'])
#~ @login_required
#~ @ownsid
#~ def desktops_template():
    #~ msg=True
    #~ if request.method == 'POST':
        #~ if float(app.isardapi.get_user_quotas(current_user.username)['tqp']) >= 100:
            #~ flash('Quota for creating new templates is full','danger')
            #~ return redirect(url_for('desktops'))
        #~ original=app.isardapi.get_domain(request.form['id'])
        #~ domain_dict=app.isardapi.f.unflatten_dict(original)
        #~ res=app.isardapi.new_tmpl_from_domain(current_user.username,
                                              #~ request.form['name'],
                                              #~ request.form['description'],
                                              #~ request.form['kind'],
                                              #~ domain_dict)
        #~ if res is True:
            #~ flash('Template creation queued, wait to complete','success')
            #~ return redirect(url_for('desktops'))
        #~ else:
            #~ flash('Could not create template now','danger')
    #~ return redirect(url_for('desktops'))


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

@app.route('/desktops/getAllTemplates', methods=['GET'])
@login_required
def getAllTemplates():
    custom_filter={}
    return Response(json.dumps(app.isardapi.get_all_alloweds_domains(current_user.username)), mimetype='application/json')


@app.route('/desktops/getDistinc/<field>/<kind>', methods=['GET'])
@login_required
def getDistinct(field,kind):
    #~ if kind=='user_template':
        #~ categories=app.isardapi.get_distinc_field(current_user.username, field, kind)
    #~ else:
    categories=app.isardapi.get_distinc_field(current_user.username, field, kind)
    return Response(json.dumps(categories), mimetype='application/json')
    #~ return Response(json.dumps(app.isardapi.get_alloweds(current_user.username,'domains')), mimetype='application/json')

import json
@app.route('/desktops/templateUpdate/<id>', methods=['GET'])
@login_required
def templateUpdate(id):
    hardware=app.isardapi.get_domain(id)
    return Response(json.dumps(hardware),  mimetype='application/json')





           
        
        
