from gevent.wsgi import WSGIServer

from engine import app



def run():
    http_server = WSGIServer(('0.0.0.0', 5555), app)
    http_server.serve_forever()

# if app.debug:
#     from werkzeug.debug import DebuggedApplication
#     app.wsgi_app = DebuggedApplication( app.wsgi_app, True )

if __name__ == "__main__":
    run()