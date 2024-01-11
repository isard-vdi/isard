from engine.services.lib.debug import check_if_debugging
from engine.services.lib.status import disk_balancer_type, virt_balancer_type
from engine.services.lib.telegram import telegram_send_thread

telegram_send_thread(
    "STARTING",
    f"------------------------\nWARNING: Engine is starting now...\n - virt_balancer_type: {virt_balancer_type}\n - disk_balancer_type: {disk_balancer_type}",
)
check_if_debugging()

import logging
import traceback
from logging.handlers import RotatingFileHandler
from subprocess import check_output

from flask import Flask

## Moved populate & upgrade from webapp
from initdb.populate import Populate

check_output(("/isard/generate_certs.sh"), text=True).strip()

try:
    p = Populate()
except Exception as e:
    print(traceback.format_exc())
    print("Error populating...")
    exit(1)

from initdb.upgrade import Upgrade

try:
    u = Upgrade()
except Exception as e:
    print(traceback.format_exc())
    print("Error Upgrading...")
    exit(1)
## End

from engine.services.lib.functions import check_tables_populated

check_tables_populated()

from engine.models.engine import Engine
from engine.services import db

if __name__ == "__main__":
    app = Flask(__name__)

    app.m = Engine(with_status_threads=False)
    app.db = db

    # remove default logging for get/post messages
    werk = logging.getLogger("werkzeug")
    werk.setLevel(logging.ERROR)

    # add log handler
    handler = RotatingFileHandler("/tmp/api.log", maxBytes=10000, backupCount=1)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)

    # register blueprints
    from engine.api import api as api_blueprint

    app.register_blueprint(api_blueprint, url_prefix="")  # url_prefix /api?

    ## DEBUG mode hungs flask endpoint
    # if os.environ.get("LOG_LEVEL") == "DEBUG":
    #     app.run(debug=True, host="0.0.0.0")
    # else:
    app.run(host="0.0.0.0", port=5000)
