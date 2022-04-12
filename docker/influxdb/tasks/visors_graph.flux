option task = {
    name: "visors_graph",
    every: 10s,
}

domains = from(bucket: "isardvdi-go")
    |> range(start: -30s, stop: now())
    |> filter(fn: (r) => r["_measurement"] == "domain" and (r["_field"] == "viewer_port_spice" or r["_field"] == "viewer_port_spice_tls" or r["_field"] == "viewer_port_websocket"))
    |> aggregateWindow(every: 30s, fn: last)

sockets = from(bucket: "isardvdi-go")
    |> range(start: -30s, stop: now())
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
    |> group(columns: ["hypervisor"])
    |> aggregateWindow(
        every: 30s,
        column: "id",
        fn: (column, tables=<-) => tables
            |> unique(column: column)
            |> count(column: column),
    )
    |> rename(columns: {id: "_value"})
    |> map(
        fn: (r) => ({r with
            _measurement: "hypervisor",
            _field: "visors_graph",
            hypervisor: r.hypervisor,
        }),
    )
    |> yield(name: "visors")
    |> to(bucket: "isardvdi-tasks", org: "isardvdi")
    