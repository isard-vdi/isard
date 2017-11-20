from gevent.wsgi import WSGIServer

from api import app
from engine.models.manager_hypervisors import ManagerHypervisors
from engine.services import db
from engine.services.lib.functions import check_tables_populated

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