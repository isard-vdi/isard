def mounts_usage():
    du = {"disk_usage": []}
    phydevs = []
    f = open("/proc/filesystems", "r")
    for line in f:
        if not line.startswith("nodev"):
            phydevs.append(line.strip())
    retlist = []
    f = open("/etc/mtab", "r")
    for line in f:
        if line.startswith("none"):
            continue
        fields = line.split()
        device = fields[0]
        mountpoint = fields[1]
        fstype = fields[2]
        if fstype not in phydevs:
            continue
        if device == "none":
            device = ""
        if (
            mountpoint == "/"
            or mountpoint == "/opt"
            or mountpoint.startswith("/opt/isard")
        ):
            st = os.statvfs(mountpoint)
            free = float("{:.2f}".format(st.f_bavail * st.f_frsize / 1073741824))
            total = float("{:.2f}".format(st.f_blocks * st.f_frsize / 1073741824))
            used = float(
                "{:.2f}".format((st.f_blocks - st.f_bfree) * st.f_frsize / 1073741824)
            )
            try:
                percent = ret = (float(used) / total) * 100
            except ZeroDivisionError:
                percent = 0
            du["disk_usage"].append(
                {
                    "device": device,
                    "free": free,
                    "fstype": fstype,
                    "mountpoint": mountpoint,
                    "percent": round(percent, 1),
                    "total": total,
                    "used": used,
                }
            )
    from pprint import pformat

    print(du)


mounts_usage()
