# IsardVDI System administration

By default IsardVDI will open some container ports to the public world:

*   80 TCP: Redirect to 443 https and used by spice video protocol TLS tunnel
*  443 TCP: Web and HTML5 video protocols
*  443 UDP: Wireguard users vpn
* 4443 UDP: Wireguard hypervisors vpn

Now there is no need to use firewalld to open/close ports as docker is set
to handle iptables rules (the default docker behaviour). But a firewall
correctly set up is always a must with all your services!

## One public isard and multiple internal hypervisors

When using isard with one node visible to outside world and having other 
hypervisors internally in your infrastructure you will be using:

* main isard: docker-compose.yml
* hypervisors: docker-compose.hypervisor-standalone.yml

And then you will need to use iptables/firewalld to forward some ports inside
the isard-hypervisor docker container as to be reacheable from main isard:

Add **zone infrastructure** with unrestricted access from the networks that you
use internally to connect your cluster/storage. For example:

* cluster/ipmi network: 172.31.4.0/24
* drbd: 172.31.1.0/24
* nfs: 172.31.2.0/24
* infrastructure: 172.31.3.0/24

```bash
firewall-cmd --permanent --new-zone=infrastructure
# Source allowed (all internal networks)
firewall-cmd --permanent --zone=infrastructure --add-source=172.31.0.0/21
firewall-cmd --permanent --zone=infrastructure --add-rich-rule='rule family="ipv4" source address="172.31.0.0/21" accept'
```

Add **zone hyper** with access to 2022 and video ports 5900-6899. This interface
will be used to redirect videos from isard-portal haproxy to other hypervisors:

```bash
firewall-cmd --permanent --new-zone=hyper

# Sources allowed
firewall-cmd --permanent --zone=hyper --add-source=172.16.254.200/32
firewall-cmd --permanent --zone=hyper --add-source=172.16.254.201/32

# Hypervisor ssh port from isard-engine
firewall-cmd --permanent --zone=hyper --add-rich-rule='rule family="ipv4" source address="172.16.254.200/32" port port="2022" protocol="tcp" accept' --permanent
firewall-cmd --permanent --zone=hyper --add-rich-rule='rule family="ipv4" source address="172.16.254.201/32" port port="2022" protocol="tcp" accept' --permanent
# Forward this port to isard-hypervisor internal IP
firewall-cmd --permanent --zone=hyper --add-forward-port=port=2022:proto=tcp:toport=2022:toaddr=172.31.255.17 --permanent

# Video ports without proxy
firewall-cmd --permanent --zone=hyper --add-rich-rule='rule family="ipv4" source address="172.16.254.200/32" port port="5900-6899" protocol="tcp" accept' --permanent
firewall-cmd --permanent --zone=hyper --add-rich-rule='rule family="ipv4" source address="172.16.254.201/32" port port="5900-6899" protocol="tcp" accept' --permanent
# Forward those ports to isard-hypervisor internal IP
firewall-cmd --permanent --zone=hyper --add-forward-port=port=5900-6899:proto=tcp:toport=5900-6899:toaddr=172.31.255.17 --permanent
```

## Publicy visible hypervisors

In this configuration you will need multiple public ip's (one for main isard and one for each 
hypervisor) or use only one public IP and open multiple ports to each hypervisor video proxy.

You will be using:

* main isard without hypervisor: docker-compose.web.yml
* hypervisors: docker-compose.hypervisor.yml

Then main isard will open:

*   80 TCP: Redirect to 443
*  443 TCP: Web
*  443 UDP: Wireguard users vpn
* 4443 UDP: Wireguard hypervisors vpn

And each hypervisor will need:

* Access from main isard to get monitored (port 2022 by default). This needs to be forwarded at iptables/firewalld level as shown in the previous example
```
firewall-cmd --permanent --new-zone=hyper

# Sources allowed
firewall-cmd --permanent --zone=hyper --add-source=83.53.72.181/32

# Hypervisor ssh port from isard-engine
firewall-cmd --permanent --zone=hyper --add-rich-rule='rule family="ipv4" source address="83.53.72.181/32" port port="2022" protocol="tcp" accept' --permanent
firewall-cmd --permanent --zone=hyper --add-forward-port=port=2022:proto=tcp:toport=2022:toaddr=172.31.255.17 --permanent

```
* Access from outside world to proxy videos, by default ports 80 and 443

So, if using only one public IP you'll need to map on your border router 80/443 to main isard and then map other ports to each hypervisor for ports 80 and 443. For example:

* hyper1: 801/4431
* hyper2: 802/4432

And set it correctly at the isard main web interface for each hypervisor.
