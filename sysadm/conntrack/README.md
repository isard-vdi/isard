# Connection Tracking Optimization

Configuration files to apply on **all host machines** running any IsardVDI flavour
(web, hypervisor, video, all-in-one, etc.) — not inside containers.

## Sysctl Configuration

```bash
cp 99-isardvdi-conntrack.conf /etc/sysctl.d/
sysctl -p /etc/sysctl.d/99-isardvdi-conntrack.conf
```

Increases conntrack table from 262K to 2M entries and reduces TCP established
timeout from 5 days to 6 hours.

## NOTRACK Rules (Automatic)

NOTRACK rules for GENEVE and WireGuard tunnel traffic are automatically applied
by the `isard-hypervisor` and `isard-vpn` containers on startup. No manual
configuration needed.

## Monitoring

```bash
# Watch conntrack usage
watch -n 5 'echo "Conntrack: $(cat /proc/sys/net/netfilter/nf_conntrack_count) / $(cat /proc/sys/net/netfilter/nf_conntrack_max)"'

# Verify NOTRACK rules are applied
iptables -t raw -L -n -v

# Run comprehensive analysis
./conntrack-analysis.sh
./conntrack-analysis.sh -j | jq .  # JSON output
```

## Files

- `99-isardvdi-conntrack.conf` - Sysctl settings for conntrack optimization
- `conntrack-analysis.sh` - Connection tracking analysis tool
