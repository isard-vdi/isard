option task = {
    name: "visor_html5",
    every: 10s,
}

domains = from(bucket: "isardvdi-go")
    |> range(start: -10s, stop: now())
    |> filter(fn: (r) => r["_measurement"] == "domain" and r["_field"] == "viewer_port_spice")
    |> aggregateWindow(every: 30s, fn: last)

sockets = from(bucket: "isardvdi-go")
    |> range(start: -10s, stop: now())
    |> filter(fn: (r) => r["_measurement"] == "socket" and r["_field"] == "pid"
        // we use PID as we could have used any other socket field
        )
    |> aggregateWindow(every: 30s, fn: last)

join(tables: {domains, sockets}, on: ["_time"])
    |> filter(fn: (r) => r["source_port"] == r["_value_domains"])
    |> keep(
        columns: [
            "_time",
            "id",
            "_field_domains",
            "_value_domains",
            "hypervisor_domains",
        ],
    )
    |> rename(
        columns: {
            _field_domains: "viewer_type",
            _value_domains: "port",
            hypervisor_domains: "hypervisor",
        },
    )
    |> unique(column: "id")
    |> group(columns: ["_time", "id", "viewer_type", "hypervisor"])
    |> distinct(column: "viewer_type")
    |> count(column: "_value")
    |> drop(columns: ["id"])
    |> count(column: "_value")
    |> map(
        fn: (r) => ({r with
            _measurement: "hypervisor",
            _field: "viewers",
        }),
    )
    |> to(bucket: "isardvdi-tasks", org: "isardvdi")