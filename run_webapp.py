from gevent import monkey
monkey.patch_all()

#~ import time
#~ import json
#~ import threading
#~ from flask import Flask, render_template, session, request
#~ from flask_login import login_required, login_user, logout_user, current_user
from flask_socketio import SocketIO, emit, join_room, leave_room, \
    close_room, rooms, disconnect, send

from webapp.lib import api
from webapp import app

import rethinkdb as r
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
    socketio.run(app,host='0.0.0.0', port=5000, debug=True, logger=logger, engineio_logger=engineio_logger)
