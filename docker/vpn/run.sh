# Start guacd
echo "$(date): INFO: Starting guacd server"
guacd -b 0.0.0.0 -L info -f >> /var/log/guacd 2>&1 &

# Start RDPGW
echo "$(date): INFO: Starting RDPGW server"
apk add --no-cache openssl
openssl req -x509 -nodes -newkey rsa:2048 -keyout server.key -out server.crt -days 3650 -subj "/C=GB/ST=London/L=London/O=Global Security/OU=IT Department/CN=*"
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
