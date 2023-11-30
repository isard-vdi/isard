//   Copyright © 2023 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
//
//   This file is part of IsardVDI.
//
//   IsardVDI is free software: you can redistribute it and/or modify
//   it under the terms of the GNU Affero General Public License as published by
//   the Free Software Foundation, either version 3 of the License, or (at your
//   option) any later version.
//
//   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
//   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
//   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
//   details.
//
//   You should have received a copy of the GNU Affero General Public License
//   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
//
// SPDX-License-Identifier: AGPL-3.0-or-later



$.fn.echartHistory = function (data,text,width,height) {
    const $container = $(this);
    option = {
        scale: true,
        maintainAspectRatio: false,
        responsive: true,
        title: {
          text: text
        },
        xAxis: {
          type: 'category',
          data: data,
        },
        yAxis: {
          type: 'value',
        },
        series: [
          {
            name: 'text',
            type: 'line',
            showSymbol: false,
            data: data
          }
        ]
      };
    // Create a canvas element
    const canvas = document.createElement("canvas");
    canvas.height = height;
    canvas.width = width;
    // Append the canvas to the container
    $container.append(canvas);

    // Initialize ECharts instance and set options
    const chart = echarts.init(canvas);
    chart.setOption(option);

    $container.data('echartInstance', chart);
    return chart;
};


$.fn.echartGroupedItems = function (table, group_field, nested_array_field) {
    if (nested_array_field == null){
        kind="grouped_items"
    }else{
        kind="nested_array_grouped_items"
    }
    return this.each(function () {
      const $container = $(this);
      $.ajax({
        url: '/api/v3/admin/echart/'+kind,
        type: 'POST',
        data: JSON.stringify({
          "table": table,
          "group_field": group_field,
          "nested_array_field": nested_array_field,
        }),
        async: true
      }).then(function (d) {
        // ECharts chart configuration
        const option = {
            // legend: {
            //     orient: "vertical",
            //     left: "left",
            //     data: $.each(d, function (i, v) {
            //         return v.name;
            //     })
            // },
            grid: {
                containLabel: true,
            },
            series: [
                {
                    type: 'pie',
                    data: d,
                    roseType: 'area',
                    label: {
                        formatter: '{b}: {d}%',
                        // fontSize: 12,
                        // fontWeight: 'bold',
                        overflow: 'break',
                    },
                    labelLine: {
                        length: 10,
                        length2: 5
                    }
                }
            ]
        };

        // Create a canvas element
        const canvas = document.createElement("canvas");

        // Append the canvas to the container
        $container.append(canvas);

        // Initialize ECharts instance and set options
        const chart = echarts.init(canvas);
        chart.setOption(option);

        $container.data('echartInstance', chart);
      });
    });
  };

$.fn.echartDailyItems = function (table, date_field) {
    return this.each(function () {
      const $container = $(this);
      $.ajax({
        url: '/api/v3/admin/echart/daily_items',
        type: 'POST',
        data: JSON.stringify({
          "table": table,
          "date_field": date_field,
        }),
        async: false
      }).then(function (d) {
        // ECharts chart configuration
        const option = {
            title: {
                text: 'Daily '+date_field+' items',
                left: 'center'
            },
            tooltip: {
                trigger: 'axis'
            },
            markPoint: {
                data: [
                    {type: 'max', name: 'Max'},
                    {type: 'min', name: 'Min'}
                ]
            },
            // legend: {
            //     data: ['Desktops starting time'],
            //     top: 'top'
            // },
            dataZoom: [
                {
                    type: 'slider',
                    height: 20,
                    start: 90,
                    end: 100,
                    bottom: 20,
                }
            ],
            toolbox: {
                show: true,
                feature: {
                    magicType: {type: ['line', 'bar']},
                    restore: {},
                    saveAsImage: {},
                }
            },
            xAxis: [
                {
                    type: 'category',
                    boundaryGap: false,
                    data: d.x,
                    axisLabel: {
                        formatter: function (value) {
                            var date = new Date(value);
                            return date.getDate();
                        },
                        rotate: 0,
                    }
                },
                {
                    type: 'category',
                    boundaryGap: false,
                    data: d.x,
                    axisLabel: {
                        formatter: function (value, index) {
                            var date = new Date(value);
                            var monthName = getMonthName(date.getMonth());
                            // Show the month name only on the first day of the month or when the month changes
                            if (index === 0 || (index > 0 && new Date(d.x[index - 1]).getMonth() !== date.getMonth())) {
                                return monthName;
                            } else {
                                return '';
                            }
                        },
                        rotate: 0,
                    }
                }
            ],
            yAxis: {
                type: 'value',
                scale: true,
                axisLabel: {
                    formatter: function (value) {
                        return value + ' entries';
                    },
                    margin: 20 // Situate label a little bit more to the left to not overlap
                },
                min: 0,
                max: 'dataMax'
            },
            series: [
                {
                    name: 'Desktops',
                    type: 'bar',
                    data: d.series[date_field],
                    itemStyle: {
                        normal: {
                            color: function(params) {
                                var colorList = ['#C1232B','#B5C334','#FCCE10','#E87C25','#27727B',
                                                 '#FE8463','#9BCA63','#FAD860','#F3A43B','#60C0DD',
                                                 '#D7504B','#C6E579','#F4E001','#F0805A','#26C0C0'];
                                var date = new Date(d.x[params.dataIndex]);
                                return colorList[date.getMonth()];
                            },
                            opacity: 0.6
                        }
                    }
                },
            ]
        };

        // Create a canvas element
        const canvas = document.createElement("canvas");
        canvas.width = 1500;
        canvas.height = 200;

        // Append the canvas to the container
        $container.append(canvas);

        // Initialize ECharts instance and set options
        const chart = echarts.init(canvas);
        chart.setOption(option);

        $container.data('echartInstance', chart);

        // Define the getXaxisDataRange function within the echartDailyItems scope
        function getXaxisDataRange() {
          const option = chart.getOption();
          const startValue = option.dataZoom[0].startValue;
          const endValue = option.dataZoom[0].endValue + 1;
          const xaxisData = option.xAxis[0].data.slice(startValue, endValue);
          return {
            start: xaxisData[0],
            end: xaxisData[xaxisData.length - 1]
          };
        }
  
        // Expose the getXaxisDataRange function as a property of the chart instance
        chart.getXaxisDataRange = getXaxisDataRange;

      });
    });
};


var monthNames = ["January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
];

function getMonthName(monthNumber) {
    return monthNames[monthNumber] || '';
}

function debounce(fn, delay) {
    let timeoutId;
    return function () {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => {
            fn.apply(this, arguments);
        }, delay);
    };
}