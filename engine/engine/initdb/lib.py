# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

import os
import bcrypt,string,random
import pem
from OpenSSL import crypto
import rethinkdb as r

class loadConfig():

    def __init__(self):
        None
            
    def cfg(self):
        return {'RETHINKDB_HOST': os.environ['RETHINKDB_HOST'],
                'RETHINKDB_PORT': os.environ['RETHINKDB_PORT'],
                'RETHINKDB_DB': os.environ['RETHINKDB_DB'],
                'LOG_LEVEL': os.environ['LOG_LEVEL'],
                'WEBAPP_ADMIN_PWD': os.environ['WEBAPP_ADMIN_PWD']}


class Certificates(object):
    def __init__(self, pool='default'):
        self.pool=pool
        self.ca_file='/certs/ca-cert.pem'
        self.server_file='/certs/server-cert.pem'   
        cfg=loadConfig()
        self.cfg=cfg.cfg()    
        

    def get_viewer(self,update_db=False):
        if update_db is False:
            return self.__process_viewer()
        else:
            viewer = self.__process_viewer()
            return self.__update_hypervisor_pool(viewer)

    def update_hyper_pool(self):
        viewer = self.__process_viewer()
        return self.__update_hypervisor_pool(viewer)
            
    def __process_viewer(self):
        ca_cert = server_cert = []
        try:
            ca_cert = pem.parse_file(self.ca_file)
        except:
            ca_cert =[]
        ca_cert = False if len(ca_cert) == 0 else ca_cert[0].as_text()
            
        try:
            server_cert = pem.parse_file(self.server_file)
        except:
            server_cert=[]
        server_cert = False if len(server_cert) == 0 else server_cert[0].as_text()
        
        if server_cert is False:
            print('No valid certificate found in /opt/isard/certs/viewers')
            return {'defaultMode':'Insecure',
                                'certificate':False,
                                'server-cert': False,
                                'host-subject': False,
                                'domain':False} 
                                
        db_viewer = self.__get_hypervisor_pool_viewer()
        # ~ log.info(server_cert)
        if server_cert == db_viewer['server-cert']:
            return db_viewer
        
        '''From here we have a valid server_cert that has to be updated'''
        server_cert_obj = crypto.load_certificate(crypto.FILETYPE_PEM, open(self.server_file).read())
        
        if ca_cert is False:
            '''NEW VERIFIED CERT'''
            print('Seems a trusted certificate...')
            if self.__extract_ca() is False:
                log.error('Something failed while extracting ca root cert from server-cert.pem!!')
                print('Something failed while extracting ca root cert from server-cert.pem!!')
                return {'defaultMode':'Insecure',
                                    'certificate':False,
                                    'server-cert': False,
                                    'host-subject': False,
                                    'domain':'ERROR IMPORTING CERTS'} 
            print('Domain: '+server_cert_obj.get_subject().CN)
            return {'defaultMode':'Secure',
                                'certificate':False,
                                'server-cert': server_cert,
                                'host-subject': False,
                                'domain':server_cert_obj.get_subject().CN}               
        else:
            '''NEW SELF SIGNED CERT'''
            print('Seems a self signed certificate')
            ca_cert_obj = crypto.load_certificate(crypto.FILETYPE_PEM, open(self.ca_file).read())
            hs=''
            for t in server_cert_obj.get_subject().get_components():
                hs=hs+t[0].decode("utf-8")+'='+t[1].decode("utf-8")+','
            print('Domain: '+ca_cert_obj.get_subject().CN)
            return {'defaultMode':'Secure',
                                'certificate': ca_cert,
                                'server-cert': server_cert,
                                'host-subject': hs[:-1],
                                'domain':ca_cert_obj.get_subject().CN}             
        
        
    def __extract_ca(self):
        try:
            certs = pem.parse_file(self.server_file)
        except:
            print('Could not find server-cert.pem file in folder!!')
            log.error('Could not find server-cert.pem file in folder!!')
            return False
        if len(certs) < 2:
            print('The server-cert.pem certificate is not the full chain!! Please add ca root certificate to server-cert.pem chain.')
            log.error('The server-cert.pem certificate is not the full chain!! Please add ca root certificate to server-cert.pem chain.')
            return False
        ca = certs[-1].as_text()
        if os.path.isfile(self.ca_file):
            print('The ca-cert.file already exists. This ca extraction can not be done.')
            log.error('The ca-cert.file already exists. This ca extraction can not be done.')
            return False
        try:
            with open(self.ca_file, "w") as caFile:
                res=caFile.write(ca)  
        except:
            print('Unable to write to server-cert.pem file!!')
            log.error('Unable to write to server-cert.pem file!!')
            return False
        return ca        
        
    def __get_hypervisor_pool_viewer(self):
        try:
            with app.app_context():
                viewer = r.table('hypervisors_pools').get(self.pool).pluck('viewer').run()['viewer']
                if 'server-cert' not in viewer.keys():
                    viewer['server-cert']=False
                return viewer
        except:
            return {'defaultMode':'Insecure',
                                'certificate':False,
                                'server-cert': False,
                                'host-subject': False,
                                'domain':False} 
        
    def __update_hypervisor_pool(self,viewer):
        try:
            self.conn = r.connect( self.cfg['RETHINKDB_HOST'],self.cfg['RETHINKDB_PORT'],self.cfg['RETHINKDB_DB']).repl()
        except Exception as e:
            log.error('Database not reacheable at '+self.cfg['RETHINKDB_HOST']+':'+self.cfg['RETHINKDB_PORT'])
            exit
        r.table('hypervisors_pools').get(self.pool).update({'viewer':viewer}).run()
        if viewer['defaultMode'] == 'Secure' and viewer['certificate'] is False:
            try:
                if r.table('hypervisors').get('isard-hypervisor').run()['viewer_hostname'] == 'isard-hypervisor':
                    r.table('hypervisors').get('isard-hypervisor').update({'viewer_hostname':viewer['domain']}).run()
            except Exception as e:
                log.error('Could not update hypervisor isard-hypervisor with certificate name. You should do it through UI')
        print('Certificates updated in database')
        return True
        
        
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

# ~ class Updates():
    # ~ def register_isard_updates(self):
        # ~ dict={'resources':{'url':'http://www.isardvdi.com:5050','code':False}}
        # ~ try:
            # ~ req= requests.post('http://www.isardvdi.com:5050/register' ,allow_redirects=False, verify=False, timeout=5)
            # ~ if req.status_code==200:
                # ~ self.code=req.json()
                ##r.table('config').get(1).update({'resources':{'url':self.url,'code':req.json()}}).run()
                # ~ dict={'resources':{'url':self.url,'code':self.code}}
                # ~ wlog.warning('Isard app registered')
                # ~ return dict
            # ~ else:
                # ~ wlog.info('Isard app registering error response code: '+str(req.status_code)+'\nDetail: '+r.json())
                # ~ return dict
        # ~ except Exception as e:
            # ~ wlog.warning("Error contacting.\n"+str(e))
            # ~ return dict
        # ~ return dict
        
