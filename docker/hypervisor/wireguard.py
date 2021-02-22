# Allows hyper to reach wireguard clients
import os,ipaddress

#hypervisor=int(])
#network=os.environ['WG_GUESTS_NETS']
hypervisor=int(os.environ['HYPERVISOR_NUMBER'])
network=os.environ['WG_GUESTS_NETS']
dhcp_mask=int(os.environ['WG_GUESTS_DHCP_MASK'])
reserved_hosts=int(os.environ['WG_GUESTS_RESERVED_HOSTS'])
users_net=os.environ['WG_USERS_NET']

nparent = ipaddress.ip_network(network, strict=False)
dhcpsubnets=list(nparent.subnets(new_prefix=dhcp_mask))

dhcp_subnet=dhcpsubnets[hypervisor]
dhcp_subnet_prefix=dhcp_subnet.prefixlen
dhcp_subnet_gw=list(dhcp_subnet.hosts())[0]
dhcp_subnet_range_start=list(dhcp_subnet.hosts())[reserved_hosts]
dhcp_subnet_range_end=list(dhcp_subnet.hosts())[-1]

int_net=list(dhcpsubnets[-1].subnets(new_prefix=29))[hypervisor]
wg_gw=list(int_net.hosts())[1]


wireguard_xml = """<network xmlns:dnsmasq='http://libvirt.org/schemas/network/dnsmasq/1.0'> \
  <name>wireguard</name> \
  <bridge name="virbr20"/> \
  <forward mode="route" dev="eth1"/> \
  <port isolated='yes'/> \
  <ip address="%s" prefix="%s"> \
    <dhcp> \
      <range start="%s" end="%s"/> \
    </dhcp>  \
  </ip>  \
       <dnsmasq:options> \
        <dnsmasq:option value="dhcp-option=121,%s,%s"/> \
        <dnsmasq:option value="dhcp-script=/update-client-ips.sh"/> \
      </dnsmasq:options> \
</network>""" % (dhcp_subnet_gw, dhcp_subnet_prefix, dhcp_subnet_range_start, dhcp_subnet_range_end, users_net, dhcp_subnet_gw)

with open('/etc/libvirt/qemu/networks/wireguard.xml', 'w') as fd:
    fd.write(wireguard_xml)

print('Setting wireguard-hypervisor internal net interface IP: ip a a '+str(list(int_net.hosts())[2])+'/'+str(int_net.prefixlen)+' dev '+os.environ['WG_INTERFACE'])
os.system('ip a a '+str(list(int_net.hosts())[2])+'/'+str(int_net.prefixlen)+' dev '+os.environ['WG_INTERFACE'])
print('Setting route to wireguard users network: ip r a '+users_net+' via '+str(list(int_net.hosts())[1]))
os.system('ip r a '+users_net+' via '+str(list(int_net.hosts())[1]))
#ip r a $WG_USERS_NET via ${WG_HYPER_NET_WG_PEER}