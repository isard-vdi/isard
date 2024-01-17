$(document).ready(function () {
    getGraphsConfig()
})

function getGraphsConfig() {
    $.ajax({
        url: "/api/v3/admin/usage/reset_date", // TODO: User the real endpoint to retrieve graph conf
        type: 'GET',
        dataType: 'json',
        contentType: 'application/json'
    })
        .then(function (conf) {
            conf = [] // TODO: remove this when calling the real endpoint
            conf.sort((a, b) => a.priority - b.priority);
            $.each(conf, function (pos, it) {
                $('#usageGraphs').append(`
                    <div id="canvas-holder-${it.grouping}">
                    <div id="canvas-${it.grouping}" (window:resize)="onResize($event)"></div>
                    </div>
                `)
                $(`#canvas-holder-${it.grouping}`).html(`<div id="canvas-${it.grouping}" class="col-md-6 col-sm-6 col-xs-12" (window:resize)="onResize($event)"></div>`)
                const currentDate = new Date();
                const startDate = new Date(currentDate);
                startDate.setDate(currentDate.getDate() - it['x_axis_days']);
                const endDate = currentDate;
                getUsageCredits(it, startDate, endDate)
            })
        })
}

function getUsageCredits(conf, startDate, endDate) {
    $.ajax({
        type: "GET",
        url: `/api/v3/admin/usage/credits/category/desktop/${$('meta[id=user_data]').attr('data-categoryId')}/${conf.grouping}/${moment(startDate).utc().format('YYYY-MM-DD')}/${moment(endDate).utc().format('YYYY-MM-DD')}`,
        dataType: 'json',
        contentType: "application/json",
        success: function (limits) {
            getUsageGraphs(conf, limits, startDate, endDate)
        }
    })
}

function getUsageGraphs(conf, limits, startDate, endDate) {
    $.ajax({
        url: '/api/v3/admin/usage/grouping/' + conf.grouping,
        type: 'GET',
        dataType: 'json',
        contentType: 'application/json'
    }).then(function (grouping) {
        $.ajax({
            url: '/api/v3/admin/usage',
            type: 'PUT',
            dataType: 'json',
            contentType: 'application/json',
            data: JSON.stringify({
                items_ids: [$('meta[id=user_data]').attr('data-categoryId')],
                item_type: grouping.item_type,
                start_date: moment(startDate).utc().format('YYYY-MM-DD'),
                end_date: moment(endDate).utc().format('YYYY-MM-DD'),
                grouping: grouping.parameters,
            }),
        }).then(function (graph) {
            addChart(graph, $('meta[id=user_data]').attr('data-categoryId'), conf.grouping, conf.title, conf.subtitle, limits, 'abs')
        });
    });
}

