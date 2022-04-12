option v = {
    timeRangeStart: -1h,
    timeRangeStop: now(),
    windowPeriod: 10000ms,
}

option task = {
    name: "cpu",
    every: 1m,
}


        from(bucket: "isardvdi-go")
            |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
            |> filter(fn: (r) => r["_measurement"] == "system" and r["_field"] == "cpu_usage")
            |> aggregateWindow(every: v.windowPeriod, fn: mean, createEmpty: false)
            |> yield()
            |> to(bucket: "isardvdi-tasks", org: "isardvdi")
