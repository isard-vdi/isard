import docker
import os
import re
from time import sleep
from lib.carbon import Carbon
c=Carbon()

from lib.helpers import cu, execute

class Containers():
    def __init__(self, interval=5):
        self.interval = interval

    def check(self):
        ## We should check if we can c
        try:
            client = docker.DockerClient(base_url='unix:///var/run/docker.sock')
            return True
        except:
            return False
        # ~ return True if os.path.isfile('/var/run/docker.sock') else False
        
    def stats(self):
        cmd=["docker","stats","--no-stream","--format","{{.Name}};{{.CPUPerc}};{{.MemUsage}};{{.MemPerc}};{{.NetIO}};{{.BlockIO}}"]
        while True:
            d={}
            for line in execute(cmd):
                values=re.split(';|/',line.strip().replace('%','').replace(' ',''))
                if values[0].startswith("isard-"):
                    d[values[0]+'.cpuperc']=values[1]
                    d[values[0]+'.memusage']=cu(values[2])
                    d[values[0]+'.memlimit']=cu(values[3])
                    d[values[0]+'.memperc']=values[4]
                    d[values[0]+'.netrx']=cu(values[5])
                    d[values[0]+'.nettx']=cu(values[6])
                    d[values[0]+'.diskrd']=cu(values[7])
                    d[values[0]+'.diskwr']=cu(values[8])
            c.send2carbon({"docker":d})
            sleep(self.interval)
                    
    # ~ def python_stats(self):
        # ~ try:
            # ~ # client = docker.from_env()
            # ~ client = docker.DockerClient(base_url='unix:///var/run/docker.sock')
            # ~ docks={}
            # ~ for i in client.containers.list():
                # ~ stats=i.stats(stream=False)
                # ~ name=i.name
                # ~ docks[name+'.cpu.total']=str(stats['precpu_stats']['cpu_usage']['total_usage'])
                # ~ docks[name+'.cpu.used']=str(stats['precpu_stats']['system_cpu_usage'])
                # ~ docks[name+'.mem.total']=str(stats['memory_stats']['limit'])
                # ~ docks[name+'.mem.used']=str(stats['memory_stats']['usage'])
                # ~ try:
                    # ~ for net in stats['networks'].keys():
                        # ~ docks[name+'.net.'+net+'.rx_bytes']=str(stats['networks'][net]['rx_bytes'])
                        # ~ docks[name+'.net.'+net+'.tx_bytes']=str(stats['networks'][net]['tx_bytes'])
                # ~ except:
                    # ~ None
            # ~ return docks
        # ~ except Exception as e:
            # ~ print(e)
            # ~ return False


                    

