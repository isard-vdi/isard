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

$('#other-filters #join-checkbox').on('ifChecked', function(event){
  $("#usageTable").DataTable().column( 2 ).visible( true );
});

$('#other-filters #join-checkbox').on('ifUnchecked', function(event){
  $("#usageTable").DataTable().column( 2 ).visible( false );
});

$('#btn-edit-reset-date').on('click', function () {
  var modal = '#modalEditResetDates';
  $(modal).modal({ backdrop: 'static', keyboard: false }).modal('show');
  $(`${modal}Form`)[0].reset();

  $(modal + " option").each(function () {
    $(this).remove();
  });
  $(modal + ' #reset-date-list').empty();
  $('#modalEditResetDates #send').prop("disabled", true);
  $('#modalEditResetDates #send').prop("title", "Must add or delete a date first");


  $.ajax({
    url: `/api/v3/admin/usage/reset_date`,
    type: 'GET'
  }).done(function (data) {
    $.each(data, function (key, value) {
      $(modal + ' #reset-date-list').append(
        `<a class="list-group-item list-group-item-action" value=${value}>
            ${value}  <button style="float:right;" class="btn btn-delete btn-xs" type="button"><i class="fa fa-times" style="color:darkred"></i></button>
          </a>`
      );
    });

    $(modal + ' #add_date-calendar').daterangepicker({
      value: parseInt(moment().format('YYYY-MM-DD')),
      singleDatePicker: true,
      showDropdowns: true,
      minYear: parseInt(moment().format('YYYY')) - 5,
      maxYear: parseInt(moment().format('YYYY')) + 5
    }, function (start, end, label) { });

  });
})

$('#modalEditResetDates #add-date').on('click', function () {
  var modal = "#modalEditResetDates";
  var value = $(modal + " #add_date-calendar").val();
  var dateList = $("#reset-date-list a").map(function () {
    return $(this).attr('value');
  }).get();

  if (!dateList.includes(value)) {
    $(modal + ' #reset-date-list').append(
      `<a class="list-group-item list-group-item-action" value=${value}>
        ${value} <button style="float:right;" class="btn-delete btn btn-xs" type="button"><i class="fa fa-times" style="color:darkred"></i></button>
      </a>`
    );
    dateList.push(value)
    $(modal + " #date-list").val(dateList.join(','))
  }
  $('#reset-date-list').trigger('change')
})

$('#modalEditResetDates ul').on('click', 'button', function (e) {
  if ($(this).hasClass('btn-delete')) {
    $(this).closest('a').remove();
  }
  $('#reset-date-list').trigger('change')
});

if ($('meta[id=user_data]').attr('data-role') != 'admin') {
  $('#btn-edit-reset-date').hide();
}

$('#modalEditResetDates #send').on('click', function (e) {
  var form = $('#modalEditResetDatesForm');
  data = form.serializeObject();
  var dateList = $("#reset-date-list a").map(function () {
    return $(this).attr('value');
  }).get();

  $.ajax({
    type: 'PUT',
    url: "/api/v3/admin/usage/reset_dates",
    dataType: "json",
    async: false,
    contentType: "Application/json",
    data: JSON.stringify({ "date_list": dateList })
  }).success(function (data) {
    $('form').each(function () { this.reset() });
    $('.modal').modal('hide');
    showResetDate();
  }).error( function (data) {
    new PNotify({
      title: `ERROR`,
      text: data.responseJSON.description,
      hide: false,
      opacity: 0.9,
      type: 'error'
    })
  });
})

$('#modalEditResetDates #reset-date-list').on('change', function () {
  $('#modalEditResetDates #send').prop("disabled", false);
  $('#modalEditResetDates #send').prop("title", "Set all reset dates to match the list")
})


