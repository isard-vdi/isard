# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8
import sys, json
from webapp import app
import rethinkdb as r
from ..lib.log import * 

from .flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

import urllib

class isardVpn():
    def __init__(self):
        pass

    def vpn_data(self,vpn,kind,op_sys,itemid=False):
        if vpn == 'users':
            if itemid == False: return False
            wgdata = r.table('users').get(itemid).pluck('id','vpn').run(db.conn)
            port='443'
            endpoint=os.environ['DOMAIN']
        elif vpn == 'hypers':
            #if itemid.role != 'admin': return False
            hyper=r.table('hypervisors').get(itemid).pluck('id','vpn').run(db.conn)
            wgdata = hyper
            port='4443'
            endpoint='isard-vpn' if itemid == 'isard-hypervisor' else os.environ['DOMAIN']
        else:
            return False

        if wgdata == None or 'vpn' not in wgdata.keys():
            return False

        ## First up time the wireguard config keys are missing till isard-vpn populates it.
        if not getattr(app, 'wireguard_server_keys', False):
            sysconfig = r.db('isard').table('config').get(1).run(db.conn)
            app.wireguard_server_keys = sysconfig.get('vpn_'+vpn, {}).get('wireguard', {}).get('keys', False)
        if not app.wireguard_server_keys:
            log.error('There are no wireguard keys in webapp config yet. Try again in a few seconds...')
            return False

        if kind == 'config':
            return {'kind':'file','name':'isard-vpn','ext':'conf','mime':'text/plain','content':self.get_wireguard_file(endpoint,wgdata,port)} 
        elif kind == 'install':
            ext='sh' if op_sys == 'Linux' else 'vb'
            return {'kind':'file','name':'isard-vpn-setup','ext':ext,'mime':'text/plain','content':self.get_wireguard_install_script(endpoint,wgdata,op_sys)} 

        return False

    def get_wireguard_file(self,endpoint,peer,port):
        return """[Interface]
Address = %s
PrivateKey = %s

[Peer]
PublicKey = %s
Endpoint = %s:%s
AllowedIPs = %s
PersistentKeepalive = 25
""" % (peer['vpn']['wireguard']['Address'],peer['vpn']['wireguard']['keys']['private'],app.wireguard_server_keys['public'],endpoint,port,peer['vpn']['wireguard']['AllowedIPs'])

    def get_wireguard_install_script(self,endpoint,peer,op_sys):
        return """#!/bin/bash
echo "Installing wireguard. Ubuntu/Debian script."
apt install -y wireguard git dh-autoreconf libglib2.0-dev intltool build-essential libgtk-3-dev libnma-dev libsecret-1-dev network-manager-dev resolvconf
git clone https://github.com/max-moser/network-manager-wireguard
cd network-manager-wireguard
./autogen.sh --without-libnm-glib
./configure --without-libnm-glib --prefix=/usr --sysconfdir=/etc --libdir=/usr/lib/x86_64-linux-gnu --libexecdir=/usr/lib/NetworkManager --localstatedir=/var
make   
sudo make install
cd ..
echo "%s" > isard-vpn.conf
echo "You have your user vpn configuration to use it with NetworkManager: isard-vpn.conf""" % self.get_wireguard_file(endpoint,peer)