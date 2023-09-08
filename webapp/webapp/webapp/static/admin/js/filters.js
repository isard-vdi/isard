/*
* Copyright 2023 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

var callbackFunction = null
var callbackFunctionParams = {}
var grouping = null
var itemType = null
var consumer = null
var startDate = moment().subtract(29, 'days').format('YYYY-MM-DD')
var endDate = moment().format('YYYY-MM-DD')
var dateFilterOptions = {
  startDate: moment().subtract(29, 'days'),
  endDate: moment(),
  autoApply: true,
  showDropdowns: true,
  showWeekNumbers: true,
  timePicker: false,
  timePickerIncrement: 1,
  timePicker12Hour: true,
  ranges: {
    'Today': [moment(), moment()],
    'Yesterday': [moment().subtract(1, 'days'), moment().subtract(1, 'days')],
    'Last 7 Days': [moment().subtract(6, 'days'), moment()],
    'Last 30 Days': [moment().subtract(29, 'days'), moment()],
    'This Month': [moment().startOf('month'), moment().endOf('month')],
    'Last Month': [moment().subtract(1, 'month').startOf('month'), moment().subtract(1, 'month').endOf('month')]
  },
  opens: 'right',
  buttonClasses: ['btn btn-default'],
  applyClass: 'btn-small btn-primary',
  cancelClass: 'btn-small',
  format: 'MM/DD/YYYY',
  separator: ' to ',
  locale: {
    applyLabel: 'Submit',
    cancelLabel: 'Clear',
    fromLabel: 'From',
    toLabel: 'To',
    customRangeLabel: 'Custom',
    daysOfWeek: ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'],
    monthNames: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
    firstDay: 1
  }
};

var cb = function (start, end, label) {
  startDate = start.format('YYYY-MM-DD')
  endDate = end.format('YYYY-MM-DD')
  $('#reportrange_right span').html(start.format('MMMM D, YYYY') + ' - ' + end.format('MMMM D, YYYY'));
};

/**
 * Initializes filters. By default admin shows all categories data and managers all group data.
 * @param  {function} cbf function to be called when the filter changes
 * @param  {Array} filterList filters that will be created
 * @return {undefined}
*/
function initialize_filters(cbf, filterList, divId) {
  callbackFunction = cbf
  // Create and populate the filters
  $.each(filterList, function (pos, it) {
    var node = newFilterBox(it)
    $(divId).append(node)
    if (it.kind === 'dateRange') {
      $('#reportrange_right span').html(moment().subtract(29, 'days').format('MMMM D, YYYY') + ' - ' + moment().format('MMMM D, YYYY'));
      $('#reportrange_right').daterangepicker(dateFilterOptions, cb);
    }
    if (it.populate) {
      populateSelect(it, divId);
    }
  })
  // Create the filter buttons events
  if (cbf) {
    generate_events(divId)
  }
  generate_change_events(divId)
}


/**
 * Generates filters html.
 * @param  {String} item type of filter that will be generated.
 * @return {undefined}
 */
function newFilterBox(item, selected = null) {
  if (item.kind === 'select-multiple') {
    return `
            <div class="filter-item col-md-3 col-sm-8 col-xs-12 select2-container--focus select2-container--resize" id="filter-${item.value}" style="margin-bottom:20px;margin-right:10px" always-shown="${item.alwaysShown}" filterId="${item.value}">
              <label class="control-label" for="${item.label}">${item.label}</label>
              <select class="filter-box form-control" id="${item.value}" name="${item.value}[]"
              multiple="multiple" value="${selected}"></select>
              <div class="select2-resize-handle"></div>
            </div>
          `;
  } else if (item.kind === 'select') {
    return `
              <div class="filter-item col-md-3 col-sm-8 col-xs-12" id="filter-${item.value}" style="margin-bottom:20px;margin-right:10px" always-shown="${item.alwaysShown}" filterId="${item.value}">
                <label class="control-label" for="${item.label}">${item.label}</label>
                <select class="filter-box form-control" id="${item.value}" name="${item.value}" value="${selected}"></select>
              </div>
            `;
  } else if (item.kind === 'dateRange') {
    return `
            <div class="filter-item col-md-3 col-sm-8 col-xs-12" id="filter-${item.value}" style="margin-bottom:20px;margin-right:10px" always-shown="${item.alwaysShown}" filterId="${item.value}">
              <label class="control-label" for="${item.label}">${item.label}</label>
              <div id="reportrange_right" class="filter-box form-control col-xs-12 col-md-12 col-sm-12"
                <i class="glyphicon glyphicon-calendar fa fa-calendar"></i>
                <span></span> <b class="caret"></b>
              </div>
            </div>
        `;
  }
}

/**
 * Populates available filters dropdown.
 * @param  {String} item type of filter that will be populated.
 * @return {undefined}
 */
