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

RETHINK_HOST = 'localhost'
RETHINK_PORT = 28015
STATUS_POLLING_INTERVAL = 10
RETHINK_DB   = 'isard'

TIME_BETWEEN_POLLING = 5
TEST_HYP_FAIL_INTERVAL = 20
POLLING_INTERVAL_BACKGROUND = 10
POLLING_INTERVAL_TRANSITIONAL_STATES = 2
TRANSITIONAL_STATUS = ('Starting', 'Stopping')

# CONFIG_DICT = {k: {l[0]:l[1] for l in c.items(k)} for k in c.sections()}

CONFIG_DICT = {
'RETHINKDB':{
'host':			'localhost',
'port':			'28015',
'dbname':		'isard'
},



'SSH': {
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
    'paramiko_host_key_policy_check' : False
},

'STATS':{
'max_queue_domains_status': 10,
'max_queue_hyps_status': 10,
'hyp_stats_interval': 5
},

'LOG':{
'log_name':  'isard',
'log_level': 'DEBUG',
'log_file':  'msg.log'
},

'TIMEOUTS':{
'ssh_paramiko_hyp_test_connection':   4,
'timeout_trying_ssh': 2,
'timeout_trying_hyp_and_ssh': 10,
'timeout_queues': 2,
'timeout_hypervisor': 10,
'libvirt_hypervisor_timeout_connection': 3,
'timeout_between_retries_hyp_is_alive': 1,
'retries_hyp_is_alive': 3
},

'REMOTEOPERATIONS':{
'host_remote_disk_operatinos': 'vdesktop1.escoladeltreball.org',
'default_group_dir': '/vimet/groups/a'
},
'FERRARY':{
'prefix': '__f_',
'dir_to_ferrary_disks': '/vimet/groups/ferrary'
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