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
    remote_addr=request.headers['X-Forwarded-For'] if 'X-Forwarded-For' in request.headers else request.remote_addr
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
        # ~ remote_addr=request.headers['X-Forwarded-For'] if 'X-Forwarded-For' in request.headers else request.remote_addr
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
        return json.dumps(app.isardapi.get_domain(request.get_json(force=True)['pk'], human_size=hs))
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
        
@app.route('/desktops/template',methods=['POST'])
@login_required
@ownsid
def desktops_template():
    msg=True
    if request.method == 'POST':
        if float(app.isardapi.get_user_quotas(current_user.username)['tqp']) >= 100:
            flash('Quota for creating new templates is full','danger')
            return redirect(url_for('desktops'))
        #~ # if app.isardapi.is_domain_id_unique
        original=app.isardapi.get_domain(request.form['id'])
        domain_dict=app.isardapi.f.unflatten_dict(original)
        res=app.isardapi.new_tmpl_from_domain(current_user.username,
                                              request.form['name'],
                                              request.form['description'],
                                              request.form['kind'],
                                              domain_dict)
        if res is True:
            flash('Template creation queued, wait to complete','success')
            return redirect(url_for('desktops'))
        else:
            flash('Could not create template now','danger')
    return redirect(url_for('desktops'))

#~ @socketio.on('connect', namespace='/test')
#~ def test_connect():
    #~ print(current_user.username)
    #~ global thread
    #~ if thread is None:
        #~ thread = socketio.start_background_task(target=background_thread)
    #~ emit('my_response', {'data': 'Connected', 'count': 0})

#~ def background_thread():
    #~ """Example of how to send server generated events to clients."""
    #~ count = 0
    #~ while True:
        #~ socketio.sleep(10)
        #~ count += 1
        #~ socketio.emit('my_response',
                      #~ {'data': 'Server generated event', 'count': count},
                      #~ namespace='/test')

#~ @socketio.on('connect')
#~ def desktops_connect_handler():
    #~ if current_user.is_authenticated:
        #~ log.info('authenticated: '+current_user.username)
        #~ with app.app_context():
            #~ for c in r.table('domains').get_all(current_user.username, index='user').merge({"table": "domains"}).changes(include_initial=False).run(db.conn):
                #~ if c['new_val'] is not None:
                   #~ log.info('new event for user '+current_user.username+' desktop:'+c['new_val']['id'])
                   #~ emit('status_desktop',c['new_val'])
    #~ else:
        #~ log.info('not authenticated')
        #~ return False  # not allowed here

#~ @socketio.on('disconnect')
#~ def disconnect():
    #~ print("%s disconnected" % (current_user.username))
    
# ~ def desktops_stream():
        # ~ with app.app_context():
            # ~ for c in r.table('domains').get_all(current_user.username, index='user').merge({"table": "domains"}).changes(include_initial=False).run(db.conn):
                # ~ if c['new_val'] is not None:
                   # ~ print('new event for user '+current_user.username+' desktop:'+c['new_val']['id'])
                   # ~ emit('status_desktop',c['new_val'])

#~ @app.route('/stream/desktops')
#~ @login_required
#~ def sse_request():
        #~ return Response(event_stream(current_user.username), mimetype='text/event-stream')

#~ def event_stream(username):
        #~ with app.app_context():
            #~ #dom_started=set(['_jvinolas_asdf'])
            #~ dom_started=[]
            #~ for c in r.table('domains').get_all(username, index='user').merge({"table": "domains"}).changes(include_initial=False).union(
                #~ r.table('domains_status').get_all(r.args(dom_started)).merge({"table": "domains_status"}).changes(include_initial=False)).run(db.conn):
                #~ #get_all(username, index='user').filter({'kind': 'desktop'})
                #~ #r.table('domains_status').filter(lambda domain: r.table('domains').get_all(username, index='user').filter({'status':'Started'}))
                #~ #r.table('domains_status').get_all(r.args(list(dom_started)), index='name')
                #~ #r.table('domains_status').filter(lambda domain: r.table('domains').get_all(username, index='user').filter({'status':'Started'}))
                #~ print(list(r.table('domains_status').get_all(r.args(list(dom_started)), index='name').merge({"table": "domains_status"}).run(db.conn)))
                #~ if (c['new_val'] is not None and c['new_val']['table'] == 'domains') or (c['old_val'] is not None and c['old_val']['table'] == 'domains'):
                    #~ if c['new_val'] is None:
                        #~ yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('Deleted',time.time(),json.dumps(c['old_val']))
                        #~ continue
                    #~ if c['old_val'] is None:
                        #~ yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('New',time.time(),json.dumps(app.isardapi.f.flatten_dict(c['new_val'])))   
                        #~ continue             
                    #~ #if 'detail' not in c['new_val']: c['new_val']['detail']=''
                    #~ if c['old_val']['status']=='Starting' and c['new_val']['status']=='Started': 
                        #~ dom_started.append(c['new_val']['id'])
                    #~ yield 'retry: 2000\nevent: %s\nid: %d\ndata: %s\n\n' % ('Status',time.time(),json.dumps(app.isardapi.f.flatten_dict(c['new_val'])))
                #~ else:
                    #~ print('THIS IS A DOMAIN STATUS')
                    #~ print(c['new_val']['name'],c['new_val']['status']['cpu_usage'])

# ~ @app.route('/stream/disposable')
# ~ def sse_request_disposable():
    # ~ id = '_disposable_'+app.isardapi.parse_string(request.headers['X-Forwarded-For'] if 'X-Forwarded-For' in request.headers else request.remote_addr)
    # ~ return Response(event_disposable_stream(id), mimetype='text/event-stream')

# ~ def event_disposable_stream(id):
    # ~ with app.app_context():
        # ~ for c in r.table('domains').get(id).changes(include_initial=False).run(db.conn):
            # ~ if 'new_val' in c:
                # ~ if c['new_val']['status'] == 'Started':
                    # ~ yield 'retry: 2000\nevent: %s\nid: %d\ndata: %s\n\n' % ('Started',time.time(),json.dumps(c['new_val']))


# ~ @app.route('/stream/backend')
# ~ @login_required
# ~ def sse_request_backend():
        # ~ return Response(event_stream_backend(current_user.username, current_user.quota), mimetype='text/event-stream')

# ~ import random
# ~ def event_stream_backend(username,quota):
        # ~ yield 'retry: 2000\nevent: %s\nid: %d\ndata: %s\n\n' % ('Quota',time.time(),json.dumps(app.isardapi.get_user_quotas(username, quota)))
        # ~ with app.app_context():
            # ~ for c in r.table('domains').get_all(username, index='user').filter({'kind': 'desktop'}).changes(include_initial=False).run(db.conn):
                    # ~ yield 'retry: 2000\nevent: %s\nid: %d\ndata: %s\n\n' % ('Quota',time.time(),json.dumps(app.isardapi.get_user_quotas(username, quota)))
                    # ~ continue

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

## Helpers

# ~ def validCharacters(txt):
    # ~ import re, unicodedata, locale
    # ~ txt=txt.decode('utf-8')
    # ~ locale.setlocale(locale.LC_ALL, 'ca_ES')
    # ~ prog = re.compile("[-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$".decode('UTF-8'), re.L)
    # ~ if not prog.match(txt):
        # ~ return False
    # ~ else:
        # ~ return txt




           
        
        
