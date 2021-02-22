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

print('Setting wireguard interface IP: ip a a '+str(list(int_net.hosts())[1])+'/'+str(int_net.prefixlen)+' dev '+os.environ['WG_INTERFACE'])
os.system('ip a a '+str(list(int_net.hosts())[1])+'/'+str(int_net.prefixlen)+' dev '+os.environ['WG_INTERFACE'])

#print('Setting route to wireguard users network: ip r a '+str(dhcp_subnet)+' via '+str(list(int_net.hosts())[1]))

print('Setting route to hypervisor guests: ip r a '+str(dhcp_subnet)+' via '+str(list(int_net.hosts())[2]))
os.system('ip r a '+str(dhcp_subnet)+' via '+str(list(int_net.hosts())[2]))
