# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

import sys
from webapp import app
import rethinkdb as r
from ..lib.log import * 

from .flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

from .admin_api import flatten
from netaddr import IPNetwork, IPAddress 

class isardViewer():
    def __init__(self):
        pass

    
    def get_viewer(self,data,current_user,remote_addr=False):
        domain =  r.table('domains').get(data['pk']).run(db.conn)
        if 'preferred' in data.keys():
            if data['preferred']:
                domain['options']['viewers']['preferred']=data['kind']
            else:
                domain['options']['viewers']['preferred']=False
            r.table('domains').get(data['pk']).update({'options':{'viewers':domain['options']['viewers']}}).run(db.conn)   
                   
        if current_user.role == 'admin': 
            return self.send_viewer(data,domain,remote_addr=remote_addr)
        else:
            id=data['pk']
            if id.startswith('_'+current_user.id+'_') or id.startswith('_disposable_'+remote_addr.replace('.','_')+'_'):
                return self.send_viewer(data,domain,remote_addr=remote_addr)
        
        return False


    def send_viewer(self,data,domain,kind='domain',remote_addr=False): 
        if data['kind'] == 'spice-html5':
            viewer = self.get_domain_spice_data(data['pk'],domain,remote_addr=remote_addr)
            if viewer is not False:
                # ~ if viewer['port']:
                    # ~ viewer['port'] = viewer['port'] if viewer['port'] else viewer['tlsport']
                    # ~ viewer['port'] = "5"+ viewer['port']
                # ~ url='/wsviewer/eyeos/?host='+viewer['host']+'&port='+viewer['wsport']+'&passwd='+viewer['passwd']
                return {'kind':'url','viewer':viewer['uri']} 
                                     
        if data['kind'] == 'spice-client':
            viewer = self.get_domain_spice_data(data['pk'],domain,remote_addr=remote_addr)
            consola=self.get_spice_file(viewer,data['pk'],remote_addr=remote_addr)
            return {'kind':'file','ext':consola[0],'mime':consola[1],'content':consola[2]}      
                        
        if data['kind'] == 'vnc-html5':
            viewer = self.get_domain_vnc_data(data['pk'],domain,remote_addr=remote_addr)
            if viewer is not False:
                # ~ url='/wsviewer/novnclite/?host='+viewer['host']+'&port='+viewer['wsport']+'&password='+viewer['passwd']
                return {'kind':'url','viewer':viewer['uri']}   
                                   
        if data['kind'] == 'vnc-client':
            viewer = self.get_domain_vnc_data(data['pk'],domain,remote_addr=remote_addr)
            consola=self.get_vnc_file(viewer,data['pk'],remote_addr=remote_addr,os=data['os'])
            return {'kind':'file','ext':consola[0],'mime':consola[1],'content':consola[2]}
    
    def get_domain_spice_data(self, id, domain,remote_addr=False):
        try:
            hostname = self.get_viewer_hostname(domain['viewer'],remote_addr)
            viewer = r.table('hypervisors_pools').get(domain['hypervisors_pools'][0]).run(db.conn)['viewer']
 
            if viewer['defaultMode'] == "Secure" and domain['viewer']['port_spice_ssl'] is not False:
                tlsport=self.get_viewer_port(domain['hyp_started'],domain['viewer']['port_spice_ssl'],remote_addr)
                port=self.get_viewer_port(domain['hyp_started'],domain['viewer']['port_spice'],remote_addr)
                selfsigned='' if viewer['certificate'] is False else '_ss'
                return {'host':hostname,
                        'name': domain['name'],
                        'port': port,
                        'wsport': str(int(port)+500),
                        'tlsport': tlsport,
                        'ca':viewer['certificate'],
                        'domain':viewer['domain'],
                        'host-subject':viewer['host-subject'],
                        'passwd':domain['viewer']['passwd'],
                        'uri': 'https://<domain>/wsviewer/spice'+selfsigned+'/?host='+hostname+'&port='+str(int(port)+500)+'&passwd='+domain['viewer']['passwd']+'&protocol=wss',
                        'viewers_options': domain['options']['viewers']['spice'] if 'spice' in domain['options']['viewers'].keys() else False}
            if viewer['defaultMode'] == "Insecure" and domain['viewer']['port_spice'] is not False:
                port=self.get_viewer_port(domain['hyp_started'],domain['viewer']['port_spice'],remote_addr)
                return {'host':hostname,
                        'name': domain['name'],
                        'port': port,
                        'wsport': str(int(port)+500),
                        'tlsport':False,
                        'ca':False,
                        'domain':False,
                        'host-subject':False,
                        'passwd':domain['viewer']['passwd'],
                        'uri': 'http://<domain>/wsviewer/spice/?host='+hostname+'&port='+str(int(port)+500)+'&passwd='+domain['viewer']['passwd']+'&protocol=ws',
                        'options':domain['options']['viewers']['spice'] if 'spice' in domain['options']['viewers'].keys() else False}
            log.error('No available Spice Viewer for domain '+id+' exception:'+str(e))
            return False
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            log.error(exc_type, fname, exc_tb.tb_lineno)            
            log.error('Viewer for domain '+id+' exception:'+str(e))
            return False
    
    def get_domain_vnc_data(self, id, domain, remote_addr=False):
        try:
            hostname = self.get_viewer_hostname(domain['viewer'],remote_addr)
            viewer = r.table('hypervisors_pools').get(domain['hypervisors_pools'][0]).run(db.conn)['viewer']
            port = self.get_viewer_port(domain['hyp_started'],domain['viewer']['port_vnc'], remote_addr)
            selfsigned='' if viewer['certificate'] is False else '_ss'
            ''' VNC does not have ssl. Only in websockets is available '''
            if viewer['defaultMode'] == "Secure" and domain['viewer']['port_spice_ssl'] is not False:
                return {'host':hostname,
                        'name': domain['name'],
                        'port': port,
                        'wsport': str(int(port)+500),
                        'ca':viewer['certificate'],
                        'domain':viewer['domain'],
                        'host-subject':viewer['host-subject'],
                        'passwd': domain['viewer']['passwd'],
                        'uri': 'https://<domain>/wsviewer/novnclite'+selfsigned+'/?host='+hostname+'&port='+str(int(port)+500)+'&password='+domain['viewer']['passwd'],
                        'options': domain['options']['viewers']['vnc'] if 'vnc' in domain['options']['viewers'].keys() else False}
            if viewer['defaultMode'] == "Insecure" and domain['viewer']['port_spice'] is not False:
                return {'host':hostname,
                        'name': domain['name'],
                        'port': port,
                        'wsport': str(int(port)+500),
                        'ca':viewer['certificate'],
                        'domain':viewer['domain'],
                        'host-subject':viewer['host-subject'],
                        'passwd': domain['viewer']['passwd'],
                        'uri': 'http://<domain>/wsviewer/novnclite/?host='+hostname+'&port='+str(int(port)+500)+'&password='+domain['viewer']['passwd'],
                        'options': domain['options']['viewers']['vnc'] if 'vnc' in domain['options']['viewers'].keys() else False}                
            log.error('No available VNC Viewer for domain '+id+' exception:'+str(e))
            return False
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            log.error(exc_type, fname, exc_tb.tb_lineno)            
            log.error('Viewer for domain '+id+' exception:'+str(e))
            return False
                

    ##### VNC FILE VIEWER
    def get_vnc_file(self, dict,id,os,remote_addr=False):
        ## Should check if ssl in use: dict['tlsport']:
        hostname=dict['host']
        # ~ if dict['tlsport']:
            # ~ return False
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
        

    ##### SPICE FILE VIEWER
    def get_spice_file(self, dict,id,remote_addr=False):
        if not dict: return False
        
        # Options
        try:
            op_fscr = 1 if dict['options'] is not False and dict['options']['fullscreen'] else 0
        except:
            op_fscr = 0
        
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
        """ % ('spice',hostname, dict['port'], dict['passwd'], op_fscr, dict['name']+' [[NOT ENCRYPTED]]', c)

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
        """ % ('spice',hostname, dict['passwd'], dict['tlsport'], op_fscr, dict['name']+' [[ENCRYPTED]]', c)

            consola = consola + """%shost-subject=%s
        %sca=%r
        toggle-fullscreen=shift+f11
        release-cursor=shift+f12
        secure-attention=ctrl+alt+end
        secure-channels=main;inputs;cursor;playback;record;display;usbredir;smartcard""" % (
            '' if dict['host-subject'] is not False else ';', dict['host-subject'], '' if dict['ca'] is not False else ';', dict['ca'])

        consola = consola.replace("'", "")
        return 'vv','application/x-virt-viewer',consola
        
        
    def get_viewer_hostname(self,viewer,remote_addr):
        if remote_addr is False: return viewer['hostname'] 
        if IPAddress(remote_addr).is_private() or not 'hostname_external' in viewer.keys() or viewer['hostname_external'] is False:
            return viewer['hostname']
        else:
            return viewer['hostname_external']

    def get_viewer_port(self,hypervisor,port,remote_addr):
        if remote_addr is False: return port #viewer['hostname'] 
        
        if IPAddress(remote_addr).is_private():
            return port
        else:
            return int(port) + int(r.table('hypervisors').get(hypervisor).run(db.conn)['viewer_nat_offset'])
                        
