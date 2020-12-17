import os, time
from pprint import pprint
import traceback

from rethinkdb import RethinkDB; r = RethinkDB()
from rethinkdb.errors import ReqlDriverError, ReqlTimeoutError

import logging as log

from wgtools import Wg


def dbConnect():
    r.connect(host=os.environ['RETHINKDB_HOST'], port=os.environ['RETHINKDB_PORT'],db=os.environ['RETHINKDB_DB']).repl()

while True:
    try:
        dbConnect()
        wg=Wg()
        wg.sync_peers()
        for user in r.table('users').pluck('id','wireguard').changes(include_initial=False).run():
            if user['new_val'] == None:
                wg.remove_peer(user['old_val'])
                print('Deleted user: ')
                pprint(user)
            else:
                if 'vpn' not in user['new_val']:
                    # New user but no vpn set
                    wg.add_peer(user['new_val'])
                else:
                    if user['old_val']['vpn']['iptables'] != user['new_val']['vpn']['iptables']:
                        wg.set_iptables(user['new_val'])
                    
                print('Updated user:')
                pprint(user)
                ### New user or updated

    except ReqlDriverError:
        print('Users: Rethink db connection lost!')
        log.error('Users: Rethink db connection lost!')
        time.sleep(.5)
    except Exception as e:
        print('Users internal error: \n'+traceback.format_exc())
        log.error('Users internal error: \n'+traceback.format_exc())
        
print('Users ENDED!!!!!!!')
log.error('Users ENDED!!!!!!!')  