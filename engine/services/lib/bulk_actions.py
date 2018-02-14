# Copyright 2018 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import re
from pprint import pprint


from engine.services.db import get_domain, get_user, insert_domain
from engine.services.log import log,logs

def create_domain_from_template(name_normalized,
                                    id_template,
                                    id_user,
                                    description = '',
                                    only_dict = False):

    regex = re.compile("^[a-zA-Z0-9-_.]*$")
    if regex.match(name_normalized) is None:
        logs.bulk.error('name {} for domain is not normalized, only lower chars, letters and _ are allowed'.format(name_normalized))
        return False

    id_new_domain = '_' + id_user + '_' + name_normalized

    dict_template = t = get_domain(id_template)
    if dict_template is None:
        logs.bulk.error('template {} does not exist in database'.format(id_template))
        return False
    if dict_template['kind'] == 'desktop':
        logs.bulk.error('domain {} is a desktop, can not derivate from a desktop only from template or base'.format(id_template))
        return False

    if get_domain(id_new_domain) is not None:
        logs.bulk.error('domain {} can not be created because it already exists in database'.format(id_new_domain))
        return False

    dict_user = u = get_user(id_user)
    if dict_user is None:
        logs.bulk.error('user {} does not exist in database, can not create domains '.format(id_user))
        return False

    d_new = {}
    d_new["allowed"] = {"categories": False,
                        "groups": False,
                        "roles": False,
                        "users": False
                        }
    d_new['category'] = u['category']
    d_new['create_dict'] = t['create_dict']
    d_new['description'] = description
    d_new['detail'] = ''
    d_new['group'] = u['group']
    d_new['hypervisors_pools'] = t['hypervisors_pools']
    d_new['icon'] = t['icon']
    d_new['id'] = id_new_domain
    d_new['kind'] = 'desktop'
    d_new['name'] = name_normalized
    d_new['os'] = t['os']
    d_new['server'] = False
    d_new['status'] = 'Creating'
    d_new['user'] = id_user
    d_new['xml'] = ''


    # modify create_dict

    path_relative_disk = '{}/{}/{}/{}.qcow2'.format(u['category'], u['group'], id_user, name_normalized)

    d_new['create_dict']['origin'] = id_template

    try:
        d_new['create_dict'].pop('hypervisors_pools')
    except KeyError:
        pass

    d_new['create_dict']['hardware']['disks'][0]['parent'] = t['hardware']['disks'][0]['file']
    d_new['create_dict']['hardware']['disks'][0]['file'] = path_relative_disk

    if only_dict is True:
        return d_new
    else:
        result = insert_domain(d_new)
        if result['inserted'] == 1:
            logs.bulk.info('domain {} created from bulk operation'.format(id_new_domain))
            return True
        else:
            logs.bulk.error('error inserting domain {} in database'.format(id_new_domain))
            return False

##delete all domains and disks forced
