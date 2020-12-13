from gevent import monkey
monkey.patch_all()

from flask_socketio import SocketIO

from webapp.lib import api
from webapp import app

from webapp.lib.flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

socketio = SocketIO(app)

app.isardapi = api.isard()

from webapp.lib import isardSocketio

from webapp.lib import engineMonitor

## Main
if __name__ == '__main__':
    # Start socketio threads
    isardSocketio.start_domains_thread()
    # ~ isardSocketio.start_domains_stats_thread()
    isardSocketio.start_users_thread()
    isardSocketio.start_media_thread()
    isardSocketio.start_hypervisors_thread()
    isardSocketio.start_config_thread()
    isardSocketio.start_resources_thread()

    engineMonitor.start_thread()
    
    import logging
    logger=logging.getLogger("socketio")
    #level = logging.getLevelName('ERROR')
    logger.setLevel('ERROR')
    engineio_logger=logging.getLogger("engineio")
    engineio_logger.setLevel('ERROR')
    #~ import logging
    #~ logging.basicConfig(level=logging.ERROR)
    #~ logger = logging.getLogger(__name__)    
    #~ socketio.run(app,host='0.0.0.0', port=5000, debug=False) #, engineio_logger=engineio_logger)


    #~ import logging
    #~ logger=logging.getLogger("socketio")
    #~ #level = logging.getLevelName('ERROR')
    #~ logger.setLevel('ERROR')
    #~ engineio_logger=logging.getLogger("engineio")
    #~ engineio_logger.setLevel('ERROR')
    socketio.run(app,host='0.0.0.0', port=5000, debug=False) #, logger=logger, engineio_logger=engineio_logger)
