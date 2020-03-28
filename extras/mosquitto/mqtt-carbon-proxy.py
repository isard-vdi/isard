import paho.mqtt.client as mqtt
import time
import socket
import pickle
import struct

# mqtt data
broker="localhost"
port=1883
timelive=60

plugs_online = {}

class grafana():
    def __init__(self):
        self.host='isard-grafana'
        self.port=2004

    def send_kv(self,k,v):
        tuples = ([])
        now = int(time.time())
        if type(v) is bool:
            v = 1 if v is True else 0
        if type(v) in (int,float):
            tuples.append((k, (now, v)))
        if type(v) is str:
            tuples.append((k, (now, v)))
        print(tuples)
        self.send(tuples)

    def send(self,tuples):
        sender = self.conn()
        if sender is not False:
            package = pickle.dumps(tuples, 1)
            size = struct.pack('!L', len(package))
            sender.sendall(size)
            sender.sendall(package)
            return True
        else:
            print("Could not connect to carbon host")
            return False


    def conn(self):
        s = socket.socket()
        s.settimeout(5)

        try:
            s.connect((self.host, self.port))
            return s
        except socket.error as e:
            print("Can not connect to grafana host")
            return False

class mosquitto():
    def __init__(self,g):
        self.grafana=g
        global plugs_online
        self.plugs_online = plugs_online

        self.client = mqtt.Client()
        self.client.connect(broker,port,timelive)

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.loop_forever()

    def list2dict(self,items,value):
        new_dict = current = {}
        last_item=items[-1]
        for k in items[:-1]:
            current[k] = {}
            current = current[k]
        current[last_item] = value
        return new_dict

    def on_connect(self,client, userdata, flags, rc):
      print("Connected to mqtt broker with result code "+str(rc))
      client.subscribe("/isard/hypers/#")

    def on_message(self,client, userdata, msg):
        # Carbon
        t=time.time()
        tsplit=msg.topic[1:].rsplit("/",1)
        key=str(tsplit[0]+'/pwr/'+tsplit[1]).replace("/",".")
        #print(key)
        self.grafana.send_kv(key,msg.payload.decode())
        topic=msg.topic.split("/")
        if not topic[3] in self.plugs_online.keys():
            self.plugs_online[topic[3]]={}
        self.plugs_online[topic[3]]['last_seen']=t
        self.plugs_online[topic[3]][topic[4]]=msg.payload.decode()
        for k,v in self.plugs_online.items():
            if int(t-v['last_seen']) > 25:
                # ~ del self.plugs_online[k]
                print(k+' offline')
        pprint.pprint(self.plugs_online)

#database = db()
database = {}
g = grafana()
# ~ g.send_kv('isard.hypers.isard-hypervisor.plug.power',34)
# ~ if database.conn() and g.conn():
m = mosquitto(g)

