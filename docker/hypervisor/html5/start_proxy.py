import multiprocessing
import websockify
import socket
servers={}
procs = {}

for i in range(30):
    servers[i]=websockify.WebSocketProxy(listen_host='0.0.0.0',
                             listen_port=55900+i,
                             target_host=socket.getfqdn(),
                             target_port=5900+i)
    procs[i] = multiprocessing.Process(target=servers[i].start_server)
    procs[i].start()
