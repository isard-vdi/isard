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

