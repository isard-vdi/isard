# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

import random, queue
from threading import Thread
import time, json, sys
from webapp import app
from flask_login import current_user
import rethinkdb as r
from ..lib.log import * 

from .flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

from .admin_api import flatten
from ..auth.authentication import Password  

from netaddr import IPNetwork, IPAddress 

class isardViewer():
    def __init__(self):
        pass

    
    def get_viewer(self,data,current_user,remote_addr=False):
        if current_user.role == 'admin': 
            return self.send_viewer(data,remote_addr=remote_addr)
        else:
            id=data['pk']
            if id.startswith('_'+current_user.id+'_') or id.startswith('_disposable_'+remote_addr.replace('.','_')+'_'):
                return self.send_viewer(data,remote_addr=remote_addr)
        
        return False


    def send_viewer(self,data,kind='domain',remote_addr=False): 
        if data['kind'] == 'file':
            consola=self.get_viewer_ticket(data['pk'],remote_addr=remote_addr)
            return {'kind':data['kind'],'ext':consola[0],'mime':consola[1],'content':consola[2]}
        elif data['kind'] == 'xpi' or data['kind'] == 'html5':
            viewer=self.get_spice_xpi(data['pk'],remote_addr=remote_addr)
            if viewer is not False:
                if viewer['port']:
                    viewer['port'] = viewer['port'] if viewer['port'] else viewer['tlsport']
                    viewer['port'] = "5"+ viewer['port']
                return {'kind':data['kind'],'viewer':viewer}             
        return False




    ##### SPICE VIEWER
    
    def get_domain_spice(self, id, remote_addr=False):
        try:
            domain =  r.table('domains').get(id).run(db.conn)
            
            hostname = self.get_viewer_hostname(domain['viewer'],remote_addr)
            viewer = r.table('hypervisors_pools').get(domain['hypervisors_pools'][0]).run(db.conn)['viewer']
            
            if viewer['defaultMode'] == "Secure":
                viewer = r.table('hypervisors_pools').get(domain['hypervisors_pools'][0]).run(db.conn)['viewer']
                return {'host':hostname,
                        'kind':domain['hardware']['graphics']['type'],
                        'port':domain['viewer']['port'],
                        'tlsport': self.get_viewer_port(domain['hyp_started'],domain['viewer']['tlsport'], remote_addr),
                        'ca':viewer['certificate'],
                        'domain':viewer['domain'],
                        'passwd':domain['viewer']['passwd'],
                        'viewers_options':domain['options']['viewers']}
            else:
                return {'host':hostname,
                        'kind':domain['hardware']['graphics']['type'],
                        'port':self.get_viewer_port(domain['hyp_started'],domain['viewer']['port'],remote_addr),
                        'tlsport':False,
                        'ca':'',
                        'domain':'',
                        'passwd':domain['viewer']['passwd'],
                        'viewers_options':domain['options']['viewers']}
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            log.error(exc_type, fname, exc_tb.tb_lineno)            
            log.error('Viewer for domain '+id+' exception:'+str(e))
            return False
    
    def get_spice_xpi(self, id,remote_addr=False):
        ### Dict for XPI viewer (isardSocketio)
        
        dict = self.get_domain_spice(id)
        if not dict: return False
        #~ ca = str(self.config['spice']['certificate'])
        #~ if not dict['host'].endswith(str(self.config['spice']['domain'])):
            #~ dict['host']=dict['host']+'.'+self.config['spice']['domain']
        #~ ca = str(self.config['spice']['certificate'])
        #~ dict['ca']=ca
        return dict


    ######### VIEWER DOWNLOAD FUNCTIONS
    def get_viewer_ticket(self,id,remote_addr=False,os='generic'):
        viewer = self.get_domain_spice(id,remote_addr=remote_addr)
        if viewer is not False:
            dict=viewer
            if dict['kind']=='vnc':
                return self.get_vnc_ticket(dict,id,os,remote_addr=remote_addr)
            if dict['kind']=='spice':
                return self.get_spice_ticket(dict,id,remote_addr=remote_addr)
        return False
        
    def get_vnc_ticket(self, dict,id,os,remote_addr=False):
        ## Should check if ssl in use: dict['tlsport']:
        hostname=dict['host']
        if dict['tlsport']:
            return False
        #~ os='MacOS'
        if os in ['iOS','Windows','Android','Linux', 'generic', None]:
            consola="""[Connection]
            Host=%s
            Port=%s
            Password=%s

            [Options]
            UseLocalCursor=1
            UseDesktopResize=1
            FullScreen=1
            FullColour=0
            LowColourLevel=0
            PreferredEncoding=ZRLE
            AutoSelect=1
            Shared=0
            SendPtrEvents=1
            SendKeyEvents=1
            SendCutText=1
            AcceptCutText=1
            Emulate3=1
            PointerEventInterval=0
            Monitor=
            MenuKey=F8
            """ % (hostname, dict['port'], dict['passwd'])
            consola = consola.replace("'", "")
            return 'vnc','text/plain',consola
            
        if os in ['MacOS']:
            vnc="vnc://"+hostname+":"+dict['passwd']+"@"+hostname+":"+dict['port']
            consola="""<?xml version="1.0" encoding="UTF-8"?>
            <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
            <plist version="1.0">
            <dict>
                <key>URL</key>
                <string>%s</string>
                <key>restorationAttributes</key>
                <dict>
                    <key>autoClipboard</key>
                    <false/>
                    <key>controlMode</key>
                    <integer>1</integer>
                    <key>isFullScreen</key>
                    <false/>
                    <key>quality</key>
                    <integer>3</integer>
                    <key>scalingMode</key>
                    <true/>
                    <key>screenConfiguration</key>
                    <dict>
                        <key>GlobalIsMixedMode</key>
                        <false/>
                        <key>GlobalScreen</key>
                        <dict>
                            <key>Flags</key>
                            <integer>0</integer>
                            <key>Frame</key>
                            <string>{{0, 0}, {1920, 1080}}</string>
                            <key>Identifier</key>
                            <integer>0</integer>
                            <key>Index</key>
                            <integer>0</integer>
                        </dict>
                        <key>IsDisplayInfo2</key>
                        <false/>
                        <key>IsVNC</key>
                        <true/>
                        <key>ScaledSelectedScreenRect</key>
                        <string>(0, 0, 1920, 1080)</string>
                        <key>Screens</key>
                        <array>
                            <dict>
                                <key>Flags</key>
                                <integer>0</integer>
                                <key>Frame</key>
                                <string>{{0, 0}, {1920, 1080}}</string>
                                <key>Identifier</key>
                                <integer>0</integer>
                                <key>Index</key>
                                <integer>0</integer>
                            </dict>
                        </array>
                    </dict>
                    <key>selectedScreen</key>
                    <dict>
                        <key>Flags</key>
                        <integer>0</integer>
                        <key>Frame</key>
                        <string>{{0, 0}, {1920, 1080}}</string>
                        <key>Identifier</key>
                        <integer>0</integer>
                        <key>Index</key>
                        <integer>0</integer>
                    </dict>
                    <key>targetAddress</key>
                    <string>%s</string>
                    <key>viewerScaleFactor</key>
                    <real>1</real>
                    <key>windowContentFrame</key>
                    <string>{{0, 0}, {1829, 1029}}</string>
                    <key>windowFrame</key>
                    <string>{{45, 80}, {1829, 1097}}</string>
                </dict>
            </dict>
            </plist>""" % (vnc,vnc)
            consola = consola.replace("'", "")
            return 'vncloc','text/plain',consola
        
        
    def get_spice_ticket(self, dict,id,remote_addr=False):
        #~ dict = self.get_domain_spice(id)
        if not dict: return False
        #~ ca = str(self.config['spice']['certificate'])
        #~ if not dict['host'].endswith(str(self.config['spice']['domain'])):
            #~ dict['host']=dict['host']+'.'+self.config['spice']['domain']
        hostname=dict['host']
        if not dict['tlsport']:
            ######################
            # Client without TLS #
            ######################
            c = '%'
            consola = """[virt-viewer]
        type=%s
        host=%s
        port=%s
        password=%s
        fullscreen=%s
        title=%s:%sd - Prem SHIFT+F12 per sortir
        enable-smartcard=0
        enable-usb-autoshare=1
        delete-this-file=1
        usb-filter=-1,-1,-1,-1,0
        ;tls-ciphers=DEFAULT
        """ % (dict['kind'],hostname, dict['port'], dict['passwd'], 1 if dict['viewers_options']['spice']['fullscreen'] else 0, id, c)

            consola = consola + """;host-subject=O=%s,CN=%s
        ;ca=%r
        toggle-fullscreen=shift+f11
        release-cursor=shift+f12
        secure-attention=ctrl+alt+end
        ;secure-channels=main;inputs;cursor;playback;record;display;usbredir;smartcard""" % (
            'host-subject', 'hostname', '')

        else:
            ######################
            # TLS Client         #
            ######################
            c = '%'
            consola = """[virt-viewer]
        type=%s
        host=%s
        password=%s
        tls-port=%s
        fullscreen=%s
        title=%s:%sd - Prem SHIFT+F12 per sortir
        enable-smartcard=0
        enable-usb-autoshare=1
        delete-this-file=1
        usb-filter=-1,-1,-1,-1,0
        tls-ciphers=DEFAULT
        """ % (dict['kind'],hostname, dict['passwd'], dict['tlsport'], 1 if dict['viewers_options']['spice']['fullscreen'] else 0, id, c)

            consola = consola + """;host-subject=O=%s,CN=%s
        ca=%r
        toggle-fullscreen=shift+f11
        release-cursor=shift+f12
        secure-attention=ctrl+alt+end
        secure-channels=main;inputs;cursor;playback;record;display;usbredir;smartcard""" % (
            'host-subject', 'hostname', dict['ca'])

        consola = consola.replace("'", "")
        return 'vv','application/x-virt-viewer',consola
        
        
    def get_viewer_hostname(self,viewer,remote_addr):
        if remote_addr is False: return viewer['hostname'] 
        if IPAddress(remote_addr).is_private() or not 'hostname_external' in viewer.keys():
            return viewer['hostname']
        else:
            return viewer['hostname_external']

    def get_viewer_port(self,hypervisor,port,remote_addr):
        if remote_addr is False: return port #viewer['hostname'] 
        
        if IPAddress(remote_addr).is_private():
            return port
        else:
            return int(port) + int(r.table('hypervisors').get(hypervisor).run(db.conn)['viewer_nat_offset'])
                        
    def get_graphics(self):
        with app.app_context():
            return [{'id':'spice','name':'Spice'},{'id':'vnc','name':'VNC'}]                            