$('#btn-view-graph').on('click', function (e) {
  $('#canvas-holder').html('')
  $('#usageGraphs').html('')
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
            addChart(resp, it.id, `${it.consumer} ${it.name}`, data.incremental ? 'Showing incremental values' : 'Showing absolute values', limits, data.incremental ? 'inc' : 'abs')
            $(`#table-${it.id}`).html('')
            addChartTable(resp, it.id, it.name, it.consumer, limits, data.incremental ? 'inc' : 'abs')
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
  showResetDate();
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
        'data': null, // Will render link to Join duplicated item_id
        'className': 'always-shown toggle-vis',
        'visible': false,
        'render': function (data, type, row) {
          if (row.duplicated_item_id === true ) {
            return `<button
                type="button"
                class="btn btn-pill-right btn-info btn-xs join-button"
                data-item_id="${row.item_id}"
                title="Join all items with same id with the latest computed name"
              >
                <i class="fa fa-link"></i>
                ${row.item_id}
              </button>`
          } else {
            return ''
          }
        }
      },
      {
        'data': 'item_name',
        'className': 'always-shown',
        'defaultContent': ''
      },
      {
        'data': 'item_description',
        'className': 'always-shown',
        'defaultContent': '',
        visible: data.consumer === 'category' ? true : false
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
        $(tableId + ' thead tr').first().append('<th rowspan="2">Selected</th><th rowspan="2">Item id</th><th rowspan="2">Join duplicates</th><th rowspan="2">Name</th><th rowspan="2">Description</th><th rowspan="2">Consumer</th>')
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
                value = (row.end.abs[parameter.id] - row.start.abs[parameter.id]).toFixed(2)
                if (row.end.abs[parameter.id] > row.start.abs[parameter.id]) {
                    if (row.end.abs[parameter.id] > row.start.abs[parameter.id]) {
                      return value + ` <i title="+${(row.end.abs[parameter.id] - row.start.abs[parameter.id]).toFixed(2)}" class="fa fa-caret-up fa-lg" style="color:orange;"></i>`
                    } else if (row.end.abs[parameter.id] < row.start.abs[parameter.id]) {
                      return value + ` <i title="${(row.end.abs[parameter.id] - row.start.abs[parameter.id].toFixed(2))}" class="fa fa-caret-down fa-lg" style="color:cornflowerblue;"></i>`
                    } else {
                      return value + ' <i class="fa fa-caret-right fa-lg" style="color:lightgrey;"></i>'
                    }
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


$('tbody').on('click', 'button', function (e) {
  if ($(this).hasClass('join-button')) {
    consumer_id = $(this).data("item_id")

    new PNotify({
      title: `Join items with ID ${consumer_id}?`,
      text: "This action is irreversible and will unify all consumers under the most recent name.",
      hide: false,
      opacity: 0.9,
      confirm: { confirm: true },
      buttons: { closer: false, sticker: false },
      history: { history: false },
      addclass: "pnotify-center",
    })
      .get()
      .on("pnotify.confirm", function () {
        $.ajax({
          type: "PUT",
          url: `/api/v3/admin/usage/unify/${consumer_id}/item_name`,
          dataType: 'json',
          contentType: "application/json",
          success: function (data) {
            new PNotify({
              title: 'Joined duplicated consumers',
              text: `All items have been grouped under the name: ${data.name}`,
              hide: true,
              delay: 2000,
              opacity: 1,
              type: 'success'
            })
            $("#usageTable").DataTable().ajax.reload();
          },
          error: function ({responseJSON: {description} = {}}) {
            const msg = description ? description : 'Something went wrong';
            new PNotify({
              title: "ERROR joining duplicates",
              text: msg,
              type: 'error',
              icon: 'fa fa-warning',
              hide: true,
              delay: 15000,
              opacity: 1
            });
          }
        })
      })
      .on("pnotify.cancel", function () {});
  }
});

function addChart(data, itemId, graphTitle, graphSubtitle, limits, kind) {
  $(`#canvas-holder-${itemId}`).html(`<div id="canvas-${itemId}" (window:resize)="onResize($event)"></div>`)
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
  $('#usageGraphs').append(`
    <div id="canvas-holder-${itemId}">
      <div id="canvas-${itemId}" (window:resize)="onResize($event)"></div>
    </div>
    <div id="table-${itemId}">
    </div>
  `)
  var chart = echarts.init($(`#canvas-${itemId}`)[0])
  chart.setOption(option)
  var modalWidth = $('.modal-dialog').width();
  chart.resize({width: modalWidth - 50, height: "400"});

  window.addEventListener('resize', function () {
    var modalWidth = $('.modal-dialog').width();
    chart.resize({width: modalWidth - 50, height: "400"});
  })

}

function addChartTable(data, itemId, itemName, itemConsumer, limits, kind) {
  $(`#table-${itemId}`).append(`
    <div id="graph-other-filters">
      <div class="col-md-12 col-sm-12 col-xs-12" style="margin-bottom:20px;margin-right:10px">
        <label for="incremental">
          <input type="checkbox" ${kind === 'inc' ? 'checked' : ''} id="incremental-${itemId}" title="Will show the difference between the end date value and the start date value">
          View incremental values
        </label>
        <div class="x_panel" id="reset_date_graph" title="All data resets to zero from this date onwards">
          <b>Reset date:</b>
          <span class="reset_date_value"></span>
        </div>
      </div>
    </div>
    <div class="row ${itemId}-buttons-row">
    </div>
    <table id="${itemId}" style="width: 100%; padding-left: 25px; padding-right: 25px" class="table cell-border text-center">
    </table>
    <hr/>
  `)
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
  $.ajax({
    type: "PUT",
    url: '/admin/usage/list_parameters',
    dataType: 'json',
    contentType: "application/json",
    data: JSON.stringify({
      ids: Object.keys(data[0].abs)
    }),
    success: function (parameters) {
      // This columns can change (custom fields can be added), therefore they're generated dynamically
      $.each(parameters, function (pos, parameter) {
        cols.push(
          {
            'title': `
              ${parameter.name} <i class='fa fa-info-circle' aria-hidden='true' title="${parameter.desc}\n${parameter.formula ? 'Applied formula: ' + parameter.formula : ''}"></i><br>
              <em style="font-weight: normal;">${parameter.units ? parameter.units: '-'}</em>
            `,
            'data': 'abs.' + parameter.id,
            'defaultContent': 0,
            'visible': !(kind === 'inc'),
            'render': (value) => {
              return value ? value.toFixed(2) : 0
            }
          },
          {
            'title': `
              ${parameter.name} <i class='fa fa-info-circle' aria-hidden='true' title="${parameter.desc}\n${parameter.formula ? 'Applied formula: ' + parameter.formula : ''}"></i><br>
              <em style="font-weight: normal;">${parameter.units ? parameter.units: '-'}</em>
            `,
            'data': 'inc.' + parameter.id,
            'className': 'incremental',
            'defaultContent': 0,
            'visible': kind === 'inc',
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
        addChart(data, itemId, `${itemConsumer} ${itemName}`, this.checked ? 'Showing incremental values' : 'Showing absolute values', limits, this.checked ? 'inc' : 'abs')
        showHideIncremental('#' + itemId, this.checked ? true : false)
      });

      showExportButtons(table, itemId + '-buttons-row')
    }
  })
  $('#reset_date_graph .reset_date_value').html($('#reset_date .reset_date_value').html());
}

function showResetDate() {
  $('.reset_date_value').empty()
  $.ajax({
    url: `/api/v3/admin/usage/reset_date/${selectedRows.startDate}/${selectedRows.endDate}`,
    type: 'GET'
  }).done(function (data) {
    $('.reset_date_value').html(data.join(', '));
  })
}