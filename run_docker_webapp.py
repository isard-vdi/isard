import rethinkdb as r
import time
online=False
while not online:
    try:
        r.connect( "rethinkdb-container", 28015).repl()
        online=True
        print('Rethinkdb database container up. Starting webapp.')
    except Exception as e:
        print('Database still down, retrying in 2 seconds')
        time.sleep(2)

from gevent import monkey
monkey.patch_all()

from flask_socketio import SocketIO, emit, join_room, leave_room, \
    close_room, rooms, disconnect, send

from webapp.lib import api
from webapp import app

#import rethinkdb as r
from webapp.lib.flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

socketio = SocketIO(app)
#~ threads = {}

app.isardapi = api.isard()

from webapp.lib import isardSocketio


## Main
if __name__ == '__main__':
    isardSocketio.start_domains_thread()
    isardSocketio.start_domains_status_thread()
    isardSocketio.start_users_thread()
    isardSocketio.start_hypervisors_thread()
    isardSocketio.start_config_thread()
    
    import logging
    logger=logging.getLogger("socketio")
    #~ level = logging.getLevelName('ERROR')
    logger.setLevel('ERROR')
    engineio_logger=logging.getLogger("engineio")
    engineio_logger.setLevel('ERROR')
    socketio.run(app,host='0.0.0.0', port=5000, debug=False, logger=logger, engineio_logger=engineio_logger)
