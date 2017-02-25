#!flask/bin/python
# coding=utf-8

from webapp import app
from webapp.lib import api
app.isardapi = api.isard()

from gevent.wsgi import WSGIServer
from gevent import monkey; monkey.patch_all(thread=False)

if __name__ == "__main__":
	http_server = WSGIServer(('0.0.0.0', 5000), app)
	http_server.serve_forever()
