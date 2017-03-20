
import os
from flask import Flask

if os.path.isfile('config.py'):
    path_config = 'config.py'
elif os.path.isfile('default_config.py'):
    path_config = 'default_config.py'


try:
    from app.config import configure_app
except:
    from app.default_config import configure_app

wtforms_json.init()

app = Flask(__name__)
configure_app(app)
db = SQLAlchemy(app)

# Aquest import s'ha de fer despres de app = Flask(__name__)
from app.presentation.views import *
from app.presentation.views.query import *

# register blueprints
from app.presentation.api import api as api_blueprint
app.register_blueprint(api_blueprint, url_prefix='/api')

from app.presentation.views.test.login import auth
app.register_blueprint(auth)
