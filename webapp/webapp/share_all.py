import requests
from rethinkdb import r, ReqlTimeoutError
r.connect('isard-db', 28015).repl()

def activate_shares():
        try:
            r.db('isard').table('config').get(1).update({'shares':{'templates': True, 'isos':True}}).run()
            print("Shares between categories activated")
        except Exception as e:
            print("Error activating shares.\n"+str(e))

activate_shares()
print('Webapp docker service needs to be restarted to apply changes: docker restart isard-webapp')
