## sudo pip3 install paho-mqtt
import paho.mqtt.client as paho
broker="localhost"
port=1883
def on_publish(client,userdata,result):             #create function for callback
    print("data published \n")
    print(client)
    print(userdata)
    print(result)
    pass
client1= paho.Client("isard")                           #create client object
client1.connect(broker,port,60)                                 #establish connection
client1.on_publish = on_publish                          #assign function to callback
ret=client1.publish("isard/hypers/isard-hypervisor/power/",payload="55")                   #publish
print(ret)
