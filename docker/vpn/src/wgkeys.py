
from pprint import pprint

import os
from rethinkdb import RethinkDB; r = RethinkDB()
from rethinkdb.errors import ReqlDriverError, ReqlTimeoutError

from subprocess import check_call, check_output
import ipaddress
import traceback

class Keys(object):
    def __init__(self,interface='wg0'):
        self.interface=interface
        self.wg = '/usr/bin/wg'
        self.skeys={'private':False, 'public':False}
        self.update_clients=False
        self.check_server_cert()

    def gen_private_key(self):
        return check_output((self.wg, 'genkey'), text=True).strip()

    def gen_public_key(self, private_key):
        return check_output((self.wg, 'pubkey'), input=private_key, text=True).strip()  

    def gen_server_keys(self):
        ## Private goes in wg0.conf [Interface] config
        self.skeys['private']=self.gen_private_key()
        ## Public goes in all client config [Peer]
        self.skeys['public']=self.gen_public_key(self.skeys['private'])     

    def new_client_keys(self):
        private=self.gen_private_key()
        return {'private':private,
                'public':self.gen_public_key(private)}

    def gen_presharedkey(self):
        return check_output((self.wg, 'genpsk'), text=True).strip()

    def check_server_cert(self):
        # Check old server key with new server key that matches.
        # If new key found then all client keys should be updated!
        update_clients=False

        try:
            with open("/certs/"+self.interface+"_private.key", "r") as f:
                actual_private_key=f.read()
            with open("/certs/"+self.interface+"_public.key", "r") as f:
                actual_public_key=f.read()
        except FileNotFoundError:
            self.gen_server_keys()
            actual_private_key=self.skeys['private']
            actual_public_key=self.skeys['public']
            ## Generate new ones
        except Exception as e:
            print('Serve read keys error: \n'+traceback.format_exc())
            log.error('Server read keys internal error: \n'+traceback.format_exc())
            exit(1)

        old_key=r.table('config').get(1).pluck('vpn_'+self.interface).run()

        if 'vpn' not in old_key.keys() or actual_private_key != old_key['vpn_'+self.interface]['wireguard']['keys']['private']:
            r.table('config').get(1).update({'vpn_'+self.interface:{'wireguard':{'keys':{'private':actual_private_key,
                                                                        'public':actual_public_key}}}}).run()
            update_clients=True
            try:
                with open("/certs/"+self.interface+"_private.key", "w") as f:
                    f.write(actual_private_key)
                with open("/certs/"+self.interface+"_public.key", "w") as f:
                    f.write(actual_public_key)
            except Exception as e:
                print('Serve keys write error: \n'+traceback.format_exc())
                log.error('Server write keys internal error: \n'+traceback.format_exc())    
                exit(1)            
        self.skeys={'private':actual_private_key,
                    'public':actual_public_key}
        self.update_clients=update_clients
