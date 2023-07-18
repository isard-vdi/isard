from gevent import monkey

monkey.patch_all()

import logging
import os

import api.libv2.log
from api.libv2 import (
    api_admin_socketio,
    api_socketio_deployments,
    api_socketio_domains,
    api_socketio_media,
)
from api.libv2.bookings import api_socketio_bookings, api_socketio_plannings
from api.libv2.maintenance import Maintenance

from api import app, socketio

debug = os.environ.get("USAGE", "production") == "devel"

if __name__ == "__main__":
    Maintenance.initialization()
    # Frontend users websockets
    api_socketio_domains.start_domains_thread()
    api_socketio_deployments.start_deployments_thread()
    api_socketio_bookings.start_bookings_thread()
    api_socketio_plannings.start_plannings_thread()
    api_socketio_media.start_media_thread()

    # Webapp admin websockets
    api_admin_socketio.start_domains_thread()
    api_admin_socketio.start_users_thread()
    api_admin_socketio.start_media_thread()
    api_admin_socketio.start_hypervisors_thread()
    api_admin_socketio.start_config_thread()
    api_admin_socketio.start_resources_thread()

    socketio.run(app, host="0.0.0.0", port=5000, debug=debug, log_output=debug)
