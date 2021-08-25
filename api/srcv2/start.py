from gevent import monkey
monkey.patch_all()

from api import app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7039, debug=False) #, logger=logger, engineio_logger=engineio_logger)
