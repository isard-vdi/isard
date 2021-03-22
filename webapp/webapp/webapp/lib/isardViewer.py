# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8
import sys, json
import os
from webapp import app
import rethinkdb as r
from ..lib.log import *

from .flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

from .admin_api import flatten
from netaddr import IPNetwork, IPAddress
import urllib

from ..lib.viewer_exc import *

from http.cookies import SimpleCookie
import base64

class isardViewer():
    def __init__(self):
        # Offset from base_port == spice
        self.spice=0
        self.spice_tls=1
        self.vnc=2
        self.vnc_tls=3
        self.vnc_ws=-198 #5900-200????
        pass

    def viewer_data(self,id,get_viewer='spice-client',current_user=False,default_viewer=False,get_cookie=True):
        try:
            domain =  r.table('domains').get(id).pluck('id','name','status','viewer','options','user','tag').run(db.conn)
        except DomainNotfound:
            raise
        if not domain['status'] == 'Started':
            raise DomainNotStarted
        if current_user != False:
            # if not owner and not his tag
            if domain['user'] != current_user.id or not (current_user.role == 'advanced' and 'tag' in domain.keys() and domain['tag'] in current_user.tags):
                return False

        if  'preferred' not in domain['options']['viewers'].keys() or not domain['options']['viewers']['preferred'] == default_viewer:
            r.table('domains').get(id).update({'options':{'viewers':{'preferred':default_viewer}}}).run(db.conn)

        if get_viewer == 'rdp-client':
            return {'kind':'file','name':'isard-rdp','ext':'rdp','mime':'application/x-rdp','content':self.get_rdp_file(domain['viewer']['guest_ip'])} 


        if get_viewer == 'spice-html5':
            port=domain['viewer']['base_port']
            if get_cookie:
                cookie = base64.b64encode(json.dumps({
                    'web_viewer': {
                        'vmName': domain['name'],
                        'vmHost': domain['viewer']['proxy_hyper_host'],
                        'vmPort': str(domain['viewer']['base_port']),
                        'host': domain['viewer']['proxy_video'],
                        'port': '443',
                        'token': domain['viewer']['passwd']
                    }
                }).encode('utf-8')).decode('utf-8')
                uri = 'https://'+domain['viewer']['static']+'/viewer/spice-web-client/',
                return {'kind':'url','viewer':uri,'cookie':cookie}
            else:
                return 'https://'+domain['viewer']['static']+'/viewer/spice-web-client/?vmName='+urllib.parse.quote_plus(domain['name'])+'&vmHost='+domain['viewer']['proxy_hyper_host']+'&host='+domain['viewer']['proxy_video']+'&port='+str(port)+'&passwd='+domain['viewer']['passwd']

        if get_viewer == 'vnc-html5':
            port=domain['viewer']['base_port']+self.vnc
            if get_cookie:
                cookie = base64.b64encode(json.dumps({
                    'web_viewer': {
                        'vmName': domain['name'],
                        'vmHost': domain['viewer']['proxy_hyper_host'],
                        'vmPort': str(domain['viewer']['base_port']+self.vnc),
                        'host': domain['viewer']['proxy_video'],
                        'port': '443',
                        'token': domain['viewer']['passwd']
                    }
                }).encode('utf-8')).decode('utf-8')
                uri = 'https://'+domain['viewer']['static']+'/viewer/noVNC/',
                return {'kind':'url','viewer':uri,'cookie':cookie}
            else:
                #print('https://'+domain['viewer']['static']+'/viewer/noVNC/src/vnc_lite.html?vmName='+urllib.parse.quote_plus(domain['name'])+'&vmHost='+domain['viewer']['proxy_hyper_host']+'&host='+domain['viewer']['proxy_video']+'&port='+str(port)+'&passwd='+domain['viewer']['passwd'])
                return 'https://'+domain['viewer']['static']+'/viewer/noVNC/src/vnc_lite.html?vmName='+urllib.parse.quote_plus(domain['name'])+'&vmHost='+domain['viewer']['proxy_hyper_host']+'&host='+domain['viewer']['proxy_video']+'&vmPort='+str(port)+'&passwd='+domain['viewer']['passwd']

        if get_viewer == 'spice-client':
            port=domain['viewer']['base_port']+self.spice_tls
            consola=self.get_spice_file(domain,port)
            if get_cookie:
                return {'kind':'file','ext':consola[0],'mime':consola[1],'content':consola[2]}
            else:
                return consola[2]

        if get_viewer == 'vnc-client':
            return False
        if get_viewer == 'vnc-client-macos':
            return False
        return False

    def get_rdp_file(self,ip):
        return """full address:s:%s
""" % (ip)

    def get_spice_file(self, domain, port):
        try:
            op_fscr = 1 if domain['options'] != False and domain['options']['fullscreen'] else 0
        except:
            op_fscr = 0

        c = '%'
        consola = """[virt-viewer]
        type=%s
        proxy=http://%s:%s
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
        """ % (
            'spice',
            domain['viewer']['proxy_video'],
            os.environ.get('SPICE_PROXY_PORT', 80),
            domain['viewer']['proxy_hyper_host'],
            domain['viewer']['passwd'],
            port,op_fscr,
            domain['name'] +' (TLS)',
            c
        )

        consola = consola + """%shost-subject=%s
        %sca=%r
        toggle-fullscreen=shift+f11
        release-cursor=shift+f12
        secure-attention=ctrl+alt+end
        secure-channels=main;inputs;cursor;playback;record;display;usbredir;smartcard""" % (
            '' if domain['viewer']['tls']['host-subject'] != False else ';', domain['viewer']['tls']['host-subject'], '' if domain['viewer']['tls']['certificate'] != False else ';', domain['viewer']['tls']['certificate'])

        consola = consola.replace("'", "")
        return 'vv','application/x-virt-viewer',consola

