
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
        self.flush_chains()
        self.set_default_policy()
        self.init_domains_started()

    def init_domains_started(self):
        domains_started= r.table('domains').get_all('Started',index='status').pluck('id','user','vpn','status',{'viewer':'guest_ip'}).run()
        for ds in domains_started:
            if 'guest_ip' in ds['viewer'].keys():
                self.desktop_add(ds['user'],ds['viewer']['guest_ip'])

    def desktop_add(self,user_id,desktop_ip):
        try:
            user_addr=r.table('users').get(user_id).pluck({'vpn':{'wireguard':'Address'}}).run()['vpn']['wireguard']['Address']
        except Exception as e:
            print('EXCEPTION READING USERS: '+str(e))
            return

        check_output(('/sbin/iptables','-A','FORWARD','-s',user_addr,'-d',desktop_ip,'-j','ACCEPT'), text=True).strip()
        check_output(('/sbin/iptables','-A','FORWARD','-d',user_addr,'-s',desktop_ip,'-j','ACCEPT'), text=True).strip()
        return

    def desktop_remove(self,user_id,desktop_ip):
        try:
            user_addr=r.table('users').get(user_id).pluck({'vpn':{'wireguard':'Address'}}).run()['vpn']['wireguard']['Address']
        except Exception as e:
            print('EXCEPTION READING USERS: '+e)
            return

        check_output(('/sbin/iptables','-D','FORWARD','-s',user_addr,'-d',desktop_ip,'-j','ACCEPT'), text=True).strip()
        check_output(('/sbin/iptables','-D','FORWARD','-d',user_addr,'-s',desktop_ip,'-j','ACCEPT'), text=True).strip()
        return

    def add_rule(self, rule, table=iptc.Table.FILTER, chain='FORWARD'):
        table = iptc.Table(table)
        chain = iptc.Chain(table, chain)
        rule = iptc.easy.encode_iptc_rule(rule)
        chain.insert_rule(rule) 


    def set_default_policy(self):
        check_output(('/sbin/iptables','-P','FORWARD','DROP'), text=True).strip()

    def flush_chains(self):
        check_output(('/sbin/iptables','-F','FORWARD'), text=True).strip()

    def wireguard_default_postup(self):
        str="iptables -I FORWARD -i wg0 -o wg0 -j REJECT --reject-with icmp-host-prohibited"
