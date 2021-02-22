# Allows hyper to reach wireguard clients
GW=$(echo $WG_HYPER_GUESTNET | awk -F'.' -v OFS="." '$4=1')
PREFIX=${WG_HYPER_GUESTNET##*/}
cat > /etc/libvirt/qemu/networks/wireguard.xml << EOF
<network xmlns:dnsmasq='http://libvirt.org/schemas/network/dnsmasq/1.0'>
  <name>wireguard</name>
  <uuid>98552eb2-3e01-4f4d-9d50-4b824f31caff</uuid>
  <bridge name="virbr20"/>
  <forward mode="route" dev="eth1"/>
  <port isolated='yes'/>
  <ip address="$GW" prefix="$PREFIX">
    <dhcp>
      <range start="$WG_HYPER_GUESTNET_DHCP_START" end="$WG_HYPER_GUESTNET_DHCP_END"/>
    </dhcp>
  </ip>
       <dnsmasq:options>
        <dnsmasq:option value="dhcp-option=121,$WG_USERS_NET,$GW"/>
        <dnsmasq:option value="dhcp-script=/update-client-ips.sh"/>
      </dnsmasq:options>
</network>
EOF