function populateSelect(item, divId) {
  const elem = $(divId + " #" + item.value);
  const select2Options = {
    placeholder: `Type to select a ${item.label}`,
    maximumSelectionLength: item.maxSelect || null,
    dropdownParent: $(divId)
  }
  elem.select2(select2Options);
  elem.attr("index", item.value);
  switch (item.value) {
    case ("grouping"):
      $.ajax({ url: '/api/v3/admin/usage/groupings_dropdown', type: 'GET' })
        .then(function (f) {
          $.each(f, function (key, type) {
            elem.append('<optgroup class="l1" label=' + key.charAt(0).toUpperCase() + key.slice(1) + '>');
            $.each(type, function (type_field, fields) {
              elem.append('<optgroup class="l2" label=' + type_field.charAt(0).toUpperCase() + type_field.slice(1) + '>');
              $.each(fields, function (pos, field) {
                elem.append(`<option id='${field.item_type}${field.id}' value='{ "parameters": "${field.parameters}", "id": "${field.id}", "itemType": "${field.item_type}"}'>${field.name}</option>`);
              });
              elem.append('</optgroup>');
            });
            elem.append('</optgroup>');
          });
          // Once finished populating select by default the desktop_all grouping
          grouping = $(`${divId} #grouping`).find("[id='desktop_all']").val();
          elem.val(grouping)
          $(`${divId} #grouping`).trigger("change");
          // If it's a manager by default show the group consumer selected, if it's an admin the category consumer
          $(`${divId} #consumer`).val($('meta[id=user_data]').attr('data-role') == 'manager' ? 'group' : 'category');
          $(`${divId} #consumer`).trigger("change");
          $('#btn-filter').trigger("click")
        })
      break;
  }
}

/**
 * Generates events
 * @return {undefined}
 */
function generate_events(divId) {
  $("#btn-filter").on("click", function () {
    for (var i = 0; i < $(divId).children(':visible').length; i++) {
      // Get the filters id to get its value
      let filterId = $(divId).children(':visible')[i].getAttribute('filterId')
      let key = $('#' + filterId).attr("index");
      if ($(divId).children(':visible')[i].getAttribute('always-shown') !== 'true') {
        key = 'items_ids'
      }

      if ($(divId).children(':visible')[i].getAttribute('filterid') === 'dateRange') {
        callbackFunctionParams['startDate'] = startDate
        callbackFunctionParams['endDate'] = endDate
      } else {
        callbackFunctionParams[key] = $('#' + filterId).val()
      }

    }
    callbackFunctionParams.itemType = JSON.parse($("#grouping").val()).itemType
    callbackFunction(callbackFunctionParams)
  })

  // TODO
  // $("#btn-clear").on("click", function () {
  //   $('.filter-box').each(function () {
  //     removeFilter($(this).attr('id'))
  //   })
  // });

}

function generate_change_events (divId) {
  valuesOptions = divId;
  $(divId + " #filter-grouping").on('change', function () {
    itemType = JSON.parse($("#grouping").val()).itemType
    fetchConsumers(divId);
  })
  $(valuesOptions + " #filter-consumer").on('change', function () {
    consumer = $(valuesOptions + ' #consumer').val();
    // Show hide 
    const item = $(valuesOptions + ' #consumer').val();
    if (item !== "null") {
      $(valuesOptions).children('[always-shown!=true][id!=filter-' + item + ']').hide();
      $(valuesOptions).children('[always-shown!=true][id=filter-' + item + ']').show();
    }
    $(valuesOptions + " #" + item).find('option').remove();
    fetchConsumerItems(divId);
  });
}

function fetchConsumers (divId) {
  $.ajax({
    url: '/api/v3/admin/usage/consumers/' + itemType,
    type: 'GET',
    async: false
  }).then(function (d) {
    $(divId + " #consumer").find('option').remove();
    $.each(d, function (pos, it) {
      $(divId + " #consumer").append('<option value=' + it + '>' + it + '</option>');
    })
  });
}

function fetchConsumerItems (divId) {
  $.ajax({
    url: '/api/v3/admin/usage/distinct_items/' + consumer + "/" + startDate + "/" + endDate,
    type: 'GET',
    async: false
  }).then(function (items) {
    $.each(items, function (pos, it) {
      $(divId + " #" + consumer).append('<option value=' + it.item_id + '>' + it.item_name + '</option>');
    })
  });
}


function removeFilter(name) {
  if ($('#filter-' + name + ' #' + name).val() && name !== 'category') {
    var title = $('#filter-' + name + ' #' + name).attr("index");
    $('#domains').DataTable().columns().every(function () {
      header = $(this.header()).text().trim().toLowerCase();
      if (header === title) {
        this.search('').draw();
      }
    });
  }
  if (name != 'category' || $('meta[id=user_data]').attr('data-role') == 'admin') {
    $('#filter-' + name).remove();
    $('#filter-select').append(`<option value="${name}">${name.charAt(0).toUpperCase() + name.slice(1).replace(/_/g, ' ')}</option>`);
    $('#filter-select').children('option').sort(function (a, b) {
      if (a.value === 'null') {
        return -1;
      } else if (b.value === 'null') {
        return 1;
      } else {
        return a.text.localeCompare(b.text);
      }
    }).appendTo('#filter-select'); $('#filter-select').val('null');
  }
}