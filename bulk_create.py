from engine.db import insert_domain
import pprint
import sys

DICT_CREATE_WIN7={'allowed': {'categories': False,
             'groups': False,
             'roles': False,
             'users': False},
 'category': 'testing',
 'create_dict': {'hardware': {'boot_order': ['disk'],
                              'disks': [{'file': 'testing/test_users/test1/prova_win7.qcow2',
                                         'parent': '/vimet/bases/windows_7v3.qcow2'}],
                              'graphics': ['default'],
                              'interfaces': ['default'],
                              'memory': 2500000,
                              'vcpus': 2,
                              'videos': ['default']},
                 'origin': '_windows_7_x64_v3'},
 'description': '',
 'detail': None,
 'group': 'test_users',
 'hypervisors_pools': ['default'],
 'icon': 'windows',
 'id': '_test1_prova_win7',
 'kind': 'desktop',
 'name': 'prova win7',
 'os': 'windows',
 'server': False,
 'status': 'Creating',
 'user': 'test1',
 'xml': None}


DICT_CREATE = DICT_CREATE_WIN7.copy()
PREFIX = 'maquina_prova'
NUM_BULK = int(sys.argv[1])
disk_path=DICT_CREATE['create_dict']['hardware']['disks'][0]['file']
name = DICT_CREATE['id']
for i in range(1,1+NUM_BULK):
    id_domain = '{}_{}'.format(PREFIX,str(i).zfill(2))
    d = DICT_CREATE.copy()

    d['create_dict']['hardware']['disks'][0]['file']=disk_path.replace('prova_win7.qcow',id_domain + '.qcow')
    d['id'] = name.replace('prova_win7',id_domain)
    d['name'] = id_domain

    pprint.pprint(d)
    insert_domain(d)


        

