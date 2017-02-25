# Isard VDI installation

This will install Isard VDI on a fresh minimal Fedora 25 server.
Execute all the commands from this install folder.

## Rethinkdb database
```
sudo wget http://download.rethinkdb.com/centos/7/`uname -m`/rethinkdb.repo -O /etc/yum.repos.d/rethinkdb.repo
dnf install python rethinkdb
sudo cp /etc/rethinkdb/default.conf.sample /etc/rethinkdb/instances.d/default.conf
```

## Fedora 25 requirements
```
sudo dnf -y install python3 python3-pip redhat-rpm-config python-devel openldap-devel npm
```

## pip3 Python library requirements
```
sudo pip3 install -r requirements.pip
```

## Bower install javascript
```
npm -g install bower
bower install
```

## Systemd Service
```
sudo cp server/isard-vdi.service /etc/systemd/system/
sudo systemctl daemon-reload
```

## SElinux

For testing purposes just disable it temporarily:
```
sudo setenforce 0
```
In production enable selinux following the selinux.md file instructions.


## Firewalld

For testing purposes just allow temporarily default flask tcp port 5000.

On production we do recommend using nginx. Please follow nginx.md file.
```
firewall-cmd --zone=public --add-port=5000/tcp
```

## Start app
```
systemctl start isard-vdi
```

Now you should be able to connect to frontend through http://localhost:5000
Default user is admin and password isard.
