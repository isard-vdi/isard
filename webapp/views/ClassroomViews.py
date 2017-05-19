# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8
from flask import render_template, Response, request, redirect, url_for, stream_with_context, flash
from webapp import app
from flask_login import login_required, login_user, logout_user, current_user
import time
import json

from ..lib.log import *

import rethinkdb as r
from ..lib.flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

from .decorators import ownsid

import random
@app.route('/classroom', methods=['POST','GET'])
@login_required
def classroom():
    if request.method == 'POST':
        None
    hosts={}
    
    for r in range(1,6):
        hosts[r]={}
        for c in range(1,random.randrange(4,8)):
            hosts[r][c]={'status':random.randrange(0,3),'ip':'10.200.210.'+str(r+c),'hostname':'f2a-'+str(r+c)}
    
    return render_template('pages/classroom.html', nav='Classroom', hosts=hosts)

@app.route('/classroom_users', methods=['POST','GET'])
@login_required
def classroom_users():
    if request.method == 'POST':
        # Users from dropdown
        None
    return render_template('pages/classroom_users.html', nav='Classroom', users=app.isardapi.get_group_users('hisx1',['id','name','username']))

import random
@app.route('/classroom_test', methods=['POST','GET'])
@login_required
def classroom_test():
    #~ if request.method == 'POST':
        #~ None
    #~ users=app.isardapi.get_group_users('hisx1',['id','name','username'])
    #~ print(len(users))
    #~ print(len(users)/6)
    #~ print(int(len(users)/6) + (len(users) % 6 > 0))
    #~ host = {
           #~ 'hostname'   : 'n2m05',
           #~ 'place_id'   : 'n2m',
           #~ 'ip'         : '10.200.212.201',
           #~ 'description': 'n2m 05',
           #~ 'mac'        : '01:02:03:04:05:06',
           #~ 'enable'     : True,
           #~ 'status'     : 'Offline', #Offline, online, ready_to_launch_ssh_commands
           #~ 'login_user' : None,
           #~ 'desktops_running':[],
           #~ 'online_date': '2017/05/05 13:23:04'}

    #~ hosts={}
    #~ i=0
    #~ for r in range(0,int(len(users)/6) + (len(users) % 6 > 0)):
        #~ hosts[r]={}
        #~ for c in range(0,6):
            #~ print(str(i)+' '+str(len(users)))
            #~ if i == len(users): break
            #~ hosts[r][c]={'status':random.randrange(0,3),'ip':users[i]['id'],'hostname':users[i]['name']}
            #~ i=i+1
            
    
    #~ for r in range(0,6):
        #~ hosts[r]={}
        #~ for c in range(0,random.randrange(4,8)):
            #~ hosts[r][c]={'status':random.randrange(0,3),'ip':'10.200.210.'+str(r+c),'hostname':'f2a-'+str(r+c)}
    items=app.isardapi.get_hosts_viewers('PROVA1')
    return render_template('pages/classroom_test.html', nav='Classroom', hosts=hosts)
