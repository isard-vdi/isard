import socket
import pickle
import struct
import time

from engine.services.log import *
from engine.services.lib.functions import flatten_dict

TIMEOUT_SOCKET_CONNECTION = 30


def send_dict_to_grafana(d,host,port=2004,prefix='isard'):
    sender = create_socket_grafana(host=host,port=port)
    if sender is not False:
        flatten_and_send_dict(d, sender, prefix=prefix)
        sender.close()
        return True
    else:
        return False


def create_socket_grafana(host,port=2004):
    s = socket.socket()
    s.settimeout(TIMEOUT_SOCKET_CONNECTION)

    try:
        s.connect((host, port))
        return s

    except socket.error as e:
        log.error(e)
        log.error(f'Failed connection to grafana server: {host} in port {port}')
        try:
            ip = socket.gethostbyname(host)
        except socket.error as e:
            log.error(e)
            log.error('not resolves ip from hostname of grafana server: {}'.format(host))
            return False
        return False


def flatten_and_send_dict(d,sender,prefix='isard'):
    type_ok = (int,float)
    try:
        now = int(time.time())
        tuples = ([])
        lines = []
        # We're gonna report all three loadavg values
        d_flat = flatten_dict(d)
        for k,v in d_flat.items():
            k = prefix + '.' + k

            #check if type is ok
            if type(v) is bool:
                v = 1 if v is True else 0

            if type(v) in type_ok:
                tuples.append((k, (now, v)))
                lines.append(f'({now}) {k}: {v}')

            if type(v) is str:
                tuples.append((k + '.' + v, (now, 1)))
                lines.append(f'({now}) {k}.{v}: 0')

        message = '\n'.join(lines) + '\n'  # all lines must end in a newline
        logs.main.debug('sending to grafana:')
        logs.main.debug(message)
        package = pickle.dumps(tuples, 1)
        size = struct.pack('!L', len(package))
        sender.sendall(size)
        sender.sendall(package)
    except Exception as e:
        log.error(f'Exception when send dictionary of values to grafana: {e}')