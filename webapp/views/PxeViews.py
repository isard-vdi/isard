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

# ~ import secrets
import time,json

class usrTokens():
    def __init__(self):
        self.tokens={}
        self.valid_seconds = 120

    def add(self,usr):
        # ~ tkn=secrets.token_urlsafe(32)
        tkn="oqwefj0w9jfw0eijfwaeifj"
        self.tokens[tkn]={"usr":usr,"timestamp":time.time()}
        return tkn
        # we should check other tokens for expiry time

    def valid(self,tkn):
        if tkn in self.tokens.keys():
            if time.time()-self.tokens[tkn]['timestamp']<self.valid_seconds:
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
        return [{'id':'_id1_dom1','name':'Domain1'},{'id':'_id2_dom2','name':'Domain2'}]


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
        return json.dumps({"vms":domains}), 200, {'ContentType': 'application/json'}
    return json.dumps({"vms":""}), 403, {'ContentType': 'application/json'}
   
    # ~ res={"token":""} 
    # ~ code=401
    # ~ if user:
        # ~ login_user(user)
        # ~ res['token']=secrets.token_bytes(16) 
        # ~ code=200
    # ~ return json.dumps(res), code, {'ContentType': 'application/json'} 


#START: POST
#VIEWER
