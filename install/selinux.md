# Isard VDI with SElinux enabled

Althought it can be disabled temporarily for testing purposes (setenforce 0),
it is highly recommended to apply selinux policy for isard-vdi as follows:

Check that you have selinux enabled. You should have **SELINUX=enabled** 
in **/etc/selinux/config** file. If not, change it and reboot before continuing.

### Install audit2allow
```
sudo dnf install policycoreutils-devel
```

#### From isard-vdi.service:
```
grep isard-vdi.service /var/log/audit/audit.log | audit2allow
restorecon -R -v /etc/systemd/system/isard-vdi.service
```

#### Once rethinkdb and isard-vdi services have started:
Try to access http://localhost:5000 so selinux blocks will be logged.
Then allow those rules:

```
grep nginx /var/log/audit/audit.log | audit2allow -M nginx
selinux -i nginx.pp
```

This will create rules for nginx to serve isard-vdi.
