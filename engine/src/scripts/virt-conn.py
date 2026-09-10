from pprint import pprint

import libvirt

uri = "qemu+ssh://isard-hypervisor:2022/system"
conn = libvirt.open(uri)

hyper_info = conn.getInfo()
hyper_cpu_model_names = conn.getCPUModelNames("x86_64")
hyper_cpu_map = conn.getCPUMap()

pprint(hyper_cpu_map)
