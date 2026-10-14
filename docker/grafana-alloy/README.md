# isard-grafana-alloy

Metrics, logs and profiling collector. `run.sh` copies the always-on files into
`/etc/alloy` and adds the optional ones when their key is set:

| File | Copied when |
|---|---|
| `config.alloy`, `logs.alloy`, `metrics.alloy` | always |
| `profiling.alloy` | `PYROSCOPE_EBPF=true` |
| `faro.alloy` | `FARO_ENABLED=true` |
| `debug.alloy` | `LOG_LEVEL=debug` |
| `journal.alloy` | always, unless `HOST_JOURNAL_LOGS=false` |

Alloy has no conditionals in its config language, so this copy-per-key pattern in
`run.sh` is how a collector gets gated. A config change needs only a container
restart: the directory is bind-mounted, not baked into an image.

## Host journal

`journal.alloy` ships the host's systemd journal as `{job="journal"}` with `unit`,
`level` and `transport` labels. The faults that explain an outage of the host itself
are only there, never in a container log: a hung NIC queue (`NETDEV WATCHDOG`),
iSCSI sessions dropping (`detected conn error`), an NFS server not responding, hung
tasks, OOM kills, a cluster resource moving.

- **Paths:** the default journal locations are read, so it works with a persistent
  journal (`/var/log/journal`, through the `/var/log` bind) and with a volatile one
  (`/run/log/journal`, through `/var/run`, which is `/run` in the image). libsystemd
  opens only the journal directory named after the machine id, so the compose binds
  the host's `/etc/machine-id`: without it the source starts healthy and reads
  nothing.
- **Allow-list, not deny-list:** the kernel plus the units named in the relabel
  rule. `sshd`, `sudo` and `systemd-logind` stay on the host on purpose: they name
  people. Adding a unit means adding it to the regex.
- **Dropped:** firewall per-packet kernel lines (`[UFW …]`, `IN=… OUT=… SRC=`),
  which carry client IPs and can be thousands per minute on a public host.
- **Rate limit:** 20 lines/s with a burst of 200, so a kernel stuck in a loop cannot
  flood Loki; the first lines are the useful ones.
- **Off switch:** `HOST_JOURNAL_LOGS=false` (the file is removed on the next start).

## Collector policy

The `set_collectors` lists in `metrics.alloy` are not "everything node_exporter
offers": every entry must have a consumer in `docker/grafana/dashboards` or
`docker/vmalert/rules`, and must be cheap enough to run on every host of every
installation. Grep before adding one, and add its panel in the same change — a
collector nobody queries is pure cost, and a panel with no collector reads as a
broken dashboard.

Deliberately left out, with their panels removed: `arp`, `interrupts` (per-CPU ×
per-IRQ, hundreds of series), `processes` (walks every `/proc/<pid>`, which undoes
the work done to keep this container cheap at rest), `sockstat`, `softnet`,
`systemd` (usable only with `unit-include`), and `powersupplyclass` — server
boards expose no `/sys/class/power_supply`, so on real hardware it is silent.

### Why there are two unix exporters

The container has its own network namespace, so anything the kernel serves from
`/proc/net` — `netdev`, `netstat`, `conntrack`, `sockstat`, `softnet`, `arp`,
`nfs`, `nfsd` — describes the container and not the host. The compose runs this
container with `pid: host`, so PID 1 is the host init and **`/proc/1/net` is the
host namespace**; those collectors therefore live in a second exporter with
`procfs_path = "/proc/1"` and reach the real interfaces, sockets and conntrack.

Keep the split when adding a collector: per-namespace ones go in the second
exporter, everything else in the first. Putting the same collector in both
produces duplicate series — `lo` exists in every namespace.

`netclass` is the exception that stays in the first: it reads the bind-mounted
host `/sys`, so it already sees the real interfaces — it does still report every
bridge and veth the container runtime creates, which is churn worth filtering
separately. Mount-namespace collectors
(`mountstats`) see whatever is propagated through the `/:/rootfs:ro,rslave` bind.
Everything else (`cpu`, `meminfo`, `diskstats`, `filesystem`, `hwmon`, `vmstat`,
`timex`, …) is namespace-independent.

## Fans and temperatures

In-band via the `hwmon` and `thermal_zone` collectors, which read the host `/sys`
bind mount: `node_hwmon_temp_celsius`, `node_hwmon_temp_crit_celsius`,
`node_cooling_device_cur_state`. No dependencies, no credentials, works on every
host — but **`hwmon` exposes temperatures only: fan RPM comes from the BMC**. On a
server board measured for this, the five chips (CPU package, both NVMe, both NIC
ASICs) yielded seventeen temperature inputs and **zero fan inputs**. A virtual
machine has none of it, so expect silence there and readings only on bare metal.

For fan RPM the alternative is an out-of-band `ipmi-exporter`, deliberately not
implemented here: it needs `ipmitool` (or FreeIPMI) plus per-host BMC credentials,
which this stack has no channel for, so it belongs to whatever manages the hosts.
The two are complementary rather than alternatives — the same host can feed both,
the in-band collectors from `/sys` and the exporter from the BMC.

Setting the BMC fan profile is a host operation, not a monitoring one; on
Supermicro boards it is `ipmitool raw 0x30 0x45 0x01 0x02` for the optimized
profile and `ipmitool raw 0x30 0x45 0x00` to read the current one.
