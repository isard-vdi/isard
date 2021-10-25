import os

import psutil

psutil.PROCFS_PATH = "/proc"
import platform
from datetime import datetime
from time import sleep

from lib.carbon import Carbon

c = Carbon()

from lib.helpers import cu, execute


class OperatingSystem:
    def __init__(self, interval=10):
        self.interval = interval
        self.interval_paths = 6  # 60 seconds
        self.interval_current_paths = 6

    def check(self):
        try:
            self.one_shot()
        except Exception as e:
            print(e)
            return False
        return True

    def stats(self):
        while True:
            cpufreq = psutil.cpu_freq()
            cpu = {
                "cpu.freqcur": str(cpufreq.current),  # self.cpu['freqcur'],
                "cpu.loadperc": str(psutil.cpu_percent()),
            }
            c.send2carbon({"system": cpu})

            svmem = psutil.virtual_memory()
            mem = {
                "mem.total": str(svmem.total),
                "mem.avail": str(svmem.available),
                "mem.used": str(svmem.used),
                "mem.perc": str(svmem.percent),
            }
            c.send2carbon({"system": mem})

            # sw = psutil.swap_memory()
            # swap = {"swap.total":str(sw.total),
            #        "swap.free":str(sw.free),
            #        "swap.used":str(sw.used),
            #        "swap.perc":str(sw.percent)}
            ##c.send2carbon({"system":swap})

            if self.interval_current_paths == 0:
                partitions = psutil.disk_partitions()
                disk = {}
                for partition in partitions:
                    if partition.mountpoint.startswith("/mnt"):
                        try:
                            partition_usage = psutil.disk_usage(partition.mountpoint)
                        except PermissionError:
                            continue
                        mount = partition.mountpoint.split("/")[-1]
                        if mount == "efi":
                            continue
                        disk["disks." + mount + ".size"] = str(partition_usage.total)
                        disk["disks." + mount + ".used"] = str(partition_usage.used)
                        disk["disks." + mount + ".free"] = str(partition_usage.free)
                        disk["disks." + mount + ".perc"] = str(partition_usage.percent)
                c.send2carbon({"system": disk})

                paths = {}
                for path in ["templates", "groups", "media", "logs", "database"]:
                    size = 0
                    count = 0
                    for dirpath, dirnames, filenames in os.walk("/mnt/" + path):
                        for f in filenames:
                            fp = os.path.join(dirpath, f)
                            # skip if it is symbolic link
                            if not os.path.islink(fp):
                                size += os.path.getsize(fp)
                                count += 1
                    paths["paths." + path + ".size"] = str(size)
                    paths["paths." + path + ".count"] = str(count)
                c.send2carbon({"system": paths})
                self.interval_current_paths = self.interval_paths
            else:
                self.interval_current_paths -= 1

            sleep(self.interval)

    def one_shot(self):
        cpu = self.parse_cpu()
        cpufreq = psutil.cpu_freq()
        cpu = {
            "cpu.sockets": cpu["sockets"],
            "cpu.cores": cpu["cores"],  # str(psutil.cpu_count(logical=False)),
            "cpu.threads": cpu[
                "threads"
            ],  # str(psutil.cpu_count(logical=True)-psutil.cpu_count(logical=False)),
            "cpu.totalth": str(
                int(cpu["sockets"]) * int(cpu["cores"]) * int(cpu["threads"])
            ),
            "cpu.freqmax": cpu["freqmax"],  # str(cpufreq.max),
            "cpu.freqmin": cpu["freqmin"],
        }  # str(cpufreq.min),
        c.send2carbon({"system": cpu})

    def parse_cpu(self):
        cpu = {}
        for line in execute(["lscpu"]):
            if line.startswith("Thread"):
                cpu["threads"] = line.split(":")[1].strip()
            if line.startswith("Core"):
                cpu["cores"] = line.split(":")[1].strip()
            if line.startswith("Socket"):
                cpu["sockets"] = line.split(":")[1].strip()
            if line.startswith("CPU MHz"):
                cpu["freqcur"] = line.split(":")[1].strip()
            if line.startswith("CPU max"):
                cpu["freqmax"] = line.split(":")[1].strip()
            if line.startswith("CPU min"):
                cpu["freqmin"] = line.split(":")[1].strip()
        return cpu
