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

    def vpn_data(self,vpn,kind,os,current_user=False):
        if vpn == 'users':
            if current_user == False: return False
            wgdata = r.table('users').get(current_user.id).pluck('vpn').run(db.conn) 
        elif vpn == 'hypers':
            if current_user.role != 'admin': return False
            wgdata = r.table('hypervisors').get(current_user.id).pluck('vpn').run(db.conn)
        else:
            return False
        if wgdata == None or 'vpn' not in wgdata.keys():
            return False
        ## First up time the wireguard config keys are missing till isard-vpn populates it.
        if app.wireguard_users_keys == False:
            sysconfig = r.db('isard').table('config').get(1).run(db.conn)
            app.wireguard_users_keys = sysconfig.get('vpn_users', {}).get('wireguard', {}).get('keys', False)
        if app.wireguard_users_keys == False:
            log.error('There are no wireguard keys in webapp config yet. Try again in a few seconds...')
            return False
        endpoints=list(r.table('hypervisors').pluck({'viewer': 'static'}).run(db.conn))
        if len(endpoints):
            endpoint = endpoints[0]['viewer']['static']
        if kind == 'config':
            return {'kind':'file','name':'isard-vpn','ext':'conf','mime':'text/plain','content':self.get_wireguard_file(endpoint,wgdata)} 
        elif kind == 'install':
            ext='sh' if os == 'Linux' else 'vb'
            return {'kind':'file','name':'isard-vpn-setup','ext':ext,'mime':'text/plain','content':self.get_wireguard_install_script(endpoint,wgdata,os)} 

        return False
        
    def get_wireguard_file(self,endpoint,peer):
        return """[Interface]
Address = %s
PrivateKey = %s

[Peer]
PublicKey = %s
Endpoint = %s:443
AllowedIPs = %s
PersistentKeepalive = 21
""" % (peer['vpn']['wireguard']['Address'],peer['vpn']['wireguard']['keys']['private'],app.wireguard_users_keys['public'],endpoint,peer['vpn']['wireguard']['AllowedIPs'])

    def get_wireguard_install_script(self,endpoint,peer,os):
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