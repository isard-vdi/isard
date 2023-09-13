import json
import os
import sys
import traceback
from distutils.util import strtobool
from importlib.machinery import SourceFileLoader
from pprint import pprint
from time import sleep

from api_client import ApiClient

DEFAULT_STORAGE_POOL_ID = (
    SourceFileLoader("storage_pool", "/src/_common/default_storage_pool.py")
    .load_module()
    .DEFAULT_STORAGE_POOL_ID
)

# Instantiate connection
try:
    apic = ApiClient()
except:
    raise

flavour = os.environ.get("FLAVOUR", False)
## We only check the flavours that have hypervisor:
## all-in-one, hypervisor, hypervisor-standalone
if str(flavour) == "all-in-one" or not flavour:
    hostname = "isard-hypervisor"
    static_url = os.environ.get("DOMAIN")
    video_domain = os.environ.get("DOMAIN")
    proxy_hyper_url = "isard-hypervisor"
if str(flavour) == "hypervisor":
    hostname = os.environ.get("DOMAIN")
    static_url = os.environ.get("STATIC_DOMAIN")
    video_domain = os.environ.get("VIDEO_DOMAIN")
    proxy_hyper_url = "isard-hypervisor"
if str(flavour) == "hypervisor-standalone":
    hostname = os.environ.get("DOMAIN")
    static_url = os.environ.get("STATIC_DOMAIN")
    video_domain = os.environ.get("VIDEO_DOMAIN")
    proxy_hyper_url = os.environ.get("DOMAIN")

isard_hyper_vpn_host = os.environ.get("VPN_DOMAIN", "isard-vpn")


def SetupHypervisor():
    HYPERVISOR = {
        "hyper_id": os.environ.get("HYPER_ID", "isard-hypervisor"),
        "hostname": hostname,
        "port": "2022",
        "cap_disk": bool(strtobool(os.environ.get("CAPABILITIES_DISK", "true"))),
        "cap_hyper": bool(strtobool(os.environ.get("CAPABILITIES_HYPER", "true"))),
        "enabled": False,
        "description": "Added through api",
        "browser_port": os.environ["VIEWER_BROWSER"]
        if os.environ.get("VIEWER_BROWSER", False)
        else "443",
        "spice_port": os.environ["VIEWER_SPICE"]
        if os.environ.get("VIEWER_SPICE", False)
        else "80",
        "isard_static_url": static_url,
        "isard_video_url": video_domain,
        "isard_proxy_hyper_url": proxy_hyper_url,
        "isard_hyper_vpn_host": isard_hyper_vpn_host,
        "only_forced": json.loads(os.environ.get("ONLY_FORCED_HYP", "false").lower()),
        "nvidia_enabled": True
        if os.environ.get("GPU_NVIDIA_SCAN") == "true"
        else False,
        "force_get_hyp_info": True
        if os.environ.get("GPU_NVIDIA_RESCAN") == "true"
        else False,
        "min_free_mem_gb": os.environ.get("HYPER_FREEMEM", "0"),
        "storage_pools": os.environ.get(
            "CAPABILITIES_STORAGE_POOLS", DEFAULT_STORAGE_POOL_ID
        ),
        "buffering_hyper": json.loads(
            os.environ.get("BUFFERING_HYPER", "false").lower()
        ),
        "gpu_only": True if os.environ.get("GPU_ONLY") == "true" else False,
    }

    ## Adding hyper. Received dict with certs and number
    ok = False
    while not ok:
        try:
            data = apic.post("hypervisor", data=HYPERVISOR)
            if not data:
                print("Api does not answer OK... retrying...")
                sleep(2)
                continue
        except:
            print("Could not contact api to register me... retrying...")
            sleep(2)
            continue
        if not data["certs"]["ca-cert.pem"]:
            print("Certificate not found in main isard host.")
            sleep(2)
        else:
            ok = True

    ## Check if certificates have changed and needs updating
    try:
        update = False
        with open("/etc/pki/libvirt-spice/ca-cert.pem", "r") as clientcert:
            if clientcert.read() not in data["certs"]["ca-cert.pem"]:
                print("ca-cert differs from existing one, needs updating.")
                update = True
            else:
                print("Viewers certificates seem to be ok.")
        with open("/root/.ssh/authorized_keys", "r") as hostkey:
            if hostkey.read() not in data["certs"]["id_rsa.pub"]:
                print("id_rsa key differs from existing one, needs updating")
                update = True
            else:
                print("Authorized key from engine seem to be ok.")
    except:
        print("New certificates found so updating it from main isard...")
        update = True

    ## Updating certificates if needed
    try:
        if update:
            print("Updating viewer certificates from main isard host...")
            for k, v in data["certs"].items():
                if k == "id_rsa.pub":
                    with open("/root/.ssh/authorized_keys", "w") as f:
                        f.write(v)
                else:
                    with open("/etc/pki/libvirt-spice/" + k, "w") as f:
                        f.write(v)
    except:
        raise


def DeleteHypervisor():
    ok = False
    while not ok:
        try:
            deleted = apic.delete(
                "hypervisor/" + os.environ.get("HYPER_ID", "isard-hypervisor")
            )
            ok = True
        except:
            print("Could not contact api to delete me... retrying...")
            sleep(1)
    return deleted


def EnableHypervisor():
    data = {"enabled": True}
    ok = False
    while not ok:
        try:
            enabled = apic.update(
                "hypervisor/" + os.environ.get("HYPER_ID", "isard-hypervisor"),
                data=data,
            )
            ok = True
        except:
            print("Could not contact api to enable me... retrying...")
            sleep(1)
    return enabled


def DisableHypervisor():
    data = {"enabled": False}
    ok = False
    while not ok:
        try:
            enabled = apic.update(
                "hypervisor/" + os.environ.get("HYPER_ID", "isard-hypervisor"),
                data=data,
            )
            ok = True
        except:
            print("Could not contact api to disable me... retrying...")
            sleep(1)
    return enabled
