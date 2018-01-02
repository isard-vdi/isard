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

import logging as wlog
LOG_LEVEL='INFO'
LOG_FORMAT='%(asctime)s - WIZARD - %(levelname)s: %(message)s'
LOG_DATE_FORMAT='%Y/%m/%d %H:%M:%S'
LOG_LEVEL_NUM = wlog.getLevelName(LOG_LEVEL)
wlog.basicConfig(format=LOG_FORMAT,datefmt=LOG_DATE_FORMAT,level=LOG_LEVEL_NUM)


class Wizard():
    def __init__(self):
        self.doWizard=True if self.first_start() else False
        if self.doWizard: # WIZARD WAS FORCED BY DELETING install/.wizard file
            wlog.warning('Starting initial configuration wizard')
            try:
                if self.check_rethinkdb():
                    if not self.check_isard_database():
                        self.create_isard_database()
                    #~ else:
                        #~ self.done_start()
            except Exception as e:
                exc_type, exc_obj, exc_tb = sys.exc_info()
                fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                log.error(exc_type, fname, exc_tb.tb_lineno)
                wlog.error(e)
                None
            self.run_server()
            
        else: # WIZARD NOT FORCED. SOMETHING IS NOT GOING AS EXPECTED WITH DATABASE?
            if not self.check_rethinkdb():
                wlog.error('Can not connect to rethinkdb database! Is it running?')
                exit(1)
            else:
                if not self.check_isard_database():
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


    def check_js(self,path='bower_components/gentelella'):
        return os.path.exists(os.path.join(self.wapp.root_path+'/../',path))
        
    def check_config_file(self):
        path='./isard.conf'
        return False if not os.path.exists(path) else True
        
    def check_config_syntax(self):
        from ..lib.load_config import load_config
        return True if load_config() else False
        
    def check_rethinkdb(self):
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

    def check_isard_database(self):
        try:
            if 'isard' in r.db_list().run(): 
                return True
            else:
                return False
        except Exception as e:
            return False

    def create_isard_database(self):
        from ..config.populate import Populate
        p=Populate()
        if p.database():
            p.defaults()
            return True
        return False

    #~ def check_docker(self):
        #~ # If hypervisor is isard-hypervisor
        
        #~ return False
        
    def check_hypervisor(self):
        # Database hypervisor status
        # options: localhost or isard-hypervisor
        return False
        
    def check_server(self,server):
        import http.client as httplib
        conn = httplib.HTTPConnection(server, timeout=5)
        try:
            conn.request("HEAD", "/")
            conn.close()
            return True
        except Exception as e:
            conn.close()
            return False        

    def check_all(self):
        from ..lib.load_config import load_config
        dict=load_config()
        if dict:
            res  = {'yarn':self.check_js(),
                    'config':True,
                    'config_stx':True,
                    'internet':self.check_server('isardvdi.com'),
                    'rethinkdb':self.check_rethinkdb(),
                    'isard_db':self.check_isard_database(),
                    'docker':True if 'isard-hypervisor' in dict.keys() else False,
                    'hyper':self.check_hypervisor() if self.check_isard_database() else False,
                    'engine':self.check_server('isard-engine:5555' if 'isard-hypervisor' in dict.keys() else 'localhost:5555')}  
        else:
            res =  {'yarn':self.check_js(),
                    'config':self.check_config_file(),
                    'config_stx':self.check_config_syntax(),
                    'internet':self.check_server('isardvdi.com'),
                    'rethinkdb':self.check_rethinkdb(),
                    'isard_db':self.check_isard_database(),
                    'docker':self.check_docker(),
                    'hyper':self.check_hypervisor(),
                    'engine':self.check_engine()}
        res['continue']=res['yarn'] and res['config_stx'] and res['isard_db'] and res['engine']
        return res

    def fake_check_all(self):
        return {'yarn':False,
                'config':False,
                'config_stx':False,
                'internet':False,
                'rethinkdb':False,
                'docker':False,
                'hyper':False,
                'engine':False,
                'isard_db':False,
                'continue':True}
                
    def get_isardvdi_resources():
        None
    
    def wizard_routes(self):
            # Static
            @self.wapp.route('/build/<path:path>')
            def send_build(path):
                return send_from_directory(os.path.join(self.wapp.root_path+'/../', 'bower_components/gentelella/build'), path)
    
            @self.wapp.route('/vendors/<path:path>')
            def send_vendors(path):
                return send_from_directory(os.path.join(self.wapp.root_path+'/../', 'bower_components/gentelella/vendors'), path)

            @self.wapp.route('/', methods=['GET'])
            def base():
                chk=self.check_all()
                #~ chk=self.fake_check_all()
                msg=''
                if not chk['yarn']:
                    msg='Javascript and CSS libraries not found. Please install it running yarn on install folder.'
                    return render_template('missing_yarn.html',chk=chk, msg=msg.split('\n'))
                if not chk['config']:
                    msg+='\nIsard main configuration file isard.conf missing. Please copy (or rename) isard.conf.default to isard.conf.'
                if not chk['config_stx']:
                    msg+='\nMain configuration file isard.conf can not be read. Please check configuration from isard.conf.default.'
                if not chk['internet']:
                    msg+='\nCan not reach Internet. Please check your Internet connection.'
                if not chk['rethinkdb']:
                    msg+='\nUnable to connect to Rethinkdb server using isard.conf parameters. Is RethinkDB service running?'
                if not chk['isard_db']:
                    msg+='\nRethinkDb isard database not found on server. You should create it now.'
                #~ msg='Everything seems ok. You can continue'
                return render_template('missing_yarn.html',chk=chk, msg=msg.split('\n'))
    
            # Flask routes
            @self.wapp.route('/create_db', methods=['GET'])
            def wizard_createdb():
                return self.create_isard_database()

            @self.wapp.route('/passwd', methods=['GET','POST'])
            def wizard_passwd():
                if request.method == 'POST':
                    wlog.info(request.form['passwd'])
                wlog.error('You did a get...')
                return render_template('wizard_pwd.html')

            @self.wapp.route('/shutdown', methods=['GET'])
            def wizard_shutdown():
                # This shutdowns wizard flask server and allows for main isard src to continue loading.
                self.shutdown_server()
                self.doWizard=False
                time.sleep(4)
                return redirect('/wizard')

        
        
        
