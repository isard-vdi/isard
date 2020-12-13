import os, time, ipaddress
from pprint import pprint
import traceback

from rethinkdb import RethinkDB; r = RethinkDB()
from rethinkdb.errors import ReqlDriverError, ReqlTimeoutError, ReqlOpFailedError

import logging as log

from wgtools import Wg



def dbConnect():
    r.connect(host=os.environ['RETHINKDB_HOST'], port=os.environ['RETHINKDB_PORT'],db=os.environ['RETHINKDB_DB']).repl()

while True:
    try:
        # App was restarted or db was lost. Just sync peers before get into changes.
        print('Checking initial config...')
        dbConnect()
        #os.environ['WG_GUESTS_NETS']
        #nparent = ipaddress.ip_network('10.2.0.0/16')
        #xarxes_dhcp= list(nparent.subnets(new_prefix=23))
        #xarxa_inter=xarxes_dhcp[-1]
        #sub = ipaddress.ip_network('10.2.254.0/23')
        #xarxes_inter= list(sub.subnets(new_prefix=29))

        wg_users=Wg(interface='users',clients_net=os.environ['WG_USERS_NET'],table='users',server_port=os.environ['WG_USERS_PORT'],allowed_client_nets=os.environ['WG_GUESTS_NETS'],reset_client_certs=False)
        wg_hypers=Wg(interface='hypers',clients_net=os.environ['WG_HYPERS_NET'],table='hypervisors',server_port=os.environ['WG_HYPERS_PORT'],allowed_client_nets=os.environ['WG_USERS_NET'],reset_client_certs=False)

        print('Config regenerated from database...\nStarting to monitor users changes...')
        #for user in r.table('users').pluck('id','vpn').changes(include_initial=False).run():
        for data in r.table('users').pluck('id','vpn').merge({'table':'users'}).changes(include_initial=False).union(
            r.table('hypervisors').pluck('id','vpn','hypervisor_number').merge({'table':'hypers'}).changes(include_initial=False)).union(
                r.table('domains').pluck('id','user','vpn','status',{'viewer':'guest_ip'}).merge({'table':'domains'}).changes(include_initial=False)).run():

            if data['new_val'] == None:
                ### Was deleted
                if data['old_val']['table'] == 'users':
                    wg_users.remove_peer(data['old_val'])
                elif data['old_val']['table'] == 'hypers':
                    if data['old_val']['id']=='isard-hypervisor': continue
                    wg_hypers.remove_peer(data['old_val'])
                elif data['old_val']['table'] == 'domains':
                    wg_users.desktop_iptables(data)
                continue
            if data['old_val'] == None:
                ### New 
                print('New: '+data['new_val']['id']+'found...')
                if data['new_val']['table'] == 'users':
                    wg_users.add_peer(data['new_val'])
                elif data['old_val']['table'] == 'hypers':
                    if data['new_val']['id']=='isard-hypervisor': continue
                    wg_hypers.add_peer(data['new_val'])
                elif data['old_val']['table'] == 'domains':
                    wg_users.desktop_iptables(data)                    
            else:
                ### Update
                if data['old_val']['table'] in ['users','hypers']:
                    if 'vpn' not in data['old_val']: 
                        continue #Was just added

                    if data['old_val']['vpn']['iptables'] != data['new_val']['vpn']['iptables']:
                        print('Modified iptables')
                        if data['old_val']['table'] == 'users':
                            wg_users.set_iptables(data['new_val'])
                        else:
                            ## Maybe just avoid rules on hypers table?????
                            ## I THINK THIS IS NOT NEEDED
                            if data['new_val']['id']=='isard-hypervisor': continue
                            wg_hypers.set_iptables(data['new_val'])
                    else:
                        continue
                        print('Modified wireguard config')
                        # who else could modify the wireguard config?? 
                        if data['old_val']['table'] == 'users':
                            wg_users.update_peer(data['new_val'])
                        else:
                            if data['new_val']['id']=='isard-hypervisor': continue
                            wg_hypers.update_peer(data['new_val'])
                elif data['old_val']['table'] == 'domains':
                    wg_users.desktop_iptables(data) 

    except (ReqlDriverError, ReqlOpFailedError):
        print('Users: Rethink db connection missing!')
        log.error('Users: Rethink db connection missing!')
        time.sleep(.5)
    except Exception as e:
        print('Users internal error: \n'+traceback.format_exc())
        log.error('Users internal error: \n'+traceback.format_exc())
        #exit(1)

print('Thread ENDED!!!!!!!')
log.error('Thread ENDED!!!!!!!')  