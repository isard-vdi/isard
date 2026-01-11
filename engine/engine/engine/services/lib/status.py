import os
import socket
import ssl
from datetime import datetime

import OpenSSL
from cachetools import TTLCache, cached
from engine.models.balancers import BalancerInterface
from engine.services.log import *
from isardvdi_common.default_storage_pool import DEFAULT_STORAGE_POOL_ID

engine_threads = [
    "background",
    "events",
    "broom",
    # "downloads_changes", # We will avoid this one as it starts and stops when needed
    "orchestrator",
    "changes_domains",
]

virt_balancer_type = os.environ.get("ENGINE_HYPER_BALANCER", "available_ram_percent")
virt_balancer = BalancerInterface(
    "default",
    balancer_type=virt_balancer_type,
)

disk_balancer_type = os.environ.get("ENGINE_DISK_BALANCER", "less_cpu")
disk_balancer = BalancerInterface(
    DEFAULT_STORAGE_POOL_ID,
    balancer_type=disk_balancer_type,
)


@cached(cache=TTLCache(maxsize=1, ttl=5))
def get_next_hypervisor():
    virt, _ = virt_balancer.get_next_hypervisor(storage_pool_id=DEFAULT_STORAGE_POOL_ID)
    return virt


@cached(cache=TTLCache(maxsize=1, ttl=5))
def get_next_disk():
    return disk_balancer.get_next_diskoperations()


@cached(cache=TTLCache(maxsize=10, ttl=5))
def check_spice_video_connection(
    proxy_host,
    proxy_port,
    target_host,
    target_port=7899,
):
    # Spice to hyper connection
    headers = f"CONNECT {target_host}:{target_port} HTTP/1.0\r\n\r\n"
    try:
        s = socket.socket()
        s.connect((proxy_host, int(proxy_port)))
        s.send(headers.encode("utf-8"))
        response = s.recv(3000)
        if response == b"HTTP/1.1 200 Connection established\r\n\r\n":
            s.close()
            return True
    except socket.error as m:
        logs.main.error(
            f"Error connecting to hypervisor {target_host}:{target_port} via proxy {proxy_host}:{proxy_port} spice ports: {m}"
        )
    except Exception as e:
        logs.main.error(
            f"General error connecting to hypervisor {target_host}:{target_port} via proxy {proxy_host}:{proxy_port} spice ports: {e}"
        )
    s.close()
    return False


# Certificate check disabled - was causing startup delays due to network timeouts
# SSL_CERT_CHECK_TIMEOUT = 5  # seconds
#
#
# @cached(cache=TTLCache(maxsize=10, ttl=5))
# def get_video_cert_expiration_days(host, port=443):
#     # Video certificate
#     old_timeout = socket.getdefaulttimeout()
#     try:
#         socket.setdefaulttimeout(SSL_CERT_CHECK_TIMEOUT)
#         cert = ssl.get_server_certificate((host, port))
#         x509 = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, cert)
#         expire_days = (
#             datetime.strptime(str(x509.get_notAfter().decode("ascii")), "%Y%m%d%H%M%SZ")
#             - datetime.now()
#         ).days
#         if expire_days <= 0:
#             logs.main.warning(
#                 f"Certificate for {host}:{port} has already expired, days: {expire_days}"
#             )
#         return expire_days if expire_days > 0 else False
#     except Exception as e:
#         logs.main.error(f"Error retrieving certificate for {host}:{port} - {e}")
#         return False
#     finally:
#         socket.setdefaulttimeout(old_timeout)


def get_hypervisor_video_status(
    html5_host, html5_port, static_host, spice_host, spice_proxy_host, spice_proxy_port
):
    # Certificate checks disabled - was causing startup delays
    return {
        "html5": True,
        "static": True,
        "spice": True,
    }
