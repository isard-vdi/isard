import docker
import pprint

import multiprocessing as mp

class Containers():
    def __init__(self):
        self.output = mp.Queue()
        self.client = docker.DockerClient(base_url='unix:///var/run/docker.sock')
        
        self.containers=self.client.containers.list()

    def stats(self):
        # ~ client = docker.DockerClient(base_url='unix:///var/run/docker.sock')
        processes=[mp.Process(target=self.process_stats, args=(i.name,i.stats(stream=False))) for i in self.containers]
        
        for p in processes:
            p.start()
            
        for p in processes:
            p.join()
            
            
    def process_stats(name,stats):
        # ~ client = docker.DockerClient(base_url='unix:///var/run/docker.sock')
        docks={}
        # ~ stats=i.stats(stream=False)
        # ~ name=i.name
        docks[name+'.cpu.total']=str(stats['precpu_stats']['cpu_usage']['total_usage'])
        docks[name+'.cpu.used']=str(stats['precpu_stats']['system_cpu_usage'])
        docks[name+'.mem.total']=str(stats['memory_stats']['limit'])
        docks[name+'.mem.used']=str(stats['memory_stats']['usage'])
        try:
            for net in stats['networks'].keys():
                docks[name+'.net.'+net+'.rx_bytes']=str(stats['networks'][net]['rx_bytes'])
                docks[name+'.net.'+net+'.tx_bytes']=str(stats['networks'][net]['tx_bytes'])
        except:
            None
        self.output.put(docks)
                    
    # ~ def (self):
        # ~ try:
            #####client = docker.from_env()
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
