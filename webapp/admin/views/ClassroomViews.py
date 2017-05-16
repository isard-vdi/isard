# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json
import time

from flask import render_template, Response, request, redirect, url_for, send_from_directory
from flask_login import login_required

from webapp import app
from ...lib import admin_api

app.adminapi = admin_api.isardAdmin()

import rethinkdb as r
from ...lib.flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

from .decorators import isAdmin

import random
@app.route('/admin/classroom', methods=['POST','GET'])
@login_required
def admin_classroom():
    if request.method == 'POST':
        None
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
    
    return render_template('admin/pages/classroom.html', nav='Classroom', places=app.adminapi.get_admin_table('places'))
    
#~ {'id':'N2M2,
#~ 'description':'Aula del edificio de electrónica segunda planta',
#~ 'rows':5,
#~ 'cols':4,
#~ 'photo_url':'http://fotos_aulas.escoladeltreball.org/foto_aula_n2m_mini.jpg'
#~ 'enable':True
#~ 'ssh':{
 #~ 'enable':True
 #~ 'user':'root'
 #~ 'pwd':'password_de_root_de_las_aulas',
 #~ 'ssh_key':'/isard/sshkeys/
 #~ }
#~ 'perms':{lo que creas, de tal forma que sólo a un determinado grupo de usuarios
#~ les dejamos que manejen el aula, por ejemplo al grupo profes, o a los profes de elo}
#~ }
