import logging as log
import threading
import time
from subprocess import check_call, check_output


def monitor_vpn_status():
    while True:
        hypers = check_output(("wg", "show", "hypers", "dump"), text=True).strip()
        hyper_status = [line.split("\t") for line in hypers.split("\n")][1:]
        users = check_output(("wg", "show", "users", "dump"), text=True).strip()
        users_status = [line.split("\t") for line in hypers.split("\n")][1:]
        # log.error(hyper_status)
        # log.error(users_status)

        # ERROR:root:[['Gsi6zQMAGZHoKE7DgiwvjgllOOaPtlFf/Vq450PIWkk=', '(none)', '192.168.0.53:47291', '10.1.0.3/32', '1632681470', '5160', '1528', '25'], ['w2zNOepGC2l1ORTT1KdH+IK6/He9HxnDqvE1mMl4Byw=', '(none)', '172.18.255.17:37781', '10.1.0.2/32', '1632681538', '552', '216', '25']]
        time.sleep(25)


def start_monitoring_vpn_status():
    thread_monitor_vpn = threading.Thread(target=monitor_vpn_status, args=())
    thread_monitor_vpn.start()
