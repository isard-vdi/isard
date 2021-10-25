from pprint import pprint
from time import sleep

import requests
from lib.carbon import Carbon

c = Carbon()


class Engine:
    def __init__(self, interval=5, host="isard-engine"):
        self.url = "http://" + host + ":5555/engine_info"
        self.interval = interval

    def stats(self):
        try:
            while True:
                resp = requests.get(url=self.url, timeout=2).json()
                # ~ pprint(resp)
                dict = {
                    "mainth.background": resp["background_is_alive"],
                    "mainth.broom": resp["broom_thread_is_alive"],
                    "mainth.changes_domains": resp["changes_domains_thread_is_alive"],
                    "mainth.changes_hyps": resp["changes_hyps_thread_is_alive"],
                    "mainth.changes_downloads": resp[
                        "download_changes_thread_is_alive"
                    ],
                    "mainth.event": resp["event_thread_is_alive"],
                }
                dict["status"] = self.engine_is_alive(dict)
                for k, v in resp["queue_disk_operations_threads"].items():
                    dict["queues." + k + ".disk_operations"] = v
                for k, v in resp["queue_size_working_threads"].items():
                    dict["queues." + k + ".size_working"] = v
                c.send2carbon({"engine": dict})
                sleep(self.interval)
        except Exception as e:
            print(e)
            c.send2carbon({"engine": {"status": False}})
            sleep(self.interval)

    def check(self):
        try:
            resp = requests.get(url=self.url, timeout=2).json()
            return True
        except Exception as e:
            return False

    def engine_is_alive(self, dict):
        for k, v in dict.items():
            if v is False:
                return False
        return True

    # ~ def _iterdict(self,d):
    # ~ alert=[]
    # ~ for k,v in d.items():
    # ~ if isinstance(v, dict):
    # ~ self._iterdict(v)
    # ~ else:
    # ~ if type(v) is bool and v is False:
    # ~ alert.append(k)
    # ~ return alert
