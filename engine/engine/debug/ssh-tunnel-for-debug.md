# Reverse tunnel

debug-isard-host --> NAT   --> public-gw  <-- hypers / clients web

   
in public-gw:
* edit /etc/ssh/sshd_config and config:
    * PermitRootLogin yes
    * GatewayPorts yes
* Restart ssh:
  * systemctl restart ssh
* Copy authorized_keys in /root/.ssh

```bash
mkdir /root/.ssh
touch /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
echo "public_key content" > /root/.ssh/authorized_keys
```

in debug-isard-host

```angular2html
ssh -f -N -M -S ~/socket-test -R 443:127.0.0.1:443 root@public_gw
```