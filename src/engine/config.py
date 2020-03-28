# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

#/bin/python3
# coding=utf-8

# Y ahora usamos la otra librería

# import os
# dir = os.path.dirname(__file__)
# file_conf = os.path.join(dir,'../config/isard.conf')
#
# from configparser import ConfigParser
#
# c=ConfigParser()
# c.read(file_conf)

import rethinkdb as r
import configparser
import os, time
# ~ try:

# ~ except Exception as e:
    # ~ log.info('The isard.conf file can not be opened. Please start webapp UI interface before engine.')
    # ~ sys.exit(0)

config_exists=False
first_loop = True
fail_first_loop = False
while not config_exists:
    try:
        rcfg = configparser.ConfigParser()
        rcfg.read(os.path.join(os.path.dirname(__file__),'../isard.conf'))        
        RETHINK_HOST = rcfg.get('RETHINKDB', 'HOST')
        RETHINK_PORT = rcfg.get('RETHINKDB', 'PORT')
        RETHINK_DB   = rcfg.get('RETHINKDB', 'DBNAME')
        if fail_first_loop:
            print('ENGINE STARTING, isard.conf accesed')
        config_exists=True
    except:
        if first_loop is True:
            print('ENGINE START PENDING: Missing isard.conf file. Run webapp and access to http://localhost:5000 or https://localhost on dockers.')
            first_loop = False
            fail_first_loop = True
        time.sleep(1)

first_loop = True
fail_first_loop = False
table_exists=False
while not table_exists:
    try:
        with r.connect(host=RETHINK_HOST, port=RETHINK_PORT) as conn:
            rconfig = r.db(RETHINK_DB).table('config').get(1).run(conn)
            #grafana= rconfig['engine']['grafana']
            rconfig = rconfig['engine']
            r.db('isard').wait(wait_for='all_replicas_ready').run(conn)
        table_exists=True
        if fail_first_loop:
            print('ENGINE STARTING, database is online')
    except:
        if first_loop is True:
            print('ENGINE START PENDING: Missing database isard. Run webapp and access to http://localhost:5000 or https://localhost on dockers.')
            first_loop = False
            fail_first_loop = True
        time.sleep(1)
#print(rconfig)


MAX_QUEUE_DOMAINS_STATUS = rconfig['stats']['max_queue_domains_status']
STATUS_POLLING_INTERVAL = rconfig['intervals']['status_polling']
TIME_BETWEEN_POLLING = rconfig['intervals']['time_between_polling']
TEST_HYP_FAIL_INTERVAL = rconfig['intervals']['test_hyp_fail']
POLLING_INTERVAL_BACKGROUND = rconfig['intervals']['background_polling']
POLLING_INTERVAL_TRANSITIONAL_STATES = rconfig['intervals']['transitional_states_polling']
#GRAFANA = grafana

TRANSITIONAL_STATUS = ('Starting', 'Stopping', 'Deleting')

# CONFIG_DICT = {k: {l[0]:l[1] for l in c.items(k)} for k in c.sections()}

CONFIG_DICT = {
'RETHINKDB':{
'host':         RETHINK_HOST,
'port':         RETHINK_PORT,
'dbname':       RETHINK_DB
},

    # This is important if you want to protect to man in the midle attack
    # but paramiko have a problem with ecdsa keys that is implemented in
    # modern distributions like fedora or debian. Ecdsa keys are not supported (yet) with paramiko
    # If you want to use this host key checking, this kind of keys must be
    # disabled from sshd config by commenting out a single line in /etc/ssh/sshd_config
    #  # HostKey /etc/ssh/ssh_host_ecdsa_key
    #  # HostKey /etc/ssh/ssh_host_ed25519_key
    # and only this line must be active:
    # HostKey /etc/ssh/ssh_host_rsa_key

    # If you can not modify this behaviour in your hypervisors,
    # or man in the midle attacks with ssh aren't a problem in your
    # network
    # this parameter must be False

'SSH': rconfig['ssh'],
'STATS': rconfig['stats'],
'LOG': rconfig['log'],
'TIMEOUTS':rconfig['timeouts'],

'REMOTEOPERATIONS':{
'host_remote_disk_operatinos': 'localhost',
'default_group_dir': '/opt/isard/groups/'
},
'FERRARY':{
'prefix': '__f_',
'dir_to_ferrary_disks': '/opt/isard/groups/ferrary'
}
}

#INFO TO DEVELOPER, REVISAR PORQUE NO SE USA, HAY QUE MIRAR LO
#QUE HAY EN EL DIAGRMAA DE GOOGLE DRIVE Y CODIFICARLO
STATUS_DOMAIN_DEFINED=['stopped',
                       'starting',
                       'stopping',
                       'started',
                       'unknown',
                       'paused',
                       'failed',
                       'creating',
                       'failed_creating',
                       'blocked',
                       'deleting',
                       'deleted',
                       'modifying',
                       'creating_template'
                       ]

TESTS = {
         'HYPS_TO_TEST_OK':['vdesktop1','vdesktop2','vdesktop3','vdesktop4'],
    #INFO TO DEVELOPER, DE MOMENTO ESTO NO SE USA...
         'HYP_TO_TEST_NOT_IN_DB':['notindbhyp'],
         'HYP_TO_TEST_INSERT_IN_DB_THEN_FAIL_DNS':[
               {'id': 'hyp_fail_ssh',
                "hostname":  "127.0.0.1" ,
                "pools": [
                "default"
                ],
                "port":  "22",
                "status":  "Offline",
                "user":  "root"
                }]
}