function addChart(data, itemId, groupingId, graphTitle, graphSubtitle, limits, kind) {
    // Extract the legend keys from the data
    var legendKeys = Object.keys(data[0][kind]);
    // Sort the data by its date in order to show correctly in graph
    data.sort(function (a, b) {
        return new Date(a.date) - new Date(b.date)
    })


    // Transform the data for ECharts
    var transformedData = legendKeys.map(function (key) {
        return {
            name: key,
            type: 'line',
            data: data.map(function (item) {
                return [moment(item.date).utc().format('YYYY-MM-DD'), item[kind][key]]
            }),
            markLine: {
                data: [
                ]
            },
            markArea: {
                data: [
                ]
            }
        };
    });

    // Create the option object
    var option = {
        title: {
            text: graphTitle,
            subtext: graphSubtitle,
            id: 'graph-title',
        },
        grid: {
            top: '95',
        },
        // Set the type of chart
        series: transformedData,
        toolbox: {
            show: true,
            feature: {
                magicType: {
                    show: true,
                    title: {
                        line: 'Line',
                        bar: 'Bar'
                    },
                    type: ['line', 'bar']
                },
                saveAsImage: {
                    show: true,
                    title: "Save Image"
                }
            }
        },

        // Configure the legend
        legend: {
            data: legendKeys,
            top: 45,
            itemHeight: 10,
            itemWidth: 10
        },
        calculable: true,
        tooltip: {
            triggerOn: "mousemove",
            show: true,
            trigger: "axis",
            valueFormatter: (value) => value ? (value).toFixed(2) : value,
            textStyle: {
                align: 'left'
            }
        },
        axisPointer: {
            snap: true,
        },
        // Configure the xAxis
        xAxis: [{
            type: 'category',
            axisLine: {
                onZero: false,
            },
            axisLabel: {
                formatter: (function (value) {
                    if (/^en\b/.test(navigator.language)) {
                        return new Date(value).toLocaleDateString('en-US', { year: 'numeric', month: '2-digit', day: '2-digit' })
                    } else {
                        return new Date(value).toLocaleDateString('es-ES', { year: 'numeric', month: '2-digit', day: '2-digit' })
                    }
                })
            }
        }],

        // Configure the yAxis
        yAxis: [{
            type: 'value',
            // Adjust the chart view to the limits or max value
            max: function (value) {
                let limitsMax = Math.max.apply(Math, limits.map(function (o) {
                    if (o.limits) {
                        return o.limits.hard
                    } else {
                        return 0
                    }
                }))
                return limitsMax && limitsMax > value.max ? parseInt(limitsMax) : (value.max).toFixed(2);
            }
        }]
    };

    $.each(limits, function (pos, credit) {
        if (credit.limits) {
            let usageStartDate = new Date(data[0].date)
            let limitStartDate = new Date(credit.start_date)
            let graphLimitStartDate = limitStartDate < usageStartDate ? usageStartDate : limitStartDate

            let usageEndDate = new Date(data[data.length - 1].date)
            let limitEndDate = new Date(credit.end_date)
            let graphLimitEndDate = limitEndDate > usageEndDate ? usageEndDate : limitEndDate
            graphLimitStartDate = moment(graphLimitStartDate).utc().format('YYYY-MM-DD')
            graphLimitEndDate = moment(graphLimitEndDate).utc().format('YYYY-MM-DD')

            option.series[0].markLine.data.push(
                // Draw hard limit line
                [
                    // Start of the line
                    {
                        xAxis: graphLimitStartDate,
                        yAxis: credit.limits.hard,
                        symbol: 'none',
                        lineStyle: {
                            normal: {
                                color: "#ac2925"
                            }
                        },
                        label: {
                            normal: {
                                show: true,
                                position: 'insideEndTop',
                                formatter: 'Hard limit'
                            }
                        }
                    },
                    // End of the line
                    {
                        xAxis: graphLimitEndDate,
                        yAxis: credit.limits.hard,
                        symbol: 'none'
                    }
                ],
                // Draw soft limit line
                [
                    // Start of the line
                    {
                        xAxis: graphLimitStartDate,
                        yAxis: credit.limits.soft,
                        symbol: 'none',
                        lineStyle: {
                            normal: {
                                color: "#eea236"
                            }
                        },
                        label: {
                            normal: {
                                show: true,
                                position: 'insideEndTop',
                                formatter: 'Soft limit'
                            }
                        }
                    },
                    // End of the line
                    {
                        xAxis: graphLimitEndDate,
                        yAxis: credit.limits.soft,
                        symbol: 'none'
                    }
                ]
            )

            option.series[0].markArea.data.push(
                // Draw area between exp_min and exp_max
                [
                    {
                        xAxis: graphLimitStartDate,
                        yAxis: credit.limits.exp_min,
                        itemStyle: { color: 'rgba(200, 200, 200, 0.5)', opacity: 0.5 },
                        label: {
                            show: true,
                            position: 'inside',
                            formatter: 'Expected use area',
                            color: '#3b3e47'
                        },
                    },
                    {
                        xAxis: graphLimitEndDate,
                        yAxis: credit.limits.exp_max
                    }
                ]
            )
        }
    })
    var chart = echarts.init($(`#canvas-${groupingId}`)[0])
    chart.setOption(option)
    chart.resize({ width: $(`#canvas-${groupingId}`).width(), height: "400" });

    window.addEventListener('resize', function () {
        chart.resize({ width: $(`#canvas-${groupingId}`).width(), height: "400" });
    })

}