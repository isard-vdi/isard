# IsardVDI Installation Guide

## All-in-One Installation

### Prerequisites

#### System Requirements

- Linux distribution with Docker support (Ubuntu 20.04+, Debian 11+, RHEL 8+, etc.)
- Minimum 4GB RAM, 8GB+ recommended
- Docker and Docker Compose installed
- Git installed

#### Install Dependencies

Install Docker and Docker Compose following the official documentation:

- Docker Engine: <https://docs.docker.com/engine/install/>
- Docker Compose: <https://docs.docker.com/compose/install/>

Install Git if not already available:

```bash
# Ubuntu/Debian
apt update && apt install git -y

# RHEL/CentOS/Rocky/AlmaLinux
dnf install git -y
```

### Installation Steps

#### 1. Download Source Code

```bash
cd /opt
git clone --depth 1 --branch develop https://github.com/isard-vdi/isardvdi
cd isardvdi
```

#### 2. Configuration

Copy and edit the configuration file to fit your server installation:

```bash
cp isardvdi.cfg.example isardvdi.cfg
vi isardvdi.cfg
```

Key settings to configure:

- `DOMAIN`: Your server's domain name
- `DOCKER_IMAGE_TAG`: Version to deploy (latest stable recommended)
- `WEBAPP_ADMIN_PWD`: Admin password
- Network and storage settings as needed

#### 3. Deployment Options

##### Option A: Deploy with Pre-built Images (Recommended)

```bash
bash build.sh
docker compose pull && docker compose up -d
```

##### Option B: Build from Source

```bash
bash build.sh
docker compose build && docker compose up -d
```

#### 4. System Service (Optional)

To run IsardVDI as a system service, copy the provided service file:

```bash
cp sysadm/isardvdi.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable isardvdi
systemctl start isardvdi
```

### Post-Installation

1. Access the web interface at `https://your-domain`
2. Login with the admin credentials configured in `isardvdi.cfg`
3. Follow the initial setup wizard to configure categories, users, and templates

### Firewall Configuration

Ensure the following ports are accessible:

- `80/tcp`: HTTP (redirects to HTTPS)
- `443/tcp`: HTTPS (web interface)
- `443/udp`: WireGuard VPN (user connections)
- `4443/udp`: WireGuard VPN (hypervisor connections)

### Upgrading

Use the automated upgrade script:

```bash
cd /opt/isardvdi
./sysadm/upgrade.sh upgrade
```

For more upgrade options, see: `./sysadm/upgrade.sh --help`
