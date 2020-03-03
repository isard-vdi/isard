# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
from flask import render_template, redirect, request, flash, url_for, send_from_directory
#~ from webapp import app
#~ from flask_login import login_required, login_user, logout_user, current_user

#~ from ..auth.authentication import *   
#~ from ..lib.log import *                       

import sys, json, requests, os
public_key='$2b$12$LA4uosV80.jkE430c8.wsOI.xIjQ0om7mpQZ0w/G.atH4/83ySTGW'

import rethinkdb as r
import time
import logging as wlog
LOG_LEVEL='INFO'
LOG_FORMAT='%(asctime)s - WIZARD - %(levelname)s: %(message)s'
LOG_DATE_FORMAT='%Y/%m/%d %H:%M:%S'
LOG_LEVEL_NUM = wlog.getLevelName(LOG_LEVEL)
wlog.basicConfig(format=LOG_FORMAT,datefmt=LOG_DATE_FORMAT,level=LOG_LEVEL_NUM)


'''
PASSWORDS MANAGER
'''
import bcrypt,string,random
class Password(object):
        def __init__(self):
            None

        def valid(self,plain_password,enc_password):
            return bcrypt.checkpw(plain_password.encode('utf-8'), enc_password.encode('utf-8'))
                
        def encrypt(self,plain_password):
            return bcrypt.hashpw(plain_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        def generate_human(self,length=6):
            chars = string.ascii_letters + string.digits + '!@#$*'
            rnd = random.SystemRandom()
            return ''.join(rnd.choice(chars) for i in range(length))
            
        

class Wizard():
    def __init__(self):
        self.register_isard=False
        self.code=False
        self.url='http://www.isardvdi.com:5050'
        
        self.doWizard=True if self.first_start() else False
        if self.doWizard: # WIZARD WAS FORCED BY DELETING install/x.wizard file
            wlog.warning('Starting initial configuration wizard')
            if not self.valid_js(first=True):
                try:
                    #from pynpm import YarnPackage
                    #pkg = YarnPackage(os.path.join(os.path.dirname(__file__).rsplit('/',2)[0]+'/install/package.json'))
                    #res = pkg.install()
                    res = True
                except:
                    res=False
                if res is False:
                    wlog.error('Javascript and CSS not installed!')
                    wlog.error(' Please install yarn: https://yarnpkg.com/lang/en/docs/install')
                    wlog.error(' and run yarn from install folder before starting again.')                
                    exit(1)
            self.run_server()
            
        else: # WIZARD NOT FORCED. SOMETHING IS NOT GOING AS EXPECTED WITH DATABASE?
            wait_seconds=3
            while wait_seconds > 0:
                if not self.valid_rethinkdb():
                    time.sleep(1)
                    wait_seconds-=1
                else:
                    wait_seconds=0
            if not self.valid_rethinkdb():
                wlog.error('Can not connect to rethinkdb database! Is it running?')
                exit(1)
            else:
                if not self.valid_isard_database():
                    wlog.error('Database isard not found!')
                    wlog.error('If you need to recreate isard database you should activate wizard again:')
                    wlog.error('   REMOVE /opt/isard/database/wizard/wizard-disabled file  (rm /opt/isard/database/wizard/wizard-disabled) and start isard again')
                    exit(1)

    def run_server(self):
        from flask import Flask
        self.wapp = Flask(__name__)
        self.wizard_routes()
        wlog.info('ISARD WEBCONFIG STARTED: Access on http://localhost:5000 or https://localhost on dockers.')
        self.wapp.run(host='0.0.0.0', port=5000, debug=False)        
                
    def shutdown_server(self):
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            raise RuntimeError('Not running with the Werkzeug Server')
        func()
        wlog.info('Stopping wizard flask server')

        
    def first_start(self):
        path='./install/wizard/wizard-disabled'
        return True if not os.path.exists(path) else False
            
    def done_start(self):
        path='./install/wizard/wizard-disabled'
        os.mknod(path)


    '''
    GET UPDATES
    '''
    def get_updates_list(self):
        kinds=['media','domains','builders']
        dict={}
        for k in kinds:
            dict[k]=self.get_updates_new_kind(k,'admin')
        return dict

    def insert_updates_demo(self):
        updates=['zxspectrum','tetros']
        domains=self.get_updates_new_kind('domains','admin')
        for dom in domains:
            for u in updates:
                if str('downloaded_'+u) == dom['id']:
                    missing_resources=self.get_missing_resources(dom,'admin')
                    for k,v in missing_resources.items():
                        for resource in v:
                            r.db('isard').table(k).insert(v).run()
                    self.insert_update('domains',[dom])
                    wlog.info('New download: '+u)

        updates=['win7Virtio','win10Virtio','centos7.0','debian9','fedora26','ubuntu17.04','ubuntu16.10','winxp']
        virt_installs=self.get_updates_new_kind('virt_install','admin')
        for vi in virt_installs:
            for u in updates:
                if u == vi['id']:
                    r.db('isard').table('virt_install').insert(vi).run()
                    wlog.info('New virt_install: '+u)                    
        # Useful default media with drivers for Microsfot
        #~ medias=self.get_updates_new_kind('media','admin')
        #~ for media in medias:
            #~ if 'default-virtio-iso' in media.keys():
                #~ self.insert_update('media',[media])
                #~ wlog.info('New download: '+u)
        return True
        
    def insert_update(self,kind,data):
        username='admin'
        userpath='admin/admin/admin/'
        if kind == 'domains': 
            for d in data:
                d['id']='_'+username+'_'+d['id']
                # ~ d['percentage']=0
                d['status']='DownloadStarting'
                d['detail']=''
                d['hypervisors_pools']=d['create_dict']['hypervisors_pools']
                d.update({  'category': 'admin',
                            'group': 'admin',
                            'user': 'admin'})
                for disk in d['create_dict']['hardware']['disks']:
                    disk['file']=userpath+disk['file']
        elif kind == 'media':
            for d in data:
                # ~ if 'path' in d.keys():
                    d.update({  'category': 'admin',
                            'group': 'admin',
                            'user': 'admin'})
                    # ~ d['percentage']=0
                    d['status']='DownloadStarting'                    
                    d['path']=userpath+d['url-isard']
        r.db('isard').table(kind).insert(data).run()
            
    def get_updates_new_kind(self,kind,username):
        web=self.get_updates_kind(kind=kind)
        dbb=list(r.db('isard').table(kind).run())
        result=[]
        for w in web:
            found=False
            for d in dbb:
                if kind == 'domains':
                    if d['id']=='_'+username+'_'+w['id']:
                        found=True
                        continue
                else:
                    if d['id']==w['id']:
                        found=True
                        continue
            if not found: result.append(w)
        return result
        #~ return [i for i in web for j in dbb if i['id']==j['id']]

        
    def get_updates_kind(self,kind):
        try:
            req= requests.post(self.url+'/get/'+kind+'/list', headers={'Authorization':str(self.code)},allow_redirects=False, verify=False, timeout=3)
            if req.status_code==200:
                return req.json()
                #~ return True
            else:
                wlog.error('Error response code: '+str(req.status_code)+'\nDetail: '+req.json())
        except Exception as e:
            wlog.error("Error contacting.\n"+str(e))
        return False

    def get_missing_resources(self,domain,username):
        missing_resources={'videos':[]}
        
        dom_videos=domain['create_dict']['hardware']['videos']
        sys_videos=list(r.db('isard').table('videos').pluck('id').run())
        sys_videos=[sv['id'] for sv in sys_videos]
        for v in dom_videos:
            if v not in sys_videos:
                resource=self.getNewKindId('videos',username,v)
                if resource is not False:
                    missing_resources['videos'].append(resource)
        ## graphics and interfaces missing
        return missing_resources

    def is_registered(self):
        if self.code is False:
            return False
        return True
        
    def render_updates(self,dict):
        html='<div style="overflow-y: auto; height:360px"><h4><ul>'
        for k in dict.keys():
            html+='<li>'+k+' ('+str(len(dict[k]))+'):<ul>'
            for n in dict[k]:
                html+='<li>'+n['name']+'</li>'
            html+='</ul></li>'
        html+='</ul></h4></div>'
        return html
    '''
    CHECK VALID ITEMS
    '''
    def valid_js(self,first=False,path='bower_components/gentelella'):
        ## It is a docker, so we assume containers have created bower
        ##  (following code will fail in docker as yarn created a 
        ##   symbolic link that returns false in os.path check...)
        # ~ from ..lib.load_config import load_config
        # ~ dict=load_config()   
        # ~ if dict: 
            # ~ if 'isard-hypervisor' in dict['DEFAULT_HYPERVISORS'].keys(): 
                # ~ return True 
        # ~ else:
            # ~ return False
        
        if first:
            return os.path.exists(os.path.join(os.path.dirname(__file__).rsplit('/',1)[0]+'/'+path))
        return os.path.exists(os.path.join(self.wapp.root_path+'/../',path))
        
    def valid_config_file(self):
        path='./isard.conf'
        return False if not os.path.exists(path) else True
        
    def valid_config_syntax(self):
        from ..lib.load_config import load_config
        return True if load_config() else False
        
    def valid_rethinkdb(self):
        try:
            from ..lib.load_config import load_config
            dict=load_config()
            r.connect(  host=dict['RETHINKDB_HOST'], 
                        port=dict['RETHINKDB_PORT']).repl()
            return True
        except Exception as e:
            wlog.error('Rethinkdb server not found. Is it running? '+str(e))
            #~ wlog.error(e)
            return False

    def valid_isard_database(self):        
        try:
            if 'isard' in r.db_list().run(): 
                r.db('isard').wait(wait_for='all_replicas_ready').run()
            time.sleep(5)
            resources=r.db('isard').table('config').get(1).pluck('resources').run()['resources']
            self.code=resources['code']
            self.url=resources['url']
            # ~ if 'isard' in r.db_list().run(): 
                # ~ from ..config.populate import Populate
                # ~ dict=self.register_isard_updates()
                # ~ p=Populate(dict) 
                ## Ideally we should inform user that some tables will be deleted and others created.
                ## Maybe ask for a backup?
                ## No invasive
                # ~ p.check_integrity(commit=True)
                # if self.register_isard_updates():
                #     self.insert_updates_demo()
                # ~ return True
            # ~ else:
                # ~ return False
            return True
        except Exception as e:
            wlog.error(str(e))
            return False

    def register_isard_updates(self):
        dict={'resources':{'url':self.url,'code':self.code}}
        if not self.register_isard:
            return dict
        else:
            # USER WANTS TO REGISTER ISARD
            # ~ try:
                # ~ cfg=r.table('config').get(1).pluck('resources').run()
            # ~ except Exception as e:
                # ~ return False
            # ~ if 'resources' in cfg.keys():
                # ~ self.url=cfg['resources']['url']
                # ~ self.code=cfg['resources']['code']
            if self.code is False:
                # ~ if self.url is False: self.url='http://www.isardvdi.com:5050'
                try:
                    req= requests.post(self.url+'/register' ,allow_redirects=False, verify=False, timeout=3)
                    if req.status_code==200:
                        self.code=req.json()
                        # ~ r.table('config').get(1).update({'resources':{'url':self.url,'code':req.json()}}).run()
                        dict={'resources':{'url':self.url,'code':self.code}}
                        wlog.warning('Isard app registered')
                        return dict
                    else:
                        wlog.info('Isard app registering error response code: '+str(req.status_code)+'\nDetail: '+r.json())
                        return dict
                except Exception as e:
                    wlog.warning("Error contacting.\n"+str(e))
                    return dict
        return dict
                        
    def valid_password(self):
        try:
            pw=Password()
            usr = r.db('isard').table('users').get('admin').run()
            if usr is None:
                usr = [{'id': 'admin',
                           'name': 'Administrator',
                           'kind': 'local',
                           'active': True,
                           'accessed': time.time(),
                           'username': 'admin',
                           'password': pw.encrypt('isard'),
                           'role': 'admin',
                           'category': 'admin',
                           'group': 'admin',
                           'mail': 'admin@isard.io',
                           'quota': {'domains': {'desktops': 99,
                                                 'desktops_disk_max': 999999999,  # 1TB
                                                 'templates': 99,
                                                 'templates_disk_max': 999999999,
                                                 'running': 99,
                                                 'isos': 99,
                                                 'isos_disk_max': 999999999},
                                     'hardware': {'vcpus': 8,
                                                  'memory': 20000000}},  # 10GB
                           }]
                r.db('isard').table('users').insert(usr, conflict='update').run()
                wlog.info('password must be changed')
                return False # Password must be changed so we return false
            if pw.valid('isard',usr['password']):
                # Password is isard
                return False
            # Passwd is not isard
            return True
        except Exception as e:
            # ~ exc_type, exc_obj, exc_tb = sys.exc_info()
            # ~ fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            # ~ wlog.error(exc_type, fname, exc_tb.tb_lineno)
            # ~ wlog.error(e)
            return False

    def valid_engine(self):
        from ..lib.load_config import load_config
        dict=load_config()['DEFAULT_HYPERVISORS']    
        valid_engine=self.valid_server('isard-engine:5555' if 'isard-hypervisor' in dict.keys() else 'localhost:5555')
        # ~ if valid_engine:
            # ~ try:
                # ~ status = r.db('isard').table('hypervisors_pools').get('default').pluck('download_changes').run()['download_changes']
                # ~ if status != 'Started': return False
            # ~ except Exception as e:
                # ~ print(e)
                # ~ return False
        if valid_engine:
            if 'isard-hypervisor' in dict.keys():
                url='http://isard-engine'
                web_port=5555
            else:
                url='http://localhost'
                web_port=5555                
            r.db('isard').table('config').get(1).update({'engine':{'api':{'url':url,'web_port':web_port,'token':'fosdem'}}}).run()
            
        return valid_engine

    def valid_hypervisor(self,remote_addr=False):
        try:
            if len(list(r.db('isard').table('hypervisors').filter({'status':'Online'}).pluck('status').run())) > 0:
                # ~ if remote_addr is not False:
                    # ~ self.update_hypervisor_viewer(remote_addr)
                self.callfor_updates_demo()
                return True
            return False
        except Exception as e:
            wlog.error(e)
            return False

    def hypervisor_detail(self,remote_addr=False):
        try:
            return r.db('isard').table('hypervisors').get('isard-hypervisor').pluck('detail').run()['detail']
        except:
            return ''
            
    def update_hypervisor_viewer(self,remote_addr):
        try:
            r.db('isard').table('config').get(1).update({'engine':{'grafana':{'url':'http://'+str(remote_addr)}}}).run()
            if r.db('isard').table('hypervisors').get('isard-hypervisor').update({'viewer_hostname':remote_addr}).run() is not None:
                return True
            return False
        except Exception as e:
            return False
            
    def valid_server(self,server=False):
        if server is False: 
            server='isardvdi.com'
        import http.client as httplib
        conn = httplib.HTTPConnection(server, timeout=5)
        try:
            conn.request("HEAD", "/")
            conn.close()
            return True
        except Exception as e:
            conn.close()
            return False        

    def callfor_updates_demo(self):
        # ~ if self.url is not False:
            # ~ wlog.warning('self.url='+str(self.url))
        server=self.url.split('//')[1]
        # ~ else:
            # ~ server='isardvdi.com'
        if not self.valid_server(server): return False
        # ~ import http.client as httplib
        # ~ conn = httplib.HTTPConnection(server, timeout=5)
        try:
            # ~ conn.request("HEAD", "/")
            # ~ conn.close()
            # ~ if self.register_isard_updates():
            self.insert_updates_demo()
            return True
        except Exception as e:
            # ~ conn.close()
            wlog.warning('Could not register.')
            return False  
        
    def create_isard_database(self):
        from ..config.populate import Populate
        dict=self.register_isard_updates()
        p=Populate(dict)
        if p.database():
            # ~ p.defaults()
            p.check_integrity(commit=True)
            
            return True
        return False
        
    def check_all(self):
        from ..lib.load_config import load_config
        dict=load_config()
        if dict:
            res  = {'yarn':self.valid_js(),
                    'config':True,
                    'config_stx':True,
                    'internet': True, #self.valid_server('isardvdi.com'),
                    'rethinkdb':self.valid_rethinkdb(),
                    'isard_db':self.valid_isard_database(),
                    'passwd':self.valid_password(),
                    'docker':True if 'isard-hypervisor' in dict['DEFAULT_HYPERVISORS'].keys() else False,
                    'hyper':self.valid_hypervisor() if self.valid_isard_database() else False,
                    'engine':self.valid_server('isard-engine:5555' if 'isard-hypervisor' in dict['DEFAULT_HYPERVISORS'].keys() else 'localhost:5555')}  
        else:
            res =  {'yarn':self.valid_js(),
                    'config':self.valid_config_file(),
                    'config_stx':self.valid_config_syntax(),
                    'internet': True, #self.valid_server('isardvdi.com'),
                    'rethinkdb':self.valid_rethinkdb(),
                    'isard_db':self.valid_isard_database(),
                    'passwd':self.valid_password(),
                    'docker':False,
                    'hyper':self.valid_hypervisor(),
                    'engine':False}
        res['continue']=res['yarn'] and res['config_stx'] and res['isard_db'] and res['engine']
        return res

    def check_steps(self):
        res = self.check_all()
        errors=[]
        if not res['config'] or not res['config_stx']: 
            errors.append({'stepnum':1,'iserror':True})
        else:
            errors.append({'stepnum':2,'iserror':False})
            
        if not res['rethinkdb'] or not res['isard_db']: 
            errors.append({'stepnum':2,'iserror':True})
        else:
            errors.append({'stepnum':3,'iserror':False})
            
        if not res['passwd']: 
            errors.append({'stepnum':3,'iserror':True})
        else:
            errors.append({'stepnum':3,'iserror':False})
            
        # ~ if not res['internet']: 
            # ~ errors.append({'stepnum':4,'iserror':True})
        # ~ else:
            # ~ errors.append({'stepnum':4,'iserror':False})

        if not res['engine']: 
            errors.append({'stepnum':4,'iserror':True})
        else:
            errors.append({'stepnum':4,'iserror':False})
        return errors
            
        if not res['hyper']: 
            errors.append({'stepnum':5,'iserror':True})
        else:
            errors.append({'stepnum':5,'iserror':False})
            

    
    def wizard_routes(self):
            # Static
            @self.wapp.route('/build/<path:path>')
            def send_build(path):
                return send_from_directory(os.path.join(self.wapp.root_path+'/../', 'bower_components/gentelella/build'), path)
    
            @self.wapp.route('/vendors/<path:path>')
            def send_vendors(path):
                return send_from_directory(os.path.join(self.wapp.root_path+'/../', 'bower_components/gentelella/vendors'), path)

            @self.wapp.route('/img/<path:path>')
            def send_img(path):
                return send_from_directory(os.path.join(self.wapp.root_path+'/../', 'static/img'), path)
                
            @self.wapp.route('/errors', methods=['POST'])
            def errors():
                return json.dumps(self.check_steps())
                
            @self.wapp.route('/', methods=['GET'])
            def base():
                chk=self.check_all()
                msg=''
                if not chk['yarn']:
                    msg='Javascript and CSS libraries not found. Please install it running yarn on install folder.'
                    return render_template('missing_yarn.html',chk=chk, msg=msg.split('\n'))
                return render_template('wizard_main.html',chk=chk, msg=msg.split('\n'))
    
            # Flask routes
            @self.wapp.route('/register', methods=['POST'])
            def wizard_register():
                if request.method == 'POST':
                    reg=request.get_json(force=True)   
                    if reg: self.register_isard=True
                    return json.dumps(True)
                                
            @self.wapp.route('/create_config', methods=['POST'])
            def wizard_createconfig():
                if request.method == 'POST':
                    cfg=request.get_json(force=True)               
                    import shutil
                    shutil.copyfile(cfg, 'isard.conf')
                    return json.dumps(True)
                
            @self.wapp.route('/create_db', methods=['POST'])
            def wizard_createdb():
                return json.dumps(self.create_isard_database())

            @self.wapp.route('/passwd', methods=['GET','POST'])
            def wizard_passwd():
                if request.method == 'POST':
                    pw=Password()
                    r.db('isard').table('users').get('admin').update({'password':pw.encrypt(request.get_json(force=True))}).run()
                    return json.dumps(True)
                return render_template('wizard_pwd.html')

            @self.wapp.route('/hypervisor_address', methods=['GET','POST'])
            def wizard_hypervisor_address():
                print('UPDATING HYPERVISOR ADDRESS TO:'+str(request.get_json(force=True)))
                if self.update_hypervisor_viewer(request.get_json(force=True)):
                    return json.dumps(True)
                return json.dumps(False)
                # ~ if request.method == 'POST':
                    # ~ r.db('isard').table('users').get('admin').update({'password':pw.encrypt(request.get_json(force=True))}).run()
                    # ~ return json.dumps(True)
                # ~ return render_template('wizard_pwd.html')
                
            @self.wapp.route('/shutdown', methods=['POST'])
            def wizard_shutdown():
                # This shutdowns wizard flask server and allows for main isard src to continue loading.
                self.done_start()
                self.shutdown_server()
                self.doWizard=False
                # ~ time.sleep(10)
                # ~ return redirect('/')
                return json.dumps(True)

            @self.wapp.route('/validate/<step>', methods=['POST'])
            def wizard_validate_step(step):
                if request.method == 'POST':
                    if step == '1':
                        return json.dumps(self.valid_config_file() and self.valid_config_syntax())
                    if step == '2':
                        return json.dumps(self.valid_rethinkdb() and self.valid_isard_database())
                    if step == '3':
                        return json.dumps(self.valid_password())
                    # ~ if step == '4':
                        # ~ return json.dumps(self.valid_server('isardvdi.com'))
                    if step == '4':
                        return json.dumps(self.valid_engine())                         
                    if step == '5':
                        # ~ return json.dumps(self.valid_hypervisor() if self.valid_isard_database() else False) 
                        return json.dumps(self.valid_hypervisor())                                       
                    if step == '6':
                        return json.dumps(self.valid_server('isardvdi.com')) 
                                                                                                                    
            @self.wapp.route('/content', methods=['POST'])
            def wizard_content():
                global html
                remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
                if request.method == 'POST':
                    step=request.form['step_number']
                    if step == '1':
                        if not self.valid_config_file():
                            return html[1]['noconfig']
                        elif not self.valid_config_syntax():
                            return html[1]['nosyntax']
                        return html[1]['ok']
                    if step == '2':
                        db=self.valid_rethinkdb()
                        isard=self.valid_isard_database()
                        if not db:
                            return html[2]['noservice']
                        if not isard:
                            return html[2]['nodatabase']
                        return html[2]['ok']
                    if step == '3':
                        if not self.valid_password():
                            return html[3]['ko']
                        return html[3]['ok']
                    # ~ if step == '4':
                        # ~ if not self.valid_server('isardvdi.com'):
                            # ~ return html[4]['ko']
                        # ~ return html[4]['ok']                      
                    if step == '4':
                        if not self.valid_engine():
                            return html[4]['ko']
                        return html[4]['ok']                                                  
                    if step == '5':
                        if not (self.valid_hypervisor() if self.valid_isard_database() else False):
                            return html[5]['ko'] % (self.hypervisor_detail())
                        return html[5]['ok']                          
                    if step == '6':
                        if not self.valid_server('isardvdi.com'):
                            return html[6]['noservice']
                        if self.is_registered() is False:
                            return html[6]['noregister']
                        try:
                            updates=self.render_updates(self.get_updates_list())
                            return html[6]['ok'] % (updates)
                        except:
                            return html[6]['noregister']


'''
WIZARD STEPS DESCRIPTIONS
'''
                    
html={}                    
html[1]={'ok': '''   <h2 class="StepTitle">Step 1. Configuration</h2> 
                    <section>
                       <div class="container">
                          <div class="row">
                             <div class="col-md-2">
                                <div class="text-center"><i class="fa fa-check fa-4x" aria-hidden="true" style="color:green"></i></div>
                             </div>
                             <div class="col-md-10">
                                <h3 style="color:darkgreen">Configuration file <b>isard.conf</b> found on root installation.</h3>
                             </div>                             
                          </div><!--end row-->
                          <div class="row">
                             <div class="col-md-2">
                                <div class="text-center"><i class="fa fa-check fa-4x" aria-hidden="true" style="color:green"></i></div>
                             </div>
                             <div class="col-md-10">
                                <h3 style="color:darkgreen">Configuration file <b>isard.conf</b> has correct syntax.</h3>
                             </div>                             
                          </div><!--end row-->
                          <div class="row">
                            <div class="col-md-12">
                                <h2 align="center" style="color:green"><b>You can continue to next step...</b></h2>
                            </div>
                          </div>
                       </div><!--end container-->
                    </section> ''',
        'noconfig': '''   <h2 class="StepTitle">Step 1. Configuration</h2> 
                    <section>
                       <div class="container">
                          <div class="row">
                             <div class="col-md-2">
                                <div class="text-center"><i class="fa fa-times fa-4x" aria-hidden="true" style="color:red"></i></div>
                             </div>
                             <div class="col-md-10">
                                <h3 style="color:darkred">Configuration file <b>isard.conf</b> not found on root installation.</h3>
                             </div>                             
                          </div><!--end row-->
                          <a href="javascript:void(0);" onclick="$('#wizard').smartWizard('goToStep', 1);"><button id="populate" type="button" class="btn btn-success">Check again</button></a>
                          <hr><br><br>
                          <div class="row">
                            <div class="col-md-12">
                                <p>Please copy a default config install file as isard.conf:</p>
                                <ul>
                                    <li>isard.conf.default <a href="javascript:void(0);" onclick="createCONFIG('isard.conf.default');"><button id="populate" type="button" class="btn btn-warning">Use default config</button></a></li>
                                    <li>isard.conf.docker  <a href="javascript:void(0);" onclick="createCONFIG('isard.conf.docker');"><button id="populate" type="button" class="btn btn-warning">Use docker config</button></a></li>
                                </ul>
                            </div>
                          </div>
                       </div><!--end container-->
                    </section> ''',
        'nosyntax': '''   <h2 class="StepTitle">Step 1. Configuration</h2> 
                    <section>
                       <div class="container">
                          <div class="row">
                             <div class="col-md-2">
                                <div class="text-center"><i class="fa fa-check fa-4x" aria-hidden="true" style="color:green"></i></div>
                             </div>
                             <div class="col-md-10">
                                <h3 style="color:darkgreen">Configuration file <b>isard.conf</b> found on root installation.</h3>
                             </div>                             
                          </div><!--end row-->
                          <div class="row">
                             <div class="col-md-2">
                                <div class="text-center"><i class="fa fa-times fa-4x" aria-hidden="true" style="color:red"></i></div>
                             </div>
                             <div class="col-md-10">
                                <h3 style="color:darkred">Configuration file <b>isard.conf</b> hasn't got a correct syntax.</h3>
                             </div>                             
                          </div><!--end row-->
                          <a href="javascript:void(0);" onclick="$('#wizard').smartWizard('goToStep', 1);"><button id="populate" type="button" class="btn btn-success">Check again</button></a>
                          <hr><br><br>
                          <div class="row">
                            <div class="col-md-12">
                                <p>Please check your <b>isard.conf</b> file syntax!</p>
                                <p>You can check for correct syntax on default configuration files:</p>
                                <ul>
                                    <li>isard.conf.default <a href="javascript:void(0);" onclick="createCONFIG('isard.conf.default');"><button id="populate" type="button" class="btn btn-warning">Use default config</button></a></li>
                                    <li>isard.conf.docker  <a href="javascript:void(0);" onclick="createCONFIG('isard.conf.docker');"><button id="populate" type="button" class="btn btn-warning">Use docker config</button></a></li>

                                </ul>
                            </div>
                          </div>
                       </div><!--end container-->
                    </section> '''}

html[2]={'ok':'''   <h2 class="StepTitle">Step 2. Rethinkdb database service and isard database.</h2> 
                    <section>
                       <div class="container">
                          <div class="row">
                             <div class="col-md-2">
                                <div class="text-center"><i class="fa fa-check fa-4x" aria-hidden="true" style="color:green"></i></div>
                             </div>
                             <div class="col-md-10">
                                <h3 style="color:darkgreen">Rethinkdb database service found.</h3>
                             </div>                             
                          </div><!--end row-->
                          <div class="row">
                             <div class="col-md-2">
                                <div class="text-center"><i class="fa fa-check fa-4x" aria-hidden="true" style="color:green"></i></div>
                             </div>
                             <div class="col-md-10">
                                <h3 style="color:darkgreen">Database isard found.</h3>
                             </div>                             
                          </div><!--end row-->
                          <div class="row">
                            <div class="col-md-12">
                                <h2 align="center" style="color:green"><b>You can continue to next step...</b></h2>
                            </div>
                          </div>
                       </div><!--end container-->
                    </section> ''',
        'noservice': '''   <h2 class="StepTitle">Step 2. Rethinkdb database service and isard database.</h2> 
                    <section>
                       <div class="container">
                          <div class="row">
                             <div class="col-md-2">
                                <div class="text-center"><i class="fa fa-times fa-4x" aria-hidden="true" style="color:red"></i></div>
                             </div>
                             <div class="col-md-10">
                                <h3 style="color:darkred">Rethinkdb service not found.</h3>
                             </div>                             
                          </div><!--end row-->
                          <hr><br><br>
                          <div class="row">
                            <div class="col-md-12">
                                <p>Please check database parameters in isard.conf file and Rethinkdb service.</p>
                                <a href="javascript:void(0);" onclick="$('#wizard').smartWizard('goToStep', 2);"><button id="populate" type="button" class="btn btn-success">Check again</button></a>
                            </div>
                          </div>
                       </div><!--end container-->
                    </section> ''',
        'nodatabase': '''   <h2 class="StepTitle">Step 2. Rethinkdb database service and isard database.</h2> 
                    <section>
                       <div class="container">
                          <div class="row">
                             <div class="col-md-2">
                                <div class="text-center"><i class="fa fa-check fa-4x" aria-hidden="true" style="color:green"></i></div>
                             </div>
                             <div class="col-md-10">
                                <h3 style="color:darkgreen">Rethinkdb database service found.</h3>
                             </div>                             
                          </div><!--end row-->
                          <div class="row">
                             <div class="col-md-2">
                                <div class="text-center"><i class="fa fa-times fa-4x" aria-hidden="true" style="color:red"></i></div>
                             </div>
                             <div class="col-md-10">
                                <h3 style="color:darkred"> Database isard not found.</h3>
                             </div>                             
                          </div><!--end row-->
                          <hr><br><br>
                          <div class="row">
                            <div id="populate-div" class="col-md-12">
                                <p>You need to populate an initial isard database.</p>
                                <a href="javascript:void(0);" onclick="$('#wizard').smartWizard('goToStep', 2);"><button id="populate" type="button" class="btn btn-success">Check again</button></a>
                                <a href="javascript:void(0);" onclick="createDB();"><button id="populate" type="button" class="btn btn-warning">Populate isard database!</button></a>
                            </div>
                            <div id="populating-div" class="col-md-12" style="display:none">
                                <p><i class='fa fa-cog fa-spin fa-3x fa-fw'></i>Creating isard tables... (It can take up to 1 minute)<p>
                            </div>  
                          </div>
                       </div><!--end container-->
                    </section> '''}
                                
html[3]={'ok':'''   <h2 class="StepTitle">Step 3. Change default admin password</h2> 
                    <section>
                       <div class="container">
                          <div class="row">
                             <div class="col-md-2">
                                <div class="text-center"><i class="fa fa-check fa-4x" aria-hidden="true" style="color:green"></i></div>
                             </div>
                             <div class="col-md-10">
                                <h3 style="color:darkgreen">Default user <b>admin</b> has an updated password. You can continue.</h3>
                             </div>                             
                          </div><!--end row-->
                          <hr><br><br>
                          <div class="row">
                             <div class="col-md-12">
                                <p>In case you want to update the actual password <a data-toggle="modal" href="#passwdModal">click here</a></p>
                             </div>                             
                          </div><!--end row-->
                       </div><!--end container-->
                    </section> ''',
        'ko':'''   <h2 class="StepTitle">Step 3. Change default admin password</h2> 
                    <section>
                       <div class="container">
                          <div class="row">
                             <div class="col-md-2">
                                <div class="text-center"><i class="fa fa-times fa-4x" aria-hidden="true" style="color:red"></i></div>
                             </div>
                             <div class="col-md-10">
                                <h3 style="color:darkred">Default user <b>admin</b> needs a new password.</h3>
                             </div>                             
                          </div><!--end row-->
                          <hr><br><br>
                          <div class="row">
                             <div class="col-md-12">
                                <button type="button" data-toggle="modal" data-target="#passwdModal" class="btn btn-warning">Change password</button>
                                <a href="javascript:void(0);" onclick="$('#wizard').smartWizard('goToStep', 3);"><button  type="button" class="btn btn-success">Check again</button></a>
                             </div>                             
                          </div><!--end row-->
                       </div><!--end container-->
                    </section> '''}

# ~ html[4]={'ok':'''   <h2 class="StepTitle">Step 4. Internet connection</h2> 
                    # ~ <section>
                       # ~ <div class="container">
                          # ~ <div class="row">
                             # ~ <div class="col-md-2">
                                # ~ <div class="text-center"><i class="fa fa-check fa-4x" aria-hidden="true" style="color:green"></i></div>
                             # ~ </div>
                             # ~ <div class="col-md-10">
                                # ~ <h3 style="color:darkgreen">Seems to be an Internet connection. You can continue.</h3>
                             # ~ </div>                             
                          # ~ </div><!--end row-->
                       # ~ </div><!--end container-->
                    # ~ </section> ''',
        # ~ 'ko':'''   <h2 class="StepTitle">Step 4. Internet connection</h2> 
                    # ~ <section>
                       # ~ <div class="container">
                          # ~ <div class="row">
                             # ~ <div class="col-md-2">
                                # ~ <div class="text-center"><i class="fa fa-times fa-4x" aria-hidden="true" style="color:red"></i></div>
                             # ~ </div>
                             # ~ <div class="col-md-10">
                                # ~ <h3 style="color:darkred">Can't connect to Internet.</h3>
                             # ~ </div>                             
                          # ~ </div><!--end row-->
                          # ~ <hr><br><br>
                          # ~ <div class="row">
                             # ~ <div class="col-md-12">
                                # ~ <a href="javascript:void(0);" onclick="skipInternet();$('#wizard').smartWizard('goToStep', 5);"><button  type="button" class="btn btn-warning">Skip Internet check</button></a>
                                # ~ <a href="javascript:void(0);" onclick="$('#wizard').smartWizard('goToStep', 4);"><button  type="button" class="btn btn-success">Check again</button></a>
                             # ~ </div>                             
                          # ~ </div><!--end row-->
                       # ~ </div><!--end container-->
                    # ~ </section> '''}        

html[4]={'ok':'''   <h2 class="StepTitle">Step 4. Isard Engine</h2> 
                    <section>
                       <div class="container">
                          <div class="row">
                             <div class="col-md-2">
                                <div class="text-center"><i class="fa fa-check fa-4x" aria-hidden="true" style="color:green"></i></div>
                             </div>
                             <div class="col-md-10">
                                <h3 style="color:darkgreen">Isard engine is running. You can continue.</h3>
                             </div>                             
                          </div><!--end row-->
                       </div><!--end container-->
                    </section> ''',
        'ko':'''   <h2 class="StepTitle">Step 4. Isard Engine</h2> 
                    <section>
                       <div class="container">
                          <div class="row">
                             <div class="col-md-2">
                                <div class="text-center"><i class="fa fa-times fa-4x" aria-hidden="true" style="color:red"></i></div>
                             </div>
                             <div class="col-md-10">
                                <h3 style="color:darkred">Can't contact isard engine.</h3>
                             </div>                             
                          </div><!--end row-->
                          <hr><br><br>
                          <div class="row">
                             <div class="col-md-12">
                                <a href="javascript:void(0);" onclick="$('#wizard').smartWizard('goToStep', 5);"><button type="button" class="btn btn-success">Check again</button></a>
                             </div>                             
                          </div><!--end row-->
                          <hr><br><br>
                          <div class="row">
                            <div class="col-md-12">
                                <p>Something went wrong while initializing backend engine.</p>
                                <p>Restart installation with docker-compose down && docker-compose up</p>
                            </div>
                          </div>                          
                       </div><!--end container-->
                    </section> '''}          
        
html[5]={'ok':'''   <h2 class="StepTitle">Step 5. Hypervisors</h2> 
                    <section>
                       <div class="container">
                          <div class="row">
                             <div class="col-md-2">
                                <div class="text-center"><i class="fa fa-check fa-4x" aria-hidden="true" style="color:green"></i></div>
                             </div>
                             <div class="col-md-10">
                                <h3 style="color:darkgreen">Found a running hypervisor. You can continue</h3>
                             </div>                             
                          </div><!--end row-->
                       </div><!--end container-->
                    </section> ''',
        'ko':'''   <h2 class="StepTitle">Step 5. Hypervisors</h2> 
                    <section>
                       <div class="container">
                          <div class="row">
                             <div class="col-md-2">
                                <div class="text-center"><i class="fa fa-times fa-4x" aria-hidden="true" style="color:red"></i></div>
                             </div>
                             <div class="col-md-10">
                                <h3 style="color:darkred">Can't contact any hypervisor with virtualization available.</h3>
                             </div>                             
                          </div><!--end row-->
                          <hr><br><br>
                          <div class="row">
                             <div class="col-md-12">
                                <a href="javascript:void(0);" onclick="skipHypervisor();$('#wizard').smartWizard('goToStep', 7);"><button type="button" class="btn btn-warning">Skip Hypervisor check</button></a>
                                <a href="javascript:void(0);" onclick="$('#wizard').smartWizard('goToStep', 6);"><button  type="button" class="btn btn-success">Check again</button></a>
                             </div>                             
                          </div><!--end row-->
                          <hr><br><br>
                          <div class="row">
                            <div class="col-md-12">
                                <p>%s</p>
                                <p>Please check that You have virtualization: <a href="https://isardvdi.readthedocs.io/en/latest/install/install/#requirements" target="_blank">Documentation</a>.</p>
                            </div>
                          </div>                          
                       </div><!--end container-->
                    </section> '''} 

html[6]={'ok':'''   <h2 class="StepTitle">Step 6. Updates</h2> 
                    <section>
                       <div class="container">
                          <div class="row">
                             <div class="col-md-2">
                                <div class="text-center"><i class="fa fa-check fa-4x" aria-hidden="true" style="color:green"></i></div>
                             </div>
                             <div class="col-md-10">
                                <h3 style="color:darkgreen">Demo items in updates service</h3>
                             </div>                             
                          </div><!--end row-->
                          <div class="row">
                             %s                
                          </div><!--end row-->                          
                       </div><!--end container-->
                    </section> ''',
        'noservice':'''   <h2 class="StepTitle">Step 6. Updates</h2> 
                    <section>
                       <div class="container">
                          <div class="row">
                             <div class="col-md-2">
                                <div class="text-center"><i class="fa fa-times fa-4x" aria-hidden="true" style="color:red"></i></div>
                             </div>
                             <div class="col-md-10">
                                <h3 style="color:darkred">Can't contact IsardVDI updates service.</h3>
                             </div>                             
                          </div><!--end row-->
                          <hr><br>
                          <div class="row">
                             <div class="col-md-12">
                                <h4 style="color:darkblue">It could be your Internet connection or IsardVDI updates is in manteinance mode.</h4>
                                  <div class="row">
                                     <div class="col-md-2">
                                        <div class="text-center"><i class="fa fa-check fa-2x" aria-hidden="true" style="color:green"></i></div>
                                     </div>
                                     <div class="col-md-10">
                                        <h3 style="color:darkgreen">You can finish wizard now and try connecting to updates later.</h3>
                                     </div>                             
                                  </div><!--end row-->
                             </div>                             
                          </div><!--end row-->
                       </div><!--end container-->
                    </section> ''',
        'noregister':'''   <h2 class="StepTitle">Step 6. Updates</h2> 
                    <section>
                       <div class="container">
                          <hr><br>
                          <div class="row">
                             <div class="col-md-12">
                                <h4 style="color:darkblue">You unchecked demo updates.</h4>
                                  <div class="row">
                                     <div class="col-md-2">
                                        <div class="text-center"><i class="fa fa-check fa-2x" aria-hidden="true" style="color:green"></i></div>
                                     </div>
                                     <div class="col-md-10">
                                        <h3 style="color:darkgreen">You can finish wizard now and register for updates later.</h3>
                                     </div>                             
                                  </div><!--end row-->
                             </div>                             
                          </div><!--end row-->
                       </div><!--end container-->
                    </section> '''}                             
