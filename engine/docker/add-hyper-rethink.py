import os, time
from pprint import pprint
import traceback

from rethinkdb import RethinkDB; r = RethinkDB()
from rethinkdb.errors import ReqlDriverError, ReqlTimeoutError

import logging as log

from subprocess import check_call, check_output

def dbConnect():
    r.connect(host=os.environ['STATS_RETHINKDB_HOST'], port=os.environ['STATS_RETHINKDB_PORT'],db=os.environ['RETHINKDB_DB']).repl()

def add_hyper_keys(hyper,user,password,port):
    check_output(('/add-hypervisor.sh', 'HYPERVISOR='+hyper, 'USER='+user, 'PASSWORD='+password, +'PORT='+port), text=True).strip()

while True:
    try:
        # App was restarted or db was lost. Just sync peers before get into changes.
        print('Checking initial config...')
        dbConnect()
        
        

        print('Config regenerated from database...\nStarting to monitor users changes...')
        #for user in r.table('users').pluck('id','vpn').changes(include_initial=False).run():
        for hyp in r.table('hypervisors').changes(include_initial=False)).run():
            if user['new_val'] == None:

    except ReqlDriverError:
        print('Users: Rethink db connection lost!')
        log.error('Users: Rethink db connection lost!')
        time.sleep(.5)
    except Exception as e:
        print('Users internal error: \n'+traceback.format_exc())
        log.error('Users internal error: \n'+traceback.format_exc())
        exit(1)