import random

from engine.services.db import get_domain_status, get_domains_from_group, get_all_domains_with_id_and_status, \
    get_domains_from_user
from engine.services.db.db import get_domains_from_classroom, get_domains_running_hypervisor, \
    get_domains_from_template_origin
from engine.services.db.domains import update_domain_status
from engine.services.log import *

MAX_RANDOM = 10


def bulk_create(gr):
    pass


def run_firefox_autologin_user(ip, username):
    if 'autologin' in CONFIG_DICT.keys():
        autologin_secret = CONFIG_DICT['autologin']['autologin_secret']
        site_url = CONFIG_DICT['autologin']['url']
        url = site_url + '/autologin_secret/' + autologin_secret + '/' + username
        cmd_run_firefox = 'firefox {}'.format(url)
    else:
        log.error('autologin options not defined in CONFIG_DICT')


def bulk_action_with_domains(action,
                             groupby,
                             filterby=None,
                             quantity=False,
                             prefix=False,
                             randomize=False,
                             template=None):
    domain_list = get_domain_list_groupby(groupby, filterby, quantity, randomize)
    if action == 'start':
        starting_domain_list = []
        for domain_id in domain_list:
            status = get_domain_status(domain_id)
            if status in ['Stopped', 'Failed']:
                update_domain_status('Starting')
                starting_domain_list.append(domain_id)

        return starting_domain_list


def get_domain_list_groupby(groupby, filterby=None, quantity=None, status=None, randomize=True):
    # role
    # je je ... los que ocupen más disco
    # categoria
    # buscar en estadísticas (fecha de arranque)
    # order by(fecha...)
    # por cuanto tiempo han estado funcionando la última vez
    if groupby == 'classroom':
        domain_list_with_status = get_domains_from_classroom(filterby)
    elif groupby == 'username':
        domain_list_with_status = get_domains_from_user(filterby)
    elif groupby == 'group':
        domain_list_with_status = get_domains_from_group(filterby)
    elif groupby == 'template_origin':
        domain_list_with_status = get_domains_from_template_origin(filterby)
    elif groupby == 'hypervisor':
        domain_list_with_status = get_domains_running_hypervisor(filterby)
    elif groupby == 'all':
        domain_list_with_status = get_all_domains_with_id_and_status(status=status)
        # domain_list_with_status = random.sample(domain_list_with_status,MAX_RANDOM)

    if status is not None:
        domain_list = [{'id': d['id'], 'status': d['status']} for d in domain_list_with_status if d['status'] == status]
    else:
        domain_list = [{'id': d['id'], 'status': d['status']} for d in domain_list_with_status]

    if quantity is not None:
        if randomize is True:
            if len(domain_list) <= quantity:
                random.shuffle(domain_list)
            else:
                domain_list = random.sample(domain_list, quantity)
        else:
            if quantity < len(domain_list):
                domain_list = domain_list[:quantity]

    else:
        if randomize is True:
            random.shuffle(domain_list)

    return domain_list
