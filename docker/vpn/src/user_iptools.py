
from pprint import pprint

import os
from rethinkdb import RethinkDB; r = RethinkDB()
from rethinkdb.errors import ReqlDriverError, ReqlTimeoutError

from subprocess import check_call, check_output
import ipaddress
import traceback

import iptc

REJECT={'target': {'REJECT': {'reject-with': 'icmp-host-prohibited'}}}

class UserIpTools(object):
    def __init__(self):
        self.userdesktops={}
        self.flush_chains()
        self.init_users_chains()
        self.init_domains_started()

    def init_users_chains(self):
        iptc.easy.add_chain('filter', 'fw-users')
        iptc.easy.insert_rule('filter', 'fw-users', REJECT)

        iptc.easy.add_chain('filter', 'fw-vpn')
        rule={'src':'10.0.0.0/255.255.0.0',
              'target': 'fw-users'}
        iptc.easy.insert_rule('filter', 'fw-vpn', rule)

        print('XXXXXXXXXXXXXXXXXX Initial users iptables')
        pprint(iptc.easy.dump_table('filter', ipv6=False))
        print('XXXXXXXXXXXXXXXXXX')

    def init_domains_started(self):
        domains_started= r.table('domains').get_all('Started',index='status').pluck('id','user','vpn','status',{'viewer':'guest_ip'}).run()
        for ds in domains_started:
            if 'guest_ip' in ds['viewer'].keys():
                self.desktop_add(ds['user'],ds['viewer']['guest_ip'])
        

    def get_tables(self):
        return iptc.easy.dump_table('filter', ipv6=False)

    def user_desktop_add(self,user_id,desktop_id):
        if user_id in self.userdesktops.keys():
            self.userdesktops[user_id].add(desktop_id)
        else:
            self.userdesktops[user_id]=set([desktop_id])
            self._add_user(user_id)
    
    def user_desktop_remove(self,user_id,desktop_id):
        pprint(self.userdesktops)
        if user_id in self.userdesktops.keys():
            print(self.userdesktops[user_id])
            self.userdesktops[user_id]=set(self.userdesktops[user_id]).difference([desktop_id])
            print(self.userdesktops[user_id])
            if len(self.userdesktops[user_id]) == 0:
                self._del_user(user_id)

    def _add_user(self,id,src=False):
        #iptables -A fw-beto -j fw-users
        try:
            user_addr=r.table('users').get(id).pluck({'vpn':{'wireguard':'Address'}}).run()['vpn']['wireguard']['Address']
        except Exception as e:
            print('EXCEPTION READING USERS: '+e)
            return
        iptc.easy.add_chain('filter', 'fw-'+id)
        rule={'target': 'fw-'+id}
        iptc.easy.insert_rule('filter', 'fw-users', rule)
        rule={'src':user_addr,
            'target': 'fw-'+id}
        iptc.easy.insert_rule('filter', 'fw-vpn', rule)

        print('user iptables added')
        #iptables -I fw-vpn -s 10.1.2.3 -j fw-beto

    def _del_user(self,id):
        #self.delete_user_chain(id)
        iptc.easy.delete_chain('filter', 'fw-'+id, flush=True)
        print('user iptables deleted')

    def desktop_add(self,user_id,desktop_ip):
        pprint(iptc.easy.dump_table('filter', ipv6=False))
        self.user_desktop_add(user_id,desktop_ip)
        pprint(iptc.easy.dump_table('filter', ipv6=False))
        rule={'dst':desktop_ip,
            'target': 'fw-'+user_id}
        pprint(rule)
        iptc.easy.insert_rule('filter', 'fw-vpn', rule)
        print('desktop iptables added')

    def desktop_remove(self,user_id,desktop_ip):
        self.delete_rule('fw-vpn',dst=desktop_ip)
        self.user_desktop_remove(user_id,desktop_ip)
        
        print('desktop iptables deleted')



    def delete_user_chain(self,id,table=iptc.Table.FILTER):
        table = iptc.Table(table)
        chains = ['fw-vpn','fw-users',id]
        for ch in chains:
            self.delete_rule(ch,target=id)




    #############Common
    def delete_rule(self,chain,src='',dst='',target='',table=iptc.Table.FILTER):
        table = iptc.Table(table)
        #table.autocommit = False
        chain = iptc.Chain(table, chain)
        for rule in chain.rules:
            if src != '' and rule.src and src in rule.src:
                chain.delete_rule(rule)
            if dst != '' and rule.dst  and dst in rule.dst:

                #pprint(iptc.easy.decode_iptc_rule(rule))
                #pprint(iptc.easy.dump_table('filter', ipv6=False))
                chain.delete_rule(rule)
            if target != '' and rule.target and target in rule.target:
                chain.delete_rule(rule)
        #table.commit()
        #table.autocommit = True

    def flush_chains(self,table=iptc.Table.FILTER):
        table = iptc.Table(table)
        table.flush()

#test=UserIpTools()
