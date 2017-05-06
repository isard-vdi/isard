from time import sleep
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