##### VNC NOT DONE

    def get_domain_vnc_data(self, domain, hostnames, viewer, port):
        try:
            cookie = base64.b64encode(json.dumps({
                'web_viewer': {
                    'host': hostnames['host'],
                    'port': str(int(port)),
                    'token': domain['viewer']['passwd']
                }
            }).encode('utf-8')).decode('utf-8')

            return {
                'uri': 'https://' + hostnames['proxy'] + '/viewer/noVNC',
                'cookie': cookie
            }

        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            log.error(exc_type, fname, exc_tb.tb_lineno)
            log.error('Viewer for domain '+domain['name']+' exception:'+str(e))
            return False

    # ~ def get_domain_vnc_data(self, domain, hostnames, viewer, port, tlsport, selfsigned, remote_addr=False):
        # ~ try:
            # ~ ''' VNC does not have ssl. Only in websockets is available '''
            # ~ if viewer['defaultMode'] == "Secure" and domain['viewer']['port_spice_ssl'] != False:
                # ~ return {'host':hostname,
                        # ~ 'name': domain['name'],
                        # ~ 'port': port,
                        # ~ 'wsport': str(int(port)+500),
                        # ~ 'ca':viewer['certificate'],
                        # ~ 'domain':viewer['domain'],
                        # ~ 'host-subject':viewer['host-subject'],
                        # ~ 'passwd': domain['viewer']['passwd'],
                        # ~ 'uri': 'https://<domain>/wsviewer/novnclite'+selfsigned+'/?host='+hostname+'&port='+str(int(port))+'&password='+domain['viewer']['passwd'],
                        # ~ 'options': domain['options']['viewers']['vnc'] if 'vnc' in domain['options']['viewers'].keys() else False}
            # ~ if viewer['defaultMode'] == "Insecure" and domain['viewer']['port_spice'] != False:
                # ~ return {'host':hostname,
                        # ~ 'name': domain['name'],
                        # ~ 'port': port,
                        # ~ 'wsport': str(int(port)+500),
                        # ~ 'ca':viewer['certificate'],
                        # ~ 'domain':viewer['domain'],
                        # ~ 'host-subject':viewer['host-subject'],
                        # ~ 'passwd': domain['viewer']['passwd'],
                        # ~ 'uri': 'http://<domain>/wsviewer/novnclite/?host='+hostname+'&port='+str(int(port))+'&password='+domain['viewer']['passwd'],
                        # ~ 'options': domain['options']['viewers']['vnc'] if 'vnc' in domain['options']['viewers'].keys() else False}
            # ~ log.error('No available VNC Viewer for domain '+domain['name']+' exception:'+str(e))
            # ~ return False
        # ~ except Exception as e:
            # ~ exc_type, exc_obj, exc_tb = sys.exc_info()
            # ~ fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            # ~ log.error(exc_type, fname, exc_tb.tb_lineno)
            # ~ log.error('Viewer for domain '+domain['name']+' exception:'+str(e))
            # ~ return False

    ##### VNC FILE VIEWER
    def get_vnc_file(self, dict, id, clientos, remote_addr=False):
        ## Should check if ssl in use: dict['tlsport']:
        hostname=dict['host']
        # ~ if dict['tlsport']:
            # ~ return False
        #~ os='MacOS'
        if clientos in ['iOS','Windows','Android','Linux', 'generic', None]:
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

        if clientos in ['MacOS']:
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

