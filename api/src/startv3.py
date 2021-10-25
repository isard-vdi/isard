from gevent import monkey

monkey.patch_all()

import os

from api.libv2 import (
    api_socketio_deployments,
    api_socketio_domains,
    api_socketio_secrets,
)

from api import app, socketio

debug = True if os.environ["LOG_LEVEL"] == "DEBUG" else False

if __name__ == "__main__":
    api_socketio_domains.start_domains_thread()
    api_socketio_secrets.start_secrets_thread()
    api_socketio_deployments.start_deployments_thread()
    socketio.run(app, host="0.0.0.0", port=5000, debug=debug, log_output=debug)
