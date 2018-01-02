# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
from flask import render_template, redirect, request, flash, url_for
#~ from . import wapp
#~ from flask_login import login_required, login_user, logout_user, current_user

#~ from ..auth.authentication import *   
#~ from ..lib.log import *                       

import sys, json, requests, os
public_key='$2b$12$LA4uosV80.jkE430c8.wsOI.xIjQ0om7mpQZ0w/G.atH4/83ySTGW'

@wapp.route('/wizard', methods=['GET'])
#~ if app.config['wizard']==1:
def wizard():
    print(' in wizard')
    return render_template('wizard/wizard_pwd.html')

        #~ @app.route('/wizard', methods=['POST'])
        #~ def wizard():
            #~ if request.method == 'POST':
                #~ log.info(request.form['passwd'])
            #~ log.error('You did a get...')
            #~ return render_template('wizard/wizard_pwd.html')

#~ @wapp.route('/wizard/passwd', methods=['POST'])
#~ def wizard_passwd():
    #~ if request.method == 'POST':
        #~ log.info(request.form['passwd'])
    #~ log.error('You did a get...')
    #~ return render_template('wizard/wizard_pwd.html')


#~ @wapp.route('/wizard/resources', methods=['GET'])
#~ def get_resources():
    #~ return render_template('wizard/wizard_resources.html')
    
#~ @wapp.route('/wizard/get_resources_list', methods=['GET'])
#~ def get_resources_list():
    #~ url='http://isardvdi.com:5050/info'
    #~ try:
        #~ r= requests.post(url, headers={'Authorization':key},allow_redirects=False, verify=False)
        #~ if r.status_code==200:
            #~ return r.json(), 200, {'ContentType':'application/json'}
        #~ else:
            #~ print('wrong')
            #~ return json.dumps('Wrong parameters.'), 500, {'ContentType':'application/json'}
    #~ except Exception as e:
        #~ test_data=[{"id": "winbox.iso", "description": "alsdkj flasdkjf lksadj flkasdjfads l", "kind": "iso", "name": "prova iso"}]
        #~ return json.dumps(test_data), 200, {'ContentType':'application/json'}
        #~ # return json.dumps([]), 200, {'ContentType':'application/json'}
        #~ log.warning('Could not contact isard resources website. Please review your database config.')
        #~ return json.dumps('Could not contact.'), 500, {'ContentType':'application/json'}



#~ '''
#~ TESTS
#~ '''

#~ @wapp.route('/wizard/progress', methods=['GET'])
#~ # if app.config['wizard']==1:
#~ def wizard_progress():
    #~ return render_template('wizard/wizard_progress.html')


