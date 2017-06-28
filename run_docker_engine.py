import rethinkdb as r
from time import sleep

online=False
while not online:
    try:
        r.connect( "rethinkdb-container", 28015).repl()
        r.db('isard').table('config').get(1).run()
        online=True
        print('Rethinkdb database isard populated. Starting engine.')
    except Exception as e:
        print('Database still down or config table not present, retrying in 2 seconds')
        sleep(2)


from engine.manager_hypervisors import ManagerHypervisors
from engine.functions import get_threads_running
from engine.functions import check_tables_populated
from api import app
from engine import db

from gevent.wsgi import WSGIServer

check_tables_populated()
app.m = ManagerHypervisors()
app.db = db
# sleep(10)
# get_threads_running()


def run():
    http_server = WSGIServer(('0.0.0.0', 5555), app)
    http_server.serve_forever()

# if app.debug:
#     from werkzeug.debug import DebuggedApplication
#     app.wsgi_app = DebuggedApplication( app.wsgi_app, True )

if __name__ == "__main__":
    run()
