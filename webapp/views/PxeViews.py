# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
from flask import render_template, redirect, request, flash, url_for
from webapp import app
from flask_login import login_required, login_user, logout_user, current_user

from ..auth.authentication import *   
from ..lib.log import *    

from ..lib.isardViewer import isardViewer
isardviewer = isardViewer()                   

from uuid import uuid4
import time,json

class usrTokens():
    def __init__(self):
        self.tokens={}
        self.valid_seconds = 60 # Between client accesses to api

    def add(self,usr):
        tkn=str(uuid4())[:32]
        self.tokens[tkn]={"usr":usr,"timestamp":time.time(),"domains":[]}
        return tkn
        # we should check other tokens for expiry time

    def valid(self,tkn):
        if tkn in self.tokens.keys():
            if time.time()-self.tokens[tkn]['timestamp']<self.valid_seconds:
                self.tokens[tkn]['timestamp']=time.time()
                return True
            else:
                self.tokens.pop(tkn,None)
        return False
        
    def login(self,usr,pwd):
        # CHECK IF USR ALREADY IN TOKENS??
        au=auth()
        if au.check(usr,pwd):
            return self.add(usr)
        return False
    
    def domains(self,tkn):
        if not self.valid(tkn):
            return False
        usr_domains=app.isardapi.get_user_domains(self.tokens[tkn]['usr'])
        self.tokens[tkn]['domains']=[{'id':d['id'],'name':d['name'],'status':d['status']} for d in usr_domains]
        return self.tokens[tkn]['domains']

    def start(self,tkn,id):
        if not self.valid(tkn):
            return False
        if not any(d['id'] == id for d in self.tokens[tkn]['domains']):
            return False
        for d in self.tokens[tkn]['domains']:
            if d['id'] == id:
                if d['status'] in ['Stopped','Failed']:
                    app.isardapi.update_table_value('domains', id, 'status', 'Starting')
                    step=0
                    while step<5:
                        status=app.isardapi.get_domain(id)['status']
                        if status is not 'Starting':
                            return status
                        time.sleep(1)
                        step=step+1
                    return status
                elif d['status'] in ['Started']:
                    return d['status']
        return False

    def viewer(self,tkn,id,remote_addr):
        if not self.valid(tkn):
            return False   
        data={"pk":id,"kind":"file"}
        return isardviewer.get_viewer(data,self.tokens[tkn]['usr'],remote_addr)
        # SPICE {'kind':'file','ext':'vv','mime':'application/x-virt-viewer','content':'vv data file'}
        # PC VNC 'vnc','text/plain'
        
tokens=usrTokens() 

@app.route('/pxe/login', methods=['POST'])
def pxe_login():
    # ~ usr = request.args.get('usr')
    # ~ pwd = request.args.get('pwd')
    usr = request.get_json(force=True)['usr']
    pwd = request.get_json(force=True)['pwd']    
    print(usr)
    tkn=tokens.login(usr,pwd)
    if tkn:
        print(tkn)
        return json.dumps({"tkn":tkn}), 200, {'ContentType': 'application/json'} 
    return json.dumps({"tkn":""}), 401, {'ContentType': 'application/json'} 

@app.route('/pxe/list', methods=['GET'])
def pxe_list():
    tkn = request.args.get('tkn')
    domains = tokens.domains(tkn)
    if domains:
        # What happens if user has no domains?
        return json.dumps({"vms":domains}), 200, {'ContentType': 'application/json'}
    return json.dumps({"vms":""}), 403, {'ContentType': 'application/json'}

@app.route('/pxe/start', methods=['POST'])
def pxe_start():
    tkn = request.args.get('tkn')
    id = request.args.get('id')
    res=tokens.start(tkn,id)
    if res is False:
        return json.dumps({"code":0,"msg":"Token expired or not user domain"}), 403, {'ContentType': 'application/json'}
    else:
        if res == 'Started':
            return json.dumps({}), 200, {'ContentType': 'application/json'}
        else:
            if res == 'Failed':
                return json.dumps({"code":2,"msg":"Get domain message for failed..."}), 500, {'ContentType': 'application/json'}
            if res == 'Starting':
                return json.dumps({"code":1,"msg":"Engine seems to be down. Contact administrator."}), 500, {'ContentType': 'application/json'}
        return json.dumps({"code":1,"msg":"Unknown error. Domain status is: "+str(res)}), 500, {'ContentType': 'application/json'}

@app.route('/pxe/viewer', methods=['POST'])
def pxe_viewer():
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    tkn = request.args.get('tkn')
    id = request.args.get('id')
    res=tokens.viewer(tkn,id,remote_addr)
    if res is False:
        return json.dumps({"code":0,"msg":"Token expired or not user domain"}), 403, {'ContentType': 'application/json'}
    else:
        return json.dumps(res), 200, {'ContentType': 'application/json'}
        
