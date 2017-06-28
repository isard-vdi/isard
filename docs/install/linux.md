# IsardVDI installation on FEDORA 25

## Install OS

Minimal Fedora 25 install
sudo dnf update -y

## Clone IsardVDI repository

```
sudo dnf install git
git clone https://github.com/isard-vdi/isard.git
```

## Install IsardVDI requirements

```
cd isard/install/
sudo dnf install wget gcc redhat-rpm-config python3-devel openldap-devel openssl-devel libvirt-python3 npm
sudo pip3 install -r requirements.pip3
```

```
sudo npm -g install bower
bower install
```

```
sudo wget http://download.rethinkdb.com/centos/7/`uname -m`/rethinkdb.repo -O /etc/yum.repos.d/rethinkdb.repo
sudo dnf install -y rethinkdb
sudo cp /etc/rethinkdb/default.conf.sample /etc/rethinkdb/instances.d/default.conf
sudo systemctl daemon-reload
sudo systemctl start rethinkdb
```

## Selinux and Firewalld
For testing purposes, just disable both till next reboot:

```
sudo setenforce 0
sudo systemctl stop firewalld
```

**Do not disable them in production!, please follow nginx.md and selinux.md documentation**

## Run the application

```
cd ..
./run.sh
```

You can browse to your computer port 5000
Default user is 'admin' and password 'isard'


# KNOWN ISSUES

## IsardVDI engine can't contact hypervisor(s)

### ssh authentication fail when connect: Server 'vdesktop6.escoladeltreball.org' not found in known_hosts

You should generate int your IsardVDI machine your ssh key and copy it to the hypervisor(s):
```
ssh-keygen
ssh-copy-id root@<hypervisor_hostname>
```


Now you should be able to connect to frontend through http://localhost:5000
Default user is admin and password isard.


# In hypervisors we need


in Fedora or centos:
```
dnf -y install openssh-server qemu-kvm libguestfs-tools
```

Check that you can connect to the hypervisor using ssh root@<hypervisor_hostname>

NOTE: Service sshd on hypervisor(s) should use ssh-rsa keys. Please check **/etc/ssh/sshd_config** on hypervisor that you have only **HostKey /etc/ssh/ssh_host_rsa_key** option active

## IsardVDI does not start

+ Check that you have rethinkdb database running: **systemctl status rethinkdb**
+ Check that rethinkdb tcp port 28015 it is open: **netstat -tulpn | grep 28015**
+ Check that there are no error logs on output.

