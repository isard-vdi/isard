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
        self.doWizard=True if self.first_start() else False
        if self.doWizard: # WIZARD WAS FORCED BY DELETING install/.wizard file
            wlog.warning('Starting initial configuration wizard')
            if not self.valid_js(first=True):
                print('Javascript and CSS not installed!')
                print(' Please install yarn: https://yarnpkg.com/lang/en/docs/install')
                print(' and run yarn from install folder before starting again.')
                exit(1)
            try:
                if self.valid_rethinkdb():
                    if not self.valid_isard_database():
                        self.create_isard_database()
                    #~ else:
                        #~ self.done_start()
            except Exception as e:
                exc_type, exc_obj, exc_tb = sys.exc_info()
                fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                wlog.error(exc_type, fname, exc_tb.tb_lineno)
                wlog.error(e)
                None
            self.run_server()
            
        else: # WIZARD NOT FORCED. SOMETHING IS NOT GOING AS EXPECTED WITH DATABASE?
            if not self.valid_rethinkdb():
                wlog.error('Can not connect to rethinkdb database! Is it running?')
                exit(1)
            else:
                if not self.valid_isard_database():
                    wlog.error('Database isard not found!')
                    wlog.error('If you need to recreate isard database you should activate wizard again:')
                    wlog.error('   REMOVE install/.wizard file  (rm install/.wizard) and start isard again')
                    exit(1)

    def run_server(self):
        from flask import Flask
        self.wapp = Flask(__name__)
        self.wizard_routes()
        wlog.info('ISARD WEBCONFIG AVAILABLE AT http://localhost:5000')
        self.wapp.run()        
                
    def shutdown_server(self):
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            raise RuntimeError('Not running with the Werkzeug Server')
        func()
        wlog.info('Stopping wizard flask server')

        
    def first_start(self):
        path='./install/.wizard'
        return True if not os.path.exists(path) else False
            
    def done_start(self):
        path='./install/.wizard'
        os.mknod(path)

    '''
    CHECK VALID ITEMS
    '''
    def valid_js(self,first=False,path='bower_components/gentelella'):
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
                return True
            else:
                return False
        except Exception as e:
            return False

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
                print('password must be changed')
                return False # Password must be changed so we return false
            if pw.valid('isard',usr['password']):
                print('Password is isard')
                return False
            print('Passwd is not isard')
            return True
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            wlog.error(exc_type, fname, exc_tb.tb_lineno)
            wlog.error(e)
            return False

    def valid_engine(self):
        from ..lib.load_config import load_config
        dict=load_config()        
        return self.valid_server('isard-engine:5555' if 'isard-hypervisor' in dict.keys() else 'localhost:5555')  

    def valid_hypervisor(self):
        return True
                      
    def valid_server(self,server):
        import http.client as httplib
        conn = httplib.HTTPConnection(server, timeout=5)
        try:
            conn.request("HEAD", "/")
            conn.close()
            return True
        except Exception as e:
            conn.close()
            return False        

        
    def create_isard_database(self):
        from ..config.populate import Populate
        p=Populate()
        if p.database():
            p.defaults()
            return True
        return False
        
    def check_all(self):
        from ..lib.load_config import load_config
        dict=load_config()
        if dict:
            res  = {'yarn':self.valid_js(),
                    'config':True,
                    'config_stx':True,
                    'internet':self.valid_server('isardvdi.com'),
                    'rethinkdb':self.valid_rethinkdb(),
                    'isard_db':self.valid_isard_database(),
                    'passwd':self.valid_password(),
                    'docker':True if 'isard-hypervisor' in dict.keys() else False,
                    'hyper':self.valid_hypervisor() if self.valid_isard_database() else False,
                    'engine':self.valid_server('isard-engine:5555' if 'isard-hypervisor' in dict.keys() else 'localhost:5555')}  
        else:
            res =  {'yarn':self.valid_js(),
                    'config':self.valid_config_file(),
                    'config_stx':self.valid_config_syntax(),
                    'internet':self.valid_server('isardvdi.com'),
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
            
        if not res['internet']: 
            errors.append({'stepnum':4,'iserror':True})
        else:
            errors.append({'stepnum':4,'iserror':False})
            
        if not res['engine']: 
            errors.append({'stepnum':5,'iserror':True})
        else:
            errors.append({'stepnum':5,'iserror':False})
            
        if not res['hyper']: 
            errors.append({'stepnum':6,'iserror':True})
        else:
            errors.append({'stepnum':6,'iserror':False})
        return errors
    
    def wizard_routes(self):
            # Static
            @self.wapp.route('/build/<path:path>')
            def send_build(path):
                return send_from_directory(os.path.join(self.wapp.root_path+'/../', 'bower_components/gentelella/build'), path)
    
            @self.wapp.route('/vendors/<path:path>')
            def send_vendors(path):
                return send_from_directory(os.path.join(self.wapp.root_path+'/../', 'bower_components/gentelella/vendors'), path)

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
                print('im on step '+step)
                if request.method == 'POST':
                    if step is '1':
                        return json.dumps(self.valid_config_file() and self.valid_config_syntax())
                    if step is '2':
                        return json.dumps(self.valid_rethinkdb() and self.valid_isard_database())
                    if step is '3':
                        return json.dumps(self.valid_password())
                    if step is '4':
                        return json.dumps(self.valid_server('isardvdi.com'))
                    if step is '5':
                        return json.dumps(self.valid_engine())
                    if step is '6':
                        return json.dumps(self.valid_hypervisor() if self.valid_isard_database() else False)                        
                    if step is '7':
                        return json.dumps(self.valid_server('isardvdi.com:5050')) 
                                                                                                                    
            @self.wapp.route('/content', methods=['POST'])
            def wizard_content():
                global html
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
                    if step == '4':
                        if not self.valid_server('isardvdi.com'):
                            return html[4]['ko']
                        return html[4]['ok']                                              
                    if step == '5':
                        if not self.valid_engine():
                            return html[5]['ko']
                        return html[5]['ok']  
                    if step == '6':
                        if not (self.valid_hypervisor() if self.valid_isard_database() else False):
                            return html[6]['ko']
                        return html[6]['ok']  
                        return 'Hypervisor online' 
                    if step == '7':
                        if not self.valid_server('isardvdi.com:5050'):
                            return 'Isard update website seems down...'
                        return 'This updates are available'                         


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
                                    <li>isard.conf.default</li>
                                    <li>isard.conf.docker</li>
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
                                    <li>isard.conf.default</li>
                                    <li>isard.conf.docker</li>
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
                                <p><i class='fa fa-cog fa-spin fa-3x fa-fw'></i>Creating isard tables...<p>
                            </div>  
                          </div>
                       </div><!--end container-->
                    </section> '''}
                                
html[3]={'ok':'''   <h2 class="StepTitle">Step 1. Change default admin password</h2> 
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
        'ko':'''   <h2 class="StepTitle">Step 1. Change default admin password</h2> 
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

html[4]={'ok':'''   <h2 class="StepTitle">Step 4. Internet connection</h2> 
                    <section>
                       <div class="container">
                          <div class="row">
                             <div class="col-md-2">
                                <div class="text-center"><i class="fa fa-check fa-4x" aria-hidden="true" style="color:green"></i></div>
                             </div>
                             <div class="col-md-10">
                                <h3 style="color:darkgreen">Seems to be an Internet connection. You can continue.</h3>
                             </div>                             
                          </div><!--end row-->
                       </div><!--end container-->
                    </section> ''',
        'ko':'''   <h2 class="StepTitle">Step 4. Internet connection</h2> 
                    <section>
                       <div class="container">
                          <div class="row">
                             <div class="col-md-2">
                                <div class="text-center"><i class="fa fa-times fa-4x" aria-hidden="true" style="color:red"></i></div>
                             </div>
                             <div class="col-md-10">
                                <h3 style="color:darkred">Can't connect to Internet.</h3>
                             </div>                             
                          </div><!--end row-->
                          <hr><br><br>
                          <div class="row">
                             <div class="col-md-12">
                                <a href="javascript:void(0);" onclick="skipInternet();$('#wizard').smartWizard('goToStep', 5);"><button  type="button" class="btn btn-warning">Skip Internet check</button></a>
                                <a href="javascript:void(0);" onclick="$('#wizard').smartWizard('goToStep', 4);"><button  type="button" class="btn btn-success">Check again</button></a>
                             </div>                             
                          </div><!--end row-->
                       </div><!--end container-->
                    </section> '''}        

html[5]={'ok':'''   <h2 class="StepTitle">Step 5. Isard Engine</h2> 
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
        'ko':'''   <h2 class="StepTitle">Step 5. Isard Engine</h2> 
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
                                <p>Please check that engine is running.</p>
                                <p> It can be started with: <b>python3 run_engine.py</b>
                            </div>
                          </div>                          
                       </div><!--end container-->
                    </section> '''}          
        
html[6]={'ok':'''   <h2 class="StepTitle">Step 6. Hypervisors</h2> 
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
        'ko':'''   <h2 class="StepTitle">Step 6. Hypervisors</h2> 
                    <section>
                       <div class="container">
                          <div class="row">
                             <div class="col-md-2">
                                <div class="text-center"><i class="fa fa-times fa-4x" aria-hidden="true" style="color:red"></i></div>
                             </div>
                             <div class="col-md-10">
                                <h3 style="color:darkred">Can't contact any hypervisor.</h3>
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
                                <p>Please check that engine is running.</p>
                                <p> It can be started with: <b>python3 run_engine.py</b>
                            </div>
                          </div>                          
                       </div><!--end container-->
                    </section> '''} 
                            
