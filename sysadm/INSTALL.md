# IsardVDI
## All in one

### Debian 10 (buster)

#### Install

##### Sources
```
cd /root
apt install git -y
git clone --depth 1 --branch develop https://github.com/isard-vdi/isard
```

##### Config & Personalization

Edit contents to fit your server installation.

```
cd isard
cp isardvdi.cfg.example isardvdi.cfg
vi isardvdi.cfg
```

##### Services & Security

Install docker, docker-compose and set basic firewall and fail2ban ssh jail.

```
cd sysadm
bash debian_docker.sh
bash debian_firewall.sh
cd ..
```

##### OPTION A: Pull from docker hub

```
bash build.sh
docker-compose pull && docker-compose up -d
```


##### OPTION B: Build from source

```
bash build.sh
docker-compose build && docker-compose up -d
```


