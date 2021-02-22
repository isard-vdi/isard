
from pprint import pprint

import os
from rethinkdb import RethinkDB; r = RethinkDB()
from rethinkdb.errors import ReqlDriverError, ReqlTimeoutError

from subprocess import check_call, check_output
import ipaddress
import traceback

import iptc

def test():

    decode = {'filter': {'FORWARD': [{'counters': (0, 0),
                         'in-interface': 'wg0',
                         'out-interface': 'wg0',
                         'target': {'REJECT': {'reject-with': 'icmp-host-prohibited'}}}]}}
    return iptc.easy.encode_iptc_rule(decode)
    rule = {'comment': {'comment': 'Match tcp.22'}, 
        'protocol': 'tcp', 
        'target': 'ACCEPT', 
        'tcp': {'dport': '22'}}


def delete(table,chain,interface):
    if table == 'filter':
        table = iptc.Table(iptc.Table.FILTER)
    table.autocommit = False
    chain = iptc.Chain(table, "FORWARD")
    for rule in chain.rules:
        if rule.out_interface and "eth0" in rule.out_interface:
            chain.delete_rule(rule)
    table.commit()
    table.autocommit = True

def lookup(table,chain,lookup_rule):
    if table == 'filter':
        table = iptc.Table(iptc.Table.FILTER)
    table.autocommit = False
    chain = iptc.Chain(table, "FORWARD")
    for rule in chain.rules:
        ruledict = iptc.easy.decode_iptc_rule(rule)
        del ruledict['counters']
        pprint(ruledict)
        pprint(lookup_rule)
        if iptc.easy.decode_iptc_rule(rule) == lookup_rule:
            print('match')
            #chain.delete_rule(rule)
    #table.commit()
    #table.autocommit = True

def new_chain(name):
    table = iptc.Table(iptc.Table.FILTER)
    chain = table.create_chain(name)

    
postup = {'users':{'table': 'filter',
                    'chain': 'FORWARD',
                    'rule':{'in-interface': 'users',
                            'out-interface': 'users',
                            'target': {'REJECT': {'reject-with': 'icmp-host-prohibited'}}
                            }
                    }
        }
        #postup[kind]

for kind in postup.keys():
    print(kind)
    if postup[kind]['table'] == 'filter':
        table = iptc.Table(iptc.Table.FILTER)
    chain = iptc.Chain(table, postup[kind]['chain'])
    rule =  iptc.easy.encode_iptc_rule(postup[kind]['rule'])
    chain.insert_rule(rule)
    lookup('filter','FORWARD',postup['users']['rule'])


#pprint(iptc.easy.dump_all())
exit(0)

chain = iptc.Chain(iptc.Table(iptc.Table.FILTER), "FORWARD")
rule = iptc.Rule()
rule.in_interface = "users"
rule.out_interface = "users"
#rule.src = "127.0.0.1/255.0.0.0"
target = iptc.Target(rule, "REJECT")
rule.target = target
#pprint(iptc.easy.decode_iptc_rule(rule))
#chain.insert_rule(rule)

new_rule = test()
pprint(iptc.easy.decode_iptc_rule(new_rule))


    
    