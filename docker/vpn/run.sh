cd /certs
if [ ! -f /certs/server_private.key ]
then
    ## Alert! All client public keys should be updated in databas
    ## It is done afterwards in wgadmin
    wg genkey | tee server_private.key | wg pubkey > server_public.key
fi

# Allows wireguard to reach guests in hypervisor
ip r a 192.168.128.0/22 via 192.168.119.3
cd /src
python3 wgadmin.py
