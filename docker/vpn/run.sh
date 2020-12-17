cd /certs
if [ ! -f /certs/server_private.key ]
then
    ## Alert! All client public keys should be updated in database
    wg genkey | tee server_private.key | wg pubkey > server_public.key
fi
echo "[Interface]
Address = $WIREGUARD_SERVER_IP
SaveConfig = false
PrivateKey = $(cat /certs/server_private.key)
ListenPort = 443
PostUp = iptables -I FORWARD -i wg0 -o wg0 -j REJECT --reject-with icmp-host-prohibited" > /etc/wireguard/wg0.conf

wg-quick up wg0
ip r a 192.168.128.0/22 via 192.168.119.3
sleep infinity
