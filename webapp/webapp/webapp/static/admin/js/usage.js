/*
* Copyright 2023 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

var selectedRows = {}

$(document).ready(function () {
  const filters = [
    {
      value: 'dateRange',
      label: 'Dates between',
      kind: 'dateRange',
      populate: false,
      alwaysShown: true
    },
    {
      value: 'grouping',
      label: 'Grouping',
      kind: 'select',
      populate: true,
      alwaysShown: true,
    },
    {
      value: 'consumer',
      label: 'Consumer',
      kind: 'select',
      populate: true,
      alwaysShown: true,
    },
    {
      value: 'category',
      label: 'Category',
      kind: 'select-multiple',
      maxSelect: 5,
      populate: true
    },
    {
      value: 'group',
      label: 'Group',
      kind: 'select-multiple',
      maxSelect: 5,
      populate: true
    },
    {
      value: 'user',
      label: 'User',
      kind: 'select-multiple',
      maxSelect: 5,
      populate: true
    },
    {
      value: 'desktop',
      label: 'Desktop',
      kind: 'select-multiple',
      maxSelect: 5,
      populate: true
    },
    {
      value: 'deployment',
      label: 'Deployment',
      kind: 'select-multiple',
      maxSelect: 5,
      populate: true
    },
    {
      value: 'template',
      label: 'Template',
      kind: 'select-multiple',
      maxSelect: 5,
      populate: true
    },
    {
      value: 'hypervisor',
      label: 'Hypervisor',
      kind: 'select-multiple',
      maxSelect: 5,
      populate: true
    },
  ]
  initialize_filters(createUsageTable, filters, '#filter-boxes')

});

$('#other-filters #incremental').on('ifChecked', function(event){
  showHideIncremental('#usageTable', true)
});

$('#other-filters #incremental').on('ifUnchecked', function(event){
  showHideIncremental('#usageTable', false)
});

function showHideIncremental (tableId, show) {
  if (show) {
    $(tableId).DataTable().columns().eq(0).each( function ( index ) {
      var column = $(tableId).DataTable().column( index );
      if ( !$(column.header()).hasClass( 'always-shown' ) && $(column.header()).hasClass( 'incremental' ) ) {column.visible(true)}
      if ( !$(column.header()).hasClass( 'always-shown' ) && !$(column.header()).hasClass( 'incremental' ) ) {column.visible(false)}
    })
  } else {
    $(tableId).DataTable().columns().eq(0).each( function ( index ) {
      var column = $(tableId).DataTable().column( index );
      if ( !$(column.header()).hasClass( 'always-shown' ) && !$(column.header()).hasClass( 'incremental' ) ) {column.visible(true)}
      if ( !$(column.header()).hasClass( 'always-shown' ) && $(column.header()).hasClass( 'incremental' ) ) {column.visible(false)}
    })
  }
}

$('#btn-view-graph').on('click', function (e) {
  $('#canvas-holder').html('')
  data = selectedRows
  $('#graphsModal').modal({
    keyboard: false
  }).modal('show');
  // Show one graph for each item selected
  $.each(data.items, function (pos, it) {
    $.ajax({
      type: "PUT",
      url: '/admin/usage',
      dataType: 'json',
      contentType: "application/json",
      data: JSON.stringify({
        items_ids: [it.id],
        item_type: data.itemType,
        start_date: data.startDate,
        end_date: data.endDate,
        grouping: data.grouping.parameters
      }),
      success: function (resp) {
        $.ajax({
          type: "GET",
          url: `/api/v3/admin/usage/credits/${data.consumer}/${data.itemType}/${it.id}/${data.grouping.id}/${data.startDate}/${data.endDate}`,
          dataType: 'json',
          contentType: "application/json",
          success: function (limits) {
            let graphTitle = it.name
            addChart(resp, it.id, graphTitle, null, limits, data.incremental ? 'inc' : 'abs')
          }
        })
      }
    })
  })
})


function createUsageTable(data) {
  if (!data.consumer) {
    $("#usageTable").html("<div class='alert alert-danger' role='alert'>There is no usage data computed. Contact the administrator if it's needed</div>")
    return
  }
  data.grouping = data.grouping ? { parameters: JSON.parse(data.grouping).parameters.split(','), id: JSON.parse(data.grouping).id, itemType: JSON.parse(data.grouping).itemType } : { parameters: null, id: '_all' }
  selectedRows = data
  var tableId = "#usageTable";
  // clear first
  if ($.fn.dataTable.isDataTable(tableId)) {
    $(tableId).DataTable().destroy();
  }
  
  //2nd empty html
  $(tableId + " tbody").empty();
  $(tableId + " thead").empty();
  $(tableId + ' thead').append('<tr></tr><tr></tr>')
  
  if (data.grouping.parameters.toString() !== "") {
    // This columns are always the same
    cols = [
      {
        'data': null,
        'className': 'select-checkbox always-shown',
        'width': '10px',
        'defaultContent': '<input type="checkbox" class="form-check-input"></input>'
      },
      {
        'data': 'item_id',
        'className': 'always-shown',
        'visible': false
      },
      {
        'data': 'item_name',
        'className': 'always-shown',
        'defaultContent': ''
      },
      {
        'data': 'item_consumer',
        'className': 'always-shown',
        'defaultContent': '',
        'visible': false
      }
    ]
    // These columns can change (custom fields can be added), therefore they're generated dynamically
    // Retrieve the info of the selected parameters in order to show its name on the header
    $.ajax({
      type: "PUT",
      url: '/admin/usage/list_parameters',
      dataType: 'json',
      contentType: "application/json",
      data: JSON.stringify({
        ids: data.grouping.parameters
      }),
      success: function (parameters) {
        // Add the header
        $(tableId + ' thead tr').first().append('<th rowspan="2">Selected</th><th rowspan="2">Item id</th><th rowspan="2">Name</th><th rowspan="2">Consumer</th>')
        $.each(parameters, function (pos, parameter) {
          // Add header dynamically
          $(tableId + ' thead tr').first().append(`<th colspan="3" title="${parameter.desc}\n${parameter.formula ? 'Applied formula: ' + parameter.formula : ''}">${parameter.name} <i class="fa fa-info-circle" aria-hidden="true"></i></th>`)
          $(tableId + ' thead tr').eq(1).append(`<th>Start</th><th>End</th><th>Incremental</th>`)
          cols.push({
              'data': 'start.abs.' + parameter.id,
              'defaultContent': 0,
              'visible': !data.incremental,
              'render': (value) => {
                return value ? value.toFixed(2) : 0
              }
            },
            {
              'data': 'end.abs.' + parameter.id,
              'defaultContent': 0,
              'visible': !data.incremental,
              'render': function (data, type, row) {
                if (data) {
                  value = data.toFixed(2)
                  if (row.end.abs[parameter.id] > row.start.abs[parameter.id]) {
                    return value + ` <i title="+${(row.end.abs[parameter.id] - row.start.abs[parameter.id]).toFixed(2)}" class="fa fa-caret-up fa-lg" style="color:orange;"></i>`
                  } else if (row.end.abs[parameter.id] < row.start.abs[parameter.id]) {
                    return value + ` <i title="${(row.end.abs[parameter.id] - row.start.abs[parameter.id].toFixed(2))}" class="fa fa-caret-down fa-lg" style="color:cornflowerblue;"></i>`
                  } else {
                    return value + ' <i class="fa fa-caret-right fa-lg" style="color:lightgrey;"></i>'
                  }
                } else {
                  return 0
                }
              }
            },
            {
              'data': '',
              'defaultContent': 0,
              'className': 'incremental',
              'visible': data.incremental,
              'render': (data, type, row) => {
                if (row.end.abs[parameter.id] > row.start.abs[parameter.id]) {
                  return (row.end.abs[parameter.id] - row.start.abs[parameter.id]).toFixed(2)
                } else {
                  return 0
                }
              }
            })
        })
        //3rd recreate Datatable object
        $(tableId).DataTable({
          processing: true,
          rowId: "id",
          deferRender: true,
          paging: true,
          cache: false,
          columns: cols,
          ajax: {
            url: "/admin/usage/start_end",
            contentType: "application/json",
            type: "PUT",
            data: function (d) {
              return JSON.stringify({
                items_ids: data.items_ids,
                start_date: data.startDate,
                end_date: data.endDate,
                grouping: data.grouping.parameters,
                item_type: data.grouping.itemType,
                item_consumer: data.consumer
              });
            },
          },
          sAjaxDataProp: "",
          language: {
            loadingRecords:
              '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
          },
          rowId: "id",
        })

        $(tableId).off('click', 'tr[role="row"]').on('click', 'tr[role="row"]', function (e) {
          toggleRow(this, e);
          selectedItems = []
          $.each($(tableId).DataTable().rows('.active').data(), function (key, value) {
            selectedItems.push({ id: value.item_id, name: value.item_name, consumer: value.item_consumer })
          });
          selectedRows['items'] = selectedItems
          $('#btn-view-graph').prop('disabled', selectedItems.length ? false : true)
          $('#btn-view-graph').prop('title', selectedItems.length ? 'Generate graph' : 'Select items from the table in order to generate its graph')
        })

        showExportButtons($(tableId).DataTable(), 'usage-buttons-row')
      }
    })

  } else {
    $('#usageTable tbody').html(`
      <div style="text-align:center; padding:10px; background:#f7f7f7;">
        <h4>No parameters in this grouping</h4>
      </div>
    `);
  }

}

function addChart(data, itemId, graphTitle, graphSubtitle, limits, kind) {

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
    // Configure the xAxis
    xAxis: [{
      type: 'category',
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
        return limitsMax && limitsMax > value.max ? parseInt(limitsMax) : value.max;
      }
    }]
  };

  if (kind === 'abs') {
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
  }
  // Initialize the ECharts instance and set the option
  $(`#canvas-holder`).append(`
    <div id="canvas-holder-${itemId}">
    </div>
  `)
  let canvas = document.createElement("canvas")
  canvas.width = 1500
  canvas.height = 400
  $(`#canvas-holder-${itemId}`).append(canvas)
  var chart = echarts.init(canvas)
  chart.setOption(option)
  if (kind === 'abs') {
    $(`#canvas-holder-${itemId}`).append(`
    <div id="graph-other-filters">
      <div class="col-md-12 col-sm-12 col-xs-12" style="margin-bottom:20px;margin-right:10px">
        <label for="incremental">
          <input type="checkbox" id="incremental-${itemId}" title="Will show the difference between the end date value and the start date value">
          View incremental values
        </label>
      </div>
    </div>
  `)
  } else {
    $(`#canvas-holder-${itemId}`).append(`
    <div id="graph-other-filters">
      <div class="col-md-12 col-sm-12 col-xs-12" style="margin-bottom:20px;margin-right:10px">
        <label for="incremental">
          <input type="checkbox" checked id="incremental-${itemId}" title="Will show the difference between the end date value and the start date value">
          View incremental values
        </label>
      </div>
    </div>
  `)
  }
  addChartTable(data, itemId, graphTitle, limits)

  let hr = document.createElement("hr")
  $(`#canvas-holder-${itemId}`).append(hr)

  // Resize the chart to fit the container
  window.addEventListener('resize', function () {
  });
}

function addChartTable(data, itemId, graphTitle, limits) {
  let exportButtons = document.createElement('div')
  exportButtons.setAttribute('class', 'row ' + itemId + '-buttons-row')
  let table = document.createElement("table")
  table.setAttribute('id', itemId)
  table.setAttribute('style', 'width: 100%; padding-left: 25px; padding-right: 25px')
  table.setAttribute('class', "table cell-border text-center")
  $(`#canvas-holder-${itemId}`).append(exportButtons)
  $(`#canvas-holder-${itemId}`).append(table)
  cols = [
    {
      'title': 'Date',
      'data': 'date',
      'className': 'always-shown',
      'defaultContent': '',
      'render': (date) => {
        return new Date(date).toLocaleDateString('en-US', { year: 'numeric', month: '2-digit', day: '2-digit' })
      }
    }
  ]

  // This columns can change (custom fields can be added), therefore they're generated dynamically
  $.each(Object.keys(data[0].abs), function (pos, it) {
    cols.push(
      {
        'title': it,
        'data': 'abs.' + it,
        'defaultContent': 0,
        'render': (value) => {
          return value ? value.toFixed(2) : 0
        }
      },
      {
        'title': it + ' inc',
        'data': 'inc.' + it,
        'className': 'incremental',
        'defaultContent': 0,
        'visible': false,
        'render': (value) => {
          return value ? value.toFixed(2) : 0
        }
      }
    )
  })

  table = $('#' + itemId).DataTable({
    data: data,
    processing: true,
    rowId: "id",
    deferRender: true,
    paging: true,
    cache: false,
    columns: cols
  })

  $(`#graph-other-filters #incremental-${itemId}`).on('change', function(event){
    $(`#canvas-holder-${itemId}`).html('')
    addChart(data, itemId, graphTitle, null, limits, this.checked ? 'inc' : 'abs')
    showHideIncremental('#' + itemId, this.checked ? true : false)
  });

  showExportButtons(table, itemId + '-buttons-row')
}
