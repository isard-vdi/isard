import json

from engine.services.db import delete_table_item, insert_table_dict, update_table_field

json_new_hyper = """

    "capabilities": {
        "disk_operations": true ,
        "hypervisor": true
    } ,
    "description": "Added via api" ,
    "detail": "" ,
    "enabled": false ,
    "hostname": "isard-hypervisor" ,
    "hypervisors_pools": [
        "default"
    ] ,
    "id": "isard-hypervisor" ,
    "port": "2022" ,
    "status": "Offline" ,
    "status_time": false ,
    "uri": "" ,
    "user": "root" ,
    "viewer": {
        "html5_ext_port": "443" ,
        "proxy_hyper_host": "isard-hypervisor" ,
        "proxy_video": "localhost" ,
        "spice_ext_port": "80" ,
        "static": "localhost"
    }
"""
new_media = """
[{"accessed":1630392808.6059213,"allowed":{"categories":false,"groups":false,"roles":[],"users":false},"category":"default","description":"","detail":"Downloaded from website","group":"default-default","hypervi
sors_pools":["default"],"icon":"fa-circle-o","id":"_local-default-admin-admin-systemrescue-8.04-amd64.iso","kind":"iso","name":"systemrescue-8.04-amd64.iso","path":"default/default/local/admin-admin/systemrescue
-8.04-amd64.iso","progress":{"received":"0","received_percent":0,"speed_current":"","speed_download_average":"","speed_upload_average":"","time_left":"","time_spent":"","time_total":"","total":"","total_percent"
:0,"xferd":"0","xferd_percent":"0"},"status":"DownloadStarting","url-isard":false,"url-web":"https://deac-fra.dl.sourceforge.net/project/systemrescuecd/sysresccd-x86/8.04/systemrescue-8.04-amd64.iso","user":"loc
al-default-admin-admin","username":"admin"}]
"""

new_media_dict = new_media = {
    "accessed": 1630392808.6059213,
    "allowed": {"categories": False, "groups": False, "roles": [], "users": False},
    "category": "default",
    "description": "",
    "detail": "Downloaded from website",
    "group": "default-default",
    "hypervisors_pools": ["default"],
    "icon": "fa-circle-o",
    "id": "_local-default-admin-admin-{name_media}",
    "kind": "iso",
    "name": "{name_media}",
    "path": "default/default/local/admin-admin/{name_media}",
    "progress": {
        "received": "0",
        "received_percent": 0,
        "speed_current": "",
        "speed_download_average": "",
        "speed_upload_average": "",
        "time_left": "",
        "time_spent": "",
        "time_total": "",
        "total": "",
        "total_percent": 0,
        "xferd": "0",
        "xferd_percent": "0",
    },
    "status": "DownloadStarting",
    "url-isard": False,
    "url-web": "https://deac-fra.dl.sourceforge.net/project/systemrescuecd/sysresccd-x86/8.04/systemrescue-8.04-amd64.iso",
    "user": "local-default-admin-admin",
    "username": "admin",
}

new_domain_from_iso = {
    "allowed": {"categories": False, "groups": False, "roles": False, "users": False},
    "category": "default",
    "create_dict": {
        "create_from_virt_install_xml": "win10Virtio",
        "forced_hyp": False,
        "favourite_hyp": False,
        "hardware": {
            "boot_order": ["iso"],
            "disk_bus": "virtio",
            "disks": [
                {"file": "default/default/local/admin-admin/srcd01.qcow2", "size": "1G"}
            ],
            "floppies": [],
            "graphics": ["default"],
            "interfaces": ["default"],
            "isos": [{"id": "_local-default-admin-admin-systemrescue-8.04-amd64.iso"}],
            "memory": 1572864,
            "vcpus": 1,
            "videos": ["default"],
        },
        "media": "_local-default-admin-admin-systemrescue-8.04-amd64.iso",
    },
    "description": "",
    "detail": None,
    "group": "default-default",
    "hypervisors_pools": ["default"],
    "icon": "circle-o",
    "id": "_local-default-admin-admin-srcd01",
    "kind": "desktop",
    "name": "srcd01",
    "options": {"viewers": {"spice": {"fullscreen": False}}},
    "os": "win10Virtio",
    "server": False,
    "status": "CreatingDiskFromScratch",
    "user": "local-default-admin-admin",
    "username": "admin",
    "xml": None,
}


def add_test_media(d_media, name="systemrescue-8.04-amd64.iso"):
    d = d_media
    for k in ["id", "name", "path"]:
        d[k] = d_media[k].format(name_media=name)
    insert_table_dict("media", d)


def add_hyper_localhost():
    pass


import os
import subprocess


def create_rsync_cmd(
    src_path, dst_path, verbose=True, show_progress=True, bwlimit=False
):
    cmd = "rsync -a"
    if verbose:
        cmd += "v"
    if len(bwlimit) > 0:
        cmd += " --bwlimit={}".format(bwlimit)
    if show_progress:
        cmd += " --progress"
    cmd += " " + src_path + " "
    cmd += "" + dst_path + ""
    return cmd


def mv_rsync_with_ssh(
    src_path, dst_path, hostname="isard-hypervisor", user="root", port=22, bwlimit=""
):
    cmd = create_rsync_cmd(src_path, dst_path, bwlimit=bwlimit)
    ssh_template = (
        """ssh -oBatchMode=yes -p {port} {user}@{hostname} """
        f""" "ls -lh {src_path}; rm -f /isard/random_10MB_copy; """ + cmd + '"'
    )

    ssh_command = ssh_template.format(
        port=port, user=user, hostname=hostname, src_path=src_path, dst_path=dst_path
    )
    print(ssh_command)

    p = subprocess.Popen(
        ssh_command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        preexec_fn=os.setsid,
    )
    line = ""
    rc = p.poll()
    if rc is None:
        # header = p.stderr.readline().decode('utf8')
        df = p.stdout.readline().decode("utf8")
        try:
            size = [a for a in df.split(" ") if len(a) > 0][4]
        except:
            size = "0M"
        # print(header)
        # print(header2)
        while rc is None:
            # c = p.stderr.read(1).decode('utf8')
            b = p.stdout.read(1).decode("utf8")
            # if not c:
            #    rc = p.poll()
            #    break
            if b == "\r":
                if len(line) > 60:
                    print("asdf" + line)
                    line_split = [a for a in line.split(" ") if len(a) > 0]
                    tmp = line[: line.find("%")]
                    percent = tmp[tmp.rfind(" ") + 1 :]
                    print(f"percent: {percent}")
                    received_percent = line_split[-3]
                    speed_download_average = line_split[-2]
                    total = size
                    time_left = line_split[-1]
                    progress = {
                        "received_percent": received_percent,
                        # "speed_current":  "" ,
                        "speed_download_average": speed_download_average,
                        # "speed_upload_average":  "" ,
                        "time_left": time_left,
                        # "time_spent":  "" ,
                        # "time_total":  "" ,
                        "total": total,
                        "total_percent": 0,
                        # "xferd":  "0" ,
                        # "xferd_percent":  "0"
                    }
                    line = ""
                    # values = line.split()
                    # update_download_percent(d_progres  s)
            else:
                line = line + b
            rc = p.poll()
            if rc is None:
                continue
            elif rc != 0:
                error_msg = f"Rsync failed with status code {rc}"
                print(error_msg)
            else:
                print("rsync finalished ok")
    elif rc == 0:
        print("finalished ok")


if __name__ == "__main__":
    pass
