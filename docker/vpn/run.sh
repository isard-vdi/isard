# NOTRACK for tunnel traffic (reduces conntrack overhead)
# On-the-wire ports:
#   WG_USERS_PORT:  always WireGuard (user VPN)
#   WG_HYPERS_PORT: WireGuard (wg+geneve mode) or plain Geneve (geneve-only mode)
echo "$(date): INFO: Applying NOTRACK rules for tunnel traffic"
_wg_users_port=${WG_USERS_PORT:-443}
_wg_hypers_port=${WG_HYPERS_PORT:-4443}
for _port in $_wg_users_port $_wg_hypers_port; do
    iptables -t raw -C PREROUTING -p udp --dport "$_port" -j NOTRACK 2>/dev/null || \
        iptables -t raw -I PREROUTING 1 -p udp --dport "$_port" -j NOTRACK
    iptables -t raw -C OUTPUT -p udp --sport "$_port" -j NOTRACK 2>/dev/null || \
        iptables -t raw -I OUTPUT 1 -p udp --sport "$_port" -j NOTRACK
done
echo "$(date): INFO: Tunnel traffic (UDP $_wg_users_port, $_wg_hypers_port): NOTRACK applied"

# Start conntrackd
echo "1" > /host-proc/sys/net/netfilter/nf_conntrack_acct
conntrackd &

function extract_conntrack () {
    while : ; do
        conntrack -L -p udp --dport 3389 -p tcp --dport 3389 -o xml 1> /conntrack/rdp.xml 2> /dev/null
        ip -j neigh show 1> /conntrack/arp.json
        sleep 10
    done
}
extract_conntrack &

# OVS Security Stats loop (JSON format)
function ovs_stats_loop () {
    while : ; do
        python3 /ovs/security-stats.py 2>/dev/null
        sleep 60
    done
}
ovs_stats_loop &

# Start guacd
echo "$(date): INFO: Starting guacd server"
guacd -b 0.0.0.0 -L info -f >> /var/log/guacd 2>&1 &

# Start RDPGW
echo "$(date): INFO: Starting RDPGW server"
/rdpgw &

# Start wireguard
cd /certs
if [ ! -f /certs/server_private.key ]
then
    ## Alert! All client public keys should be updated in database
    ## It is done afterwards in wgadmin
    echo "$(date): WARNING: Not found wireguard keys. Regenerating new one's..."
    wg genkey | tee server_private.key | wg pubkey > server_public.key
fi
cd /

# Allows wireguard to reach guests in hypervisors
#ip r a $WG_HYPER_GUESTNET via $WG_HYPER_NET_HYPER_PEER
# python3 networking.py

/ovs/ovs_setup.sh
cd /src

echo "$(date): INFO: Starting vpn server"
python3 wgadmin.py
