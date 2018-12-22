# Isard VDI with SElinux enabled

Althought it can be disabled temporarily for testing purposes (setenforce 0),
it is highly recommended to apply selinux policy for nginx as follows:

Check that you have selinux enabled. You should have **SELINUX=enabled** 
in **/etc/selinux/config** file. If not, change it and reboot before continuing.

### Install audit2allow
```
sudo dnf install policycoreutils-devel
```

#### Once rethinkdb, nginx and isard services are running:
Try to access https://localhost so selinux blocks will be logged.
Then allow those rules:

```
grep nginx /var/log/audit/audit.log | audit2allow -M nginx
semodule -i nginx.pp
```

This will create rules for nginx to proxy to isard port 5000/tcp
