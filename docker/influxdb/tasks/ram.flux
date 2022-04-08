option v = {
    timeRangeStart: -1h,
    timeRangeStop: now(),
    windowPeriod: 10000ms,
}

option task = {
    name: "ram",
    every: 1m,
}

from(bucket: "isardvdi-go")
    |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
    |> filter(fn: (r) => r["_measurement"] == "hypervisor" and r["_field"] =~ /mem_(total|free|cached)/)
    |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")
    |> map(
        fn: (r) => ({
            _time: r["_time"],
            _measurement: "system",
            hypervisor: r.hypervisor,
            _value: 100.0 - float(v: r["mem_free"] + r["mem_cached"]) / float(v: r["mem_total"]) * 100.0,
        }),
    )
    |> map(
        fn: (r) => ({
            _time: r["_time"],
            _measurement: "system",
            _field: "ram_usage",
            _value: r["_value"],
            hypervisor: r.hypervisor,
        }),
    )
    |> aggregateWindow(every: v.windowPeriod, fn: last, createEmpty: false)
    |> yield()
    |> to(bucket: "isardvdi-tasks", org: "isardvdi")
