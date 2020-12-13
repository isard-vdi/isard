
from pprint import pprint

import os
from rethinkdb import RethinkDB; r = RethinkDB()
from rethinkdb.errors import ReqlDriverError, ReqlTimeoutError

from subprocess import check_call, check_output
import ipaddress
import traceback

import iptc

REJECT={'target': {'REJECT': {'reject-with': 'icmp-host-prohibited'}}}

class IpTools(object):
    def __init__(self):
        None

    def add_rule(self, rule, table=iptc.Table.FILTER, chain='FORWARD'):
        table = iptc.Table(table)
        chain = iptc.Chain(table, chain)
        rule = iptc.easy.encode_iptc_rule(rule)
        chain.insert_rule(rule) 

    def add_chain(self, name, table=iptc.Table.FILTER):
        table = iptc.Table(table)
        if table.is_chain(name): return
        chain = table.create_chain(name)

    def add_dependency_chain(self, child, parent, table=iptc.Table.FILTER):
        table = iptc.Table(table)
        chain = iptc.Chain(table, child)
        rule = iptc.Rule()
        rule.target = iptc.Target(rule, parent)
        chain.insert_rule(rule)
        #iptables -A user-name -j fw-users

    def reject_chain(self, chain):
        self.add_rule(REJECT,chain=chain)

    def flush_chains(self,table=iptc.Table.FILTER):
        table = iptc.Table(table)
        table.flush()

    def flush_rules(self,chain,table=iptc.Table.FILTER):
        table = iptc.Table(table)
        if table.is_chain(chain):
            chain = iptc.Chain(table, chain)
            chain.flush()

    def delete_rule(self,chain,src=False,dst=False,table=iptc.Table.FILTER):
        table = iptc.Table(table)
        table.autocommit = False
        chain = iptc.Chain(table, chain)
        for rule in chain.rules:
            if rule.src and src in rule.src:
                chain.delete_rule(rule)
            if rule.src and src in rule.src:
                chain.delete_rule(rule)
        table.commit()
        table.autocommit = True
