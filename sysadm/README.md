# IsardVDI System Administration

This directory contains system administration tools and configuration files for IsardVDI.

## Files and Directories

- `upgrade.sh` - Automated upgrade script with comprehensive features
- `isardvdi.service` - Systemd service file for running IsardVDI as a system service
- `INSTALL.md` - Installation guide for new deployments
- `hypervisor/` - Hypervisor-specific configuration files
- `old/` - Legacy upgrade scripts (deprecated, kept for reference)

## Network Configuration

By default, IsardVDI opens the following container ports:

* `80/tcp` - HTTP traffic (redirects to HTTPS) and SPICE video protocol TLS tunnel
* `443/tcp` - HTTPS web interface and HTML5 video protocols
* `443/udp` - WireGuard VPN for user connections
* `4443/udp` - WireGuard VPN for hypervisor connections

Docker handles iptables rules automatically (default Docker behavior), but a properly configured firewall is still essential for security.

## Deployment Architectures

### Single Node Deployment (All-in-One)

For complete single-node installations:
- Uses the default `docker-compose.yml` (all-in-one flavor)
- Contains all services: web interface, engine, hypervisor, database, etc.

### Multi-Node with Internal Hypervisors

When using one public IsardVDI node with internal hypervisors:

**Main IsardVDI node:**
- Uses `web` flavor (creates `docker-compose.web.yml`)
- Publicly accessible on ports 80, 443 (TCP/UDP), 4443 (UDP)

**Internal hypervisors:**
- Use `hypervisor-standalone` flavor (creates `docker-compose.hypervisor-standalone.yml`)
- Require firewall configuration to forward specific ports to the main node

#### Building Different Flavors

Use the build script to create configuration for different deployment types:

```bash
# All-in-one (default)
FLAVOUR=all-in-one bash build.sh

# Web-only (for main node)
FLAVOUR=web bash build.sh

# Standalone hypervisor
FLAVOUR=hypervisor-standalone bash build.sh

# Hypervisor with video services
FLAVOUR=hypervisor bash build.sh
```

#### Firewall Configuration for Internal Hypervisors

Configure firewall zones for secure access:

**Infrastructure Zone** (for internal networks):
```bash
firewall-cmd --permanent --new-zone=infrastructure
firewall-cmd --permanent --zone=infrastructure --add-source=172.31.0.0/21
firewall-cmd --permanent --zone=infrastructure --add-rich-rule='rule family="ipv4" source address="172.31.0.0/21" accept'
```

**Hypervisor Zone** (for main IsardVDI access):
```bash
firewall-cmd --permanent --new-zone=hyper
# Allow specific source IPs (main IsardVDI nodes)
firewall-cmd --permanent --zone=hyper --add-source=172.16.254.200/32
firewall-cmd --permanent --zone=hyper --add-source=172.16.254.201/32

# SSH monitoring port (2022)
firewall-cmd --permanent --zone=hyper --add-rich-rule='rule family="ipv4" source address="172.16.254.200/32" port port="2022" protocol="tcp" accept'
firewall-cmd --permanent --zone=hyper --add-forward-port=port=2022:proto=tcp:toport=2022:toaddr=172.31.255.17

# Video ports (5900-7899)
firewall-cmd --permanent --zone=hyper --add-rich-rule='rule family="ipv4" source address="172.16.254.200/32" port port="5900-7899" protocol="tcp" accept'
firewall-cmd --permanent --zone=hyper --add-forward-port=port=5900-7899:proto=tcp:toport=5900-7899:toaddr=172.31.255.17
```

### Multi-Node with Public Hypervisors

For deployments where each hypervisor has a public IP:

**Main IsardVDI node (web-only):**
- Uses `web` flavor: `FLAVOUR=web bash build.sh`
- Opens: 80/tcp, 443/tcp, 443/udp, 4443/udp

**Public hypervisors:**
- Use `hypervisor` flavor: `FLAVOUR=hypervisor bash build.sh`
- Need SSH monitoring access from main node (port 2022)
- Provide video proxy access (ports 80/443 or custom ports)

Example firewall for public hypervisors:
```bash
firewall-cmd --permanent --new-zone=hyper
firewall-cmd --permanent --zone=hyper --add-source=83.53.72.181/32
firewall-cmd --permanent --zone=hyper --add-rich-rule='rule family="ipv4" source address="83.53.72.181/32" port port="2022" protocol="tcp" accept'
firewall-cmd --permanent --zone=hyper --add-forward-port=port=2022:proto=tcp:toport=2022:toaddr=172.31.255.17
```

### Available Deployment Flavors

The build system supports multiple deployment flavors:

- `all-in-one`: Complete single-node installation (default)
- `web`: Web interface and management services only
- `hypervisor`: Hypervisor with video proxy services  
- `hypervisor-standalone`: Hypervisor without video services
- `video-standalone`: Video proxy services only
- `storage`: Storage services only
- `monitor`: Monitoring services (Grafana, Prometheus, Loki)
- `web+monitor`: Combined web and monitoring
- `web+storage`: Combined web and storage
- `backupninja`: Standalone backup services

## Upgrade Management

### Automated Upgrades

Use the comprehensive upgrade script:

```bash
# Basic upgrade to latest version
./sysadm/upgrade.sh upgrade

# Upgrade to specific version
./sysadm/upgrade.sh upgrade v14.79.4

# Show changes before upgrading
./sysadm/upgrade.sh show-changes

# Setup automated weekly upgrades
./sysadm/upgrade.sh cron
```

### Upgrade Features

- **Version Management**: Supports version tags and branch names
- **Safety Checks**: Prevents downgrades and validates major version changes
- **Database Backup**: Automatic backup before upgrades
- **Multi-Config Support**: Handles multiple deployment configurations
- **Comprehensive Logging**: Detailed upgrade reports in `/opt/isard-local/upgrade-logs/`
- **Dry-Run Mode**: Preview changes with `show-changes` action

### Legacy Upgrade Scripts

Older upgrade scripts have been moved to the `old/` directory:
- `old/isard-upgrade-cron.sh` - Legacy upgrade script
- `old/pacemaker-upgrade-cron.sh` - Legacy Pacemaker-aware upgrade script

These are kept for reference but are deprecated. Use the new `upgrade.sh` script instead.

## System Service

To run IsardVDI as a systemd service:

```bash
# Copy service file
sudo cp sysadm/isardvdi.service /etc/systemd/system/

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable isardvdi
sudo systemctl start isardvdi

# Check status
sudo systemctl status isardvdi
```

## Security Considerations

1. **Firewall**: Always maintain proper firewall rules even with Docker's automatic iptables management
2. **VPN Access**: Configure WireGuard properly for secure remote access
3. **Network Segmentation**: Use appropriate network zones for different access levels
4. **Regular Updates**: Implement automated upgrade monitoring and testing
5. **Backup Strategy**: Regular database backups and configuration backup procedures

For detailed installation instructions, see `INSTALL.md`.
