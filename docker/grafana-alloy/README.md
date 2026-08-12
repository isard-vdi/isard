# isard-grafana-alloy

Metrics, logs and profiling collector. `run.sh` copies the always-on files into
`/etc/alloy` and adds the optional ones when their key is set:

| File | Copied when |
|---|---|
| `config.alloy`, `logs.alloy`, `metrics.alloy` | always |
| `profiling.alloy` | `PYROSCOPE_EBPF=true` |
| `faro.alloy` | `FARO_ENABLED=true` |
| `debug.alloy` | `LOG_LEVEL=debug` |

Alloy has no conditionals in its config language, so this copy-per-key pattern in
`run.sh` is how a collector gets gated. A config change needs only a container
restart: the directory is bind-mounted, not baked into an image.

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
