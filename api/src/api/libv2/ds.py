import time
from api import app
from datetime import datetime, timedelta
import pprint

#import pem
#from OpenSSL import crypto

# ~ from contextlib import closing

#import rethinkdb as r
from rethinkdb import RethinkDB; r = RethinkDB()
from rethinkdb.errors import ReqlTimeoutError
# ~ from ..libv1.log import *
import logging as log

from .flask_rethink import RDB
db = RDB(app)
db.init_app(app)

from .apiv2_exc import *

import concurrent.futures

from .helpers import _check

class DS():
    def __init__(self):
        None

    def delete_desktop(self,desktop_id, status):
            if status == 'Started':
                transition_status = 'Stopping'
                final_status = 'Stopped'
                try: 
                    self.WaitStatus(desktop_id, status, transition_status, final_status) 
                    status = 'Stopped'    
                except ReqlTimeoutError:
                    with app.app_context():
                        r.table('domains').get(desktop_id).update({'status':'Failed'}).run(db.conn)
                        status = 'Failed'
                except DesktopWaitFailed:
                    with app.app_context():
                        r.table('domains').get(desktop_id).update({'status':'Failed'}).run(db.conn)
                        status = 'Failed' 

            if status in ['Stopped', 'Failed']:
                transition_status = 'Deleting'
                final_status = 'Deleted'
                try: 
                    self.WaitStatus(desktop_id, status, transition_status, final_status)     
                except ReqlTimeoutError:
                    with app.app_context():
                        r.table('domains').get(desktop_id).delete().run(db.conn)
                except DesktopWaitFailed:
                    with app.app_context():
                        r.table('domains').get(desktop_id).delete().run(db.conn) 
                return

            with app.app_context():
                r.table('domains').get(desktop_id).update({'status':'Failed'}).run(db.conn)
            transition_status = 'Deleting'
            final_status = 'Deleted'

            try: 
                self.WaitStatus(desktop_id, 'Failed', transition_status, final_status)     
            except ReqlTimeoutError:
                with app.app_context():
                    r.table('domains').get(desktop_id).delete().run(db.conn)
            except DesktopWaitFailed:
                with app.app_context():
                    r.table('domains').get(desktop_id).delete().run(db.conn) 

    def delete_non_persistent(self, user_id, template=False):
        ## StoppingAndDeleting all the user's desktops
        if template == False:
            with app.app_context():
                desktops_to_delete = r.table('domains').get_all(user_id, index='user').filter({'persistent':False}).without('create_domain','xml','history_domain').run(db.conn)
        else:
            with app.app_context():
                desktops_to_delete = r.table('domains').get_all(user_id, index='user').filter({'from_template':template,'persistent':False}).without('create_domain','xml','history_domain').run(db.conn)
        for desktop in desktops_to_delete:
            ds.delete_desktop(desktop['id'],desktop['status'])

    def WaitStatus(self, desktop_id, original_status, transition_status, final_status, wait_seconds=10):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(lambda p: self._wait_for_domain_status(*p), [desktop_id, original_status, transition_status, final_status, wait_seconds])
        try:
            result = future.result()
        except ReqlTimeoutError:
            raise DesktopActionTimeout
        except DesktopWaitFailed:
            raise DesktopActionFailed
        return True

    def _wait_for_domain_status(self, desktop_id, original_status, transition_status, final_status, wait_seconds):
        with app.app_context():
            # Prepare changes
            if final_status == 'Deleted':
                changestatus = r.table('domains').get(desktop_id).changes().filter({'new_val': None}).run(db.conn)
            elif final_status == 'Started':
                changestatus = r.table('domains').get(desktop_id).changes().filter({'new_val':{'status':final_status}}).has_fields({'new_val': {'viewer': {'tls':{'host-subject':True}}}}).run(db.conn)
            else:
                changestatus = r.table('domains').get(desktop_id).changes().filter({'new_val':{'status':final_status}}).run(db.conn)

            # Start transition
            if transition_status != 'Any':
                status = r.table('domains').get(desktop_id).update({'status':transition_status}).run(db.conn)
                
                if _check(status,'replaced') == False:
                    raise DesktopPreconditionFailed

            # Get change
            try:
                doc = changestatus.next(wait=wait_seconds)
            except ReqlTimeoutError:
                raise
            if final_status != 'Deleted':
                if doc['new_val']['status'] != final_status:
                    raise DesktopWaitFailed

    def _check(self,dict,action):
        '''
        These are the actions:
        {u'skipped': 0, u'deleted': 1, u'unchanged': 0, u'errors': 0, u'replaced': 0, u'inserted': 0}
        '''
        if dict[action]: 
            return True
        if not dict['errors']: return True
        return False