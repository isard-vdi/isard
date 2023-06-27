/*
* Copyright 2023 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

var selectedRows = {}
var render_table_groupings, table_limits, table_parameters, table_category_credits;

$(document).ready(function () {
  render_table_parameters();
  render_table_limits();
  render_table_groupings();
  render_table_category_credits();

  // CREDIT

  $('#btn-category_credit_add').on('click', function () {
    showModal('#modalAddCategoryCredit');
    populateCategoryCredit('#modalAddCategoryCreditForm');
    $('#modalAddCategoryCreditForm :checkbox').iCheck('uncheck').iCheck('update');
    addDateRangePicker('#modalAddCategoryCreditForm');
  });

  $('#modalAddCategoryCredit #send').on('click', function () {
    var form = $('#modalAddCategoryCreditForm');
    data = form.serializeObject();
    form.parsley().validate();
    delete data['id'];
    data['item_type'] = 'category';
    data['category_id'] = data['item_id'];
    data['start_date'] = moment(data['start_date'], "MM/DD/YYYY").format("YYYY-MM-DD");
    data['end_date'] = ('end_date-cb' in data) ? moment(data['end_date'], "MM/DD/YYYY").format("YYYY-MM-DD") : null;

    if (data['end_date'] == null || moment(data['end_date']).isAfter(data['start_date'])) {
      if (form.parsley().isValid()) {
        addItem('credit', data, table_category_credits);
      }
    } else {
      new PNotify({
        title: `ERROR updating credit`,
        text: "The end date must be later than the start date.",
        type: 'error',
        hide: true,
        icon: 'fa fa-warning',
        delay: 5000,
        opacity: 1
      })
    }
  });

  $('#modalEditCategoryCredit #send').on('click', function () {
    var form = $('#modalEditCategoryCreditForm');
    data = form.serializeObject();
    form.parsley().validate();
    data['item_type'] = 'category';
    data['category_id'] = data['item_id'];
    data['start_date'] = moment(data['start_date'], "MM/DD/YYYY").format("YYYY-MM-DD");
    data['end_date'] = ('end_date-cb' in data) ? moment(data['end_date'], "MM/DD/YYYY").format("YYYY-MM-DD") : null;

    if (data['end_date'] == null || moment(data['end_date']).isAfter(data['start_date'])) {
      if (form.parsley().isValid()) {
        editItem('credit', data, table_category_credits);
      };
    } else {
      new PNotify({
        title: `ERROR updating credit`,
        text: "The end date must be later than the start date.",
        type: 'error',
        hide: true,
        icon: 'fa fa-warning',
        delay: 5000,
        opacity: 1
      })
    }

  });

  // GROUPINGS

  $('#btn-parameter_grouping_add').on('click', function () {
    showModal('#modalAddParameterGrouping');
    fetchAvailableParameters('#modalAddParameterGrouping');
    populateItemType('#modalAddParameterGrouping');
  });

  $('#modalAddParameterGrouping #send').on('click', function () {
    var form = $('#modalAddParameterGroupingForm');
    data = form.serializeObject();
    form.parsley().validate();
    delete data['id'];

    if (form.parsley().isValid()) {
      addItem('grouping', data, table_groupings);
    };
  });

  $('#modalEditParameterGrouping #send').on('click', function () {
    var form = $('#modalEditParameterGroupingForm');
    data = form.serializeObject();
    form.parsley().validate();

    if (form.parsley().isValid()) {
      editItem('grouping', data, table_groupings);
    };
  });

  // LIMITS

  $('#btn-limit_add').on('click', function () {
    showModal('#modalAddLimits');
  });

  $('#modalAddLimits #send').on('click', function () {
    var form = $('#modalAddLimitsForm');
    data = form.serializeObject();
    form.parsley().validate();
    delete data['id'];
    data['limits'] = {
      'soft': parseInt(data['soft']),
      'hard': parseInt(data['hard']),
      'exp_min': parseInt(data['exp_min']),
      'exp_max': parseInt(data['exp_max'])
    }
    if (form.parsley().isValid()) {
      addItem('limit', data, table_limits);
    };
  });

  $('#modalEditLimits #send').on('click', function () {
    var form = $('#modalEditLimitsForm');
    data = form.serializeObject();
    form.parsley().validate();
    data['limits'] = {
      'soft': parseInt(data['soft']),
      'hard': parseInt(data['hard']),
      'exp_min': parseInt(data['exp_min']),
      'exp_max': parseInt(data['exp_max'])
    }

    if (form.parsley().isValid()) {
      editItem('limit', data, table_limits);
    };
  });

  // PARAMETERS

  $('#btn-parameter_add').on('click', function () {
    showModal('#modalAddParameters');
    fetchAvailableParameters('#modalAddParameters');
    $('#modalAddParameters #item_id').append("<option value='Desktop'>Desktop</option>");
  });

  $('#modalAddParameters #send').on('click', function () {
    var form = $('#modalAddParametersForm');
    data = form.serializeObject();
    form.parsley().validate();
    data['custom'] = true;
    try {
      math.parse(data['formula']);
    } catch {
      new PNotify({
        title: `Invalid formula`,
        text: 'The formula must have a valid format. Please ensure that brackets are correctly closed, mathematical symbols are used correctly, and any other syntax rules are followed.',
        type: 'error',
        hide: true,
        icon: 'fa fa-warning',
        delay: 5000,
        opacity: 1
      })
      return;
    }

    if (form.parsley().isValid()) {
      addItem('parameter', data, table_parameters);
    };
  });

  $('#modalEditParameters #send').on('click', function () {
    var form = $('#modalEditParametersForm');
    data = form.serializeObject();
    form.parsley().validate();
    data['custom'] = true;
    try {
      math.parse(data['formula']);
    } catch {
      new PNotify({
        title: `Invalid formula`,
        text: 'The formula must have a valid format. Please ensure that parentheses are correctly closed, mathematical symbols are used correctly, and any other syntax rules are followed.',
        type: 'error',
        hide: true,
        icon: 'fa fa-warning',
        delay: 5000,
        opacity: 1
      })
      return;
    }

    if (form.parsley().isValid()) {
      editItem('parameter', data, table_parameters);
    };
  });

  // CONSOLIDATE

  $("#btn-consolidate-desktops").on("click", function () {
    showModal('#modalConsolidateDesktops');
    $('#modalConsolidateDesktopsForm #days').append(`
      <option value="all">Beggining of logs</option>
      <option selected value="7">7 days ago</option>
    `);
  })

  $('#modalConsolidateDesktops #send').on('click', function () {
    var formData = $('#modalConsolidateDesktopsForm').serializeObject();
    consolidate('desktops', formData.days);
  });

  $("#btn-consolidate-users").on("click", function () {
    showModal('#modalConsolidateUsers');
    $('#modalConsolidateUsersForm #days').append(`
      <option value="all">Beggining of logs</option>
      <option selected value="7">7 days ago</option>
    `);
  })

  $('#modalConsolidateUsers #send').on('click', function () {
    var formData = $('#modalConsolidateUsersForm').serializeObject();
    consolidate('users', formData.days);
  });


  $("#btn-consolidate-storage").on("click", function () {
    consolidate('storage', false);
  })

  $("#btn-consolidate-media").on("click", function () {
    consolidate('media', false);
  })
});

function render_table_category_credits() {
  table_category_credits = $('#table-category_credit').DataTable({
    "ajax": {
      "url": "/api/v3/admin/usage/category_credits",
      "contentType": "application/json",
      "type": 'GET',
    },
    "sAjaxDataProp": "",
    "language": {
      "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
    },
    "rowId": "id",
    "deferRender": true,
    "columns": [
      { "data": "item_id",
      "render": function (data, type, row) {
        return row.category_name;
      }
      },
      { "data": "item_type", },
      {
        "data": "grouping_id",
        "render": function (data, type, row) {
          return row.grouping_name;
        }
      },
      {
        "data": "start_date",
        "render": function (data, type, row) {
          return moment(row.start_date).format("DD-MM-YYYY");
        }
      },
      {
        "data": "end_date",
        "render": function (data, type, row) {
          if (row.end_date) {
            return moment(row.end_date).format("DD-MM-YYYY");
          } else {
            return '-'
          }
        }
      },
      {
        "data": "limits",
        "render": function (data, type, row) {
          return row.limits.name;
        }
      },
      {
        "orderable": false,
        "data": null,
        "width": "100px",
        "render": function (data, type, row) {
          if (moment(row.end_date).isAfter(moment()) || !row.end_date) {
            return `<button class="btn btn-xs btn-info btn-edit-credit" type="button" data-placement="top" ><i class="fa fa-pencil"></i></button>
                    <button class="btn btn-xs btn-danger btn-delete-credit" type="button" data-placement="top" ><i class="fa fa-times"></i></button>`;
          } else {
            return null;
          }
        }
      },
    ],
  });
};

function render_table_groupings() {
  table_groupings = $('#table_groupings').DataTable({
    "ajax": {
      "url": "/api/v3/admin/usage/groupings",
      "contentType": "application/json",
      "type": 'GET',
    },
    "sAjaxDataProp": "",
    "language": {
      "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
    },
    "rowId": "id",
    "deferRender": true,
    "columns": [
      { "data": "name", },
      { "data": "item_type", },
      { "data": "item_sub_type", },
      { "data": "desc", },
      {
        "data": "parameters",
        "render": function (data, type, row) {
          return data.join(', ');
        }
      },
      {
        "orderable": false,
        "data": null,
        "width": "100px",
        "render": function (data, type, row) {
          if (!(['_all', '_system', '_custom']).includes(row.id)) {
            return `<button class="btn btn-xs btn-info btn-edit-grouping" type="button" data-placement="top" ><i class="fa fa-pencil"></i></button>
                    <button class="btn btn-xs btn-danger btn-delete-grouping" type="button" data-placement="top" ><i class="fa fa-times"></i></button>`;
          } else {
            return null;
          }
        }
      },
    ],
  });
};

function render_table_limits() {
  table_limits = $('#table_limits').DataTable({
    "ajax": {
      "url": "/api/v3/admin/usage/limits",
      "contentType": "application/json",
      "type": 'GET',
    },
    "sAjaxDataProp": "",
    "language": {
      "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
    },
    "rowId": "id",
    "deferRender": true,
    "columns": [
      { "data": "name", },
      { "data": "desc", },
      { "data": "limits.soft", },
      { "data": "limits.hard", },
      { "data": "limits.exp_min", },
      { "data": "limits.exp_max", },
      {
        "orderable": false,
        "data": null,
        "width": "100px",
        "render": function (data, type, row) {
          return `<button class="btn btn-xs btn-info btn-edit-limit" type="button" data-placement="top" ><i class="fa fa-pencil"></i></button>
                    <button class="btn btn-xs btn-danger btn-delete-limit" type="button" data-placement="top" ><i class="fa fa-times"></i></button>`;
        }
      },
    ],
  });
};

function render_table_parameters() {
  table_parameters = $('#table_parameters').DataTable({
    "ajax": {
      "url": "/api/v3/admin/usage/parameters",
      "contentType": "application/json",
      "type": 'PUT',
      "data": function(d){return JSON.stringify({})}
    },
    "sAjaxDataProp": "",
    "language": {
      "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
    },
    "rowId": "id",
    "deferRender": true,
    "columns": [
      { "data": "id", },
      { "data": "custom",
        "render": function (data, type, row) {
        if (data == false) {
          return 'System';
        }
        return 'Custom';
      } },
      { "data": "item_type", },
      { "data": "name" },
      { "data": "desc" },
      { "data": "formula",
      "render": function (data, type, row) {
        if (data == null) {
          return '-';
        }
        return data;
      }},
      { "data": "units",
      "render": function (data, type, row) {
        if (data == null) {
          return '-';
        }
        return data;
      } },
      {
        "orderable": false,
        "data": null,
        "width": "100px",
        "render": function (data, type, row) {
          if (row.custom) {
            return `<button class="btn btn-xs btn-info btn-edit-parameter" type="button" data-placement="top" ><i class="fa fa-pencil"></i></button>
                    <button class="btn btn-xs btn-danger btn-delete-parameter" type="button" data-placement="top" ><i class="fa fa-times"></i></button>`;
          } else {
            return null;
          }
        }
      },
    ],
  });
};

function fetchAvailableParameters(modal) {
  $.ajax({
    type: 'GET',
    url: '/api/v3/admin/table/usage_parameter',
    contentType: "application/json",
    success: function (parameter) {
      var parameterList = [];

      $.each(parameter, function (key, value) {
        $(modal + " #available-parameters").append(`<a title="${value.name} (${value.desc})" value="${value.id}" class="list-group-item list-group-item-action">${value.id}</a>`);
        $(modal + ' #parameters').append(`<option title="${value.desc}" value="${value.id}">${value.name}</option>`)
        parameterList.push(value.id);
      });

      $(modal + ' #available-parameters a').off('click').on('click', function () {
        parameter_id = $(this)[0].text
        $(modal + ' #formula').val($(modal + ' #formula').val() + parameter_id);
      });

      $(modal + ' #parameters').select2({
        placeholder: "Click to select a list of parameters",
      });

      parameterList = parameterList.join("|")
      var regex = `^([+-/*\(\)^ ]|\\d+|${parameterList})*$`;
      $(modal + ' #formula').attr("pattern", regex);
    }
  })

}

function populateCategoryCredit(modal) {
  $(modal + ' #item_type').append(`
    <option selected>Category</option>
  `)

  $.ajax({
    type: 'GET',
    url: '/api/v3/admin/table/categories',
    contentType: "application/json",
    success: function (category) {
      $.each(category, function (key, value) {
        $(modal + " #item_id").append(`<option title="${value.description ? value.description : ''}" value="${value.id}">${value.name}</option>`);
      });
      $(modal + " #item_id").select2({
        dropdownParent: $(modal)
      });
    }
  });

  $.ajax({
    type: 'GET',
    url: '/api/v3/admin/usage/groupings',
    contentType: "application/json",
    success: function (grouping) {
      $.each(grouping, function (key, value) {
        $(modal + " #grouping_id").append(`<option title="${value.desc ? value.desc : ''}" value="${value.id}">${value.name}</option>`);
      });
    }
  });

  $.ajax({
    type: 'GET',
    url: '/api/v3/admin/usage/limits',
    contentType: "application/json",
    success: function (limit) {
      $.each(limit, function (key, value) {
        $(modal + " #limits").append(`<option title="${value.desc}"  value="${value.id}">${value.name}</option>`);
      });
    }
  });

}

function showModal(modal_id) {
  $(modal_id).modal({ backdrop: 'static', keyboard: false }).modal('show');
  $(`${modal_id}Form`)[0].reset();

  $(modal_id + " option").each(function () {
    $(this).remove();
  });
}
function populateItemType(modal) {
  $(modal + ' #item_type').append(`
    <option value='desktop'>Desktop</option>
    <option value='media'>Media</option>
    <option value='storage'>Storage</option>
    <option value='user'>User</option>
  `);
}

function addDateRangePicker(modal) {
  $(modal + ' #start_date-calendar').daterangepicker({
    value: parseInt(moment().format('DD-MM-YYYY')),
    singleDatePicker: true,
    showDropdowns: true,
    minYear: parseInt(moment().format('YYYY')) - 5,
    maxYear: parseInt(moment().format('YYYY')) + 5
  }, function (start, end, label) {
  })

  $(modal + ' #end_date-cb').on('ifChecked', function (event) {
    $(modal + ' #end_date-calendar').daterangepicker({
      value: parseInt(moment().format('DD-MM-YYYY')),
      singleDatePicker: true,
      showDropdowns: true,
      minYear: parseInt(moment().format('YYYY')) - 5,
      maxYear: parseInt(moment().format('YYYY')) + 5
    }, function (start, end, label) {
    })
    $(modal + ' #end_date-calendar').prop('disabled', false);
  })

  $(modal + ' #end_date-cb').on('ifUnchecked', function (event) {
    $(modal + ' #end_date-calendar').prop('disabled', true);
    $(modal + ' #end_date-calendar').val('');
  })
}

function selectParameterList(modal, row) {
  $(modal + ' #parameters').select2({
    placeholder: "Click to select a list of parameters",
  });

  $.ajax({
    type: 'GET',
    url: '/api/v3/admin/table/usage_parameter',
    contentType: "application/json",
    success: function (parameter) {
      $.each(parameter, function (key, value) {
        $(modal + ' #parameters').append(`<option title="${value.desc}" value="${value.id}">${value.name}</option>`)
      });

      $.each(row.data().parameters, function (key, param) {
        var optionText = "";
        optionText = $(modal + " #parameters").find("option[value='" + param + "']").eq(0).text();
        var newOption = new Option(optionText, param, true, true);
        $(modal + " #parameters").append(newOption).trigger('change');
      });
    }
  });
}

function addItem(kind, data, datatable) {
  url = (kind == 'credit') ? `/api/v3/admin/usage/${kind}s/${data.item_type}` : `/api/v3/admin/usage/${kind}s`

  $.ajax({
    type: 'POST',
    url: url,
    data: JSON.stringify(data),
    contentType: "application/json",
    success: function (data) {
      $('form').each(function () { this.reset() });
      $('.modal').modal('hide');
      new PNotify({
        title: 'Added',
        text: `${kind.charAt(0).toUpperCase() + kind.slice(1)} added successfully`,
        hide: true,
        delay: 2000,
        opacity: 1,
        type: 'success'
      })
      datatable.ajax.reload().draw();
    },
    error: function (data) {
      new PNotify({
        title: `ERROR adding ${kind}`,
        text: data.responseJSON.description,
        type: 'error',
        hide: true,
        icon: 'fa fa-warning',
        delay: 5000,
        opacity: 1
      })
    }
  });
}

function editItem(kind, data, datatable) {
  url = (kind == 'credit') ? `/api/v3/admin/usage/${kind}s/${data.item_type}` : `/api/v3/admin/usage/${kind}s`

  $.ajax({
    type: 'PUT',
    url: url,
    data: JSON.stringify(data),
    contentType: "application/json",
    success: function (data) {
      $('form').each(function () { this.reset() });
      $('.modal').modal('hide');
      new PNotify({
        title: 'Updated',
        text: `${kind.charAt(0).toUpperCase() + kind.slice(1)} updated successfully`,
        hide: true,
        delay: 2000,
        opacity: 1,
        type: 'success'
      })
      datatable.ajax.reload().draw();
    },
    error: function (data) {
      new PNotify({
        title: `ERROR updating ${kind}`,
        text: data.responseJSON.description,
        type: 'error',
        hide: true,
        icon: 'fa fa-warning',
        delay: 5000,
        opacity: 1
      })
    }
  });
}

function deleteItem(kind, id, datatable) {
  url = (kind == 'credit') ? `/api/v3/admin/usage/${kind}s/category/${id}` : `/api/v3/admin/usage/${kind}s/${id}`;

  new PNotify({
    title: 'Confirmation Needed',
    text: `Are you sure you want to delete this ${kind}?`,
    hide: false,
    opacity: 0.9,
    confirm: {
      confirm: true
    },
    buttons: {
      closer: false,
      sticker: false
    },
    addclass: 'pnotify-center'
  }).get().on('pnotify.confirm', function () {
    $.ajax({
      type: 'DELETE',
      url: url,
      contentType: 'application/json',
      success: function (data) {
        new PNotify({
          title: 'Deleted',
          text: `${kind.charAt(0).toUpperCase() + kind.slice(1)} deleted successfully`,
          hide: true,
          delay: 2000,
          opacity: 1,
          type: 'success'
        })
        datatable.row('#' + id).remove().draw();
      },
      error: function (data) {
        new PNotify({
          title: `ERROR deleting ${kind}`,
          text: data.responseJSON.description,
          type: 'error',
          hide: true,
          icon: 'fa fa-warning',
          delay: 5000,
          opacity: 1
        })
      }
    })
  }).on('pnotify.cancel', function () {
  });
}

$('tbody').on('click', 'button', function () {
  var row = $(this).closest('table').DataTable().row($(this).closest('tr'));
  var id = row.data().id;

  // CREDIT

  if ($(this).hasClass('btn-edit-credit')) {
    var modal = "#modalEditCategoryCredit"

    showModal(modal);
    addDateRangePicker(modal);
    populateCategoryCredit(modal);

    $.ajax({
      type: 'GET',
      url: `/api/v3/admin/usage/category_credits/${id}`,
      contentType: 'application/json',
      success: function (data) {
        $(modal + ' #item_id').val(data.item_id)
        $(modal + ' #grouping_id').val(data.grouping_id)
        $(modal + ' #limits').val(data.limits.id)
        $(modal + ' #start_date-calendar').val(moment(data['start_date']).format("MM/DD/YYYY"))
        $(modal + ' #id').val(id)

        if (data.end_date) {
          $(modal + ' :checkbox').iCheck('check').iCheck('update');
          $(modal + ' #end_date-calendar').val(moment(data['end_date']).format("MM/DD/YYYY"))
        } else {
          $(modal + ' :checkbox').iCheck('uncheck').iCheck('update');
        }
      }
    })
  }

  if ($(this).hasClass('btn-delete-credit')) {
    deleteItem('credit', id, table_category_credits)
  }

  // GROUPINGS

  else if ($(this).hasClass('btn-edit-grouping')) {
    var modal = "#modalEditParameterGrouping";

    showModal(modal);
    populateItemType(modal);
    selectParameterList(modal, row);

    $(modal + ' #name').val(row.data().name);
    $(modal + ' #desc').val(row.data().desc);
    $(modal + ' #item_type').val(row.data().item_type);
    $(modal + ' #parameters').val(row.data().parameters);
    $(modal + ' #item_sub_type').val(row.data().item_sub_type);
    $(modal + ' #id').val(id);
  }

  else if ($(this).hasClass('btn-delete-grouping')) {
    deleteItem('grouping', id, table_groupings);
  }

  // LIMITS

  else if ($(this).hasClass('btn-edit-limit')) {
    var modal = '#modalEditLimits';

    showModal(modal);

    $(modal + ' #name').val(row.data().name);
    $(modal + ' #desc').val(row.data().desc);
    $(modal + ' #soft').val(row.data().limits.soft);
    $(modal + ' #hard').val(row.data().limits.hard);
    $(modal + ' #exp_min').val(row.data().limits.exp_min);
    $(modal + ' #exp_max').val(row.data().limits.exp_max);
    $(modal + ' #id').val(id);
  }

  else if ($(this).hasClass('btn-delete-limit')) {
    deleteItem('limit', id, table_limits);
  }

  // PARAMETERS

  else if ($(this).hasClass('btn-edit-parameter')) {
    var modal = '#modalEditParameters';

    showModal(modal);
    fetchAvailableParameters(modal);

    $(modal + ' #name').val(row.data().name);
    $(modal + ' #desc').val(row.data().desc);
    $(modal + ' #item_id').append("<option value='Desktop'>Desktop</option>");
    $(modal + ' #units').val(row.data().units);
    $(modal + ' #formula').val(row.data().formula);
    $(modal + ' #id').val(id);
  }

  else if ($(this).hasClass('btn-delete-parameter')) {
    deleteItem('parameter', id, table_parameters);
  }

});

// CONSOLIDATE

function consolidate(item_type, days) {
  url = days ? `/admin/usage/consolidate/${item_type}/${days}` : `/admin/usage/consolidate/${item_type}`
  $.ajax({
    type: "PUT",
    url: url,
    dataType: 'json',
    contentType: "application/json",
    success: function (resp) {
      new PNotify({ title: "Success", text: "Usage updated for " + item_type, type: "success" })
      $('form').each(function () { this.reset() });
      $('.modal').modal('hide');
    },
    error: function (data) {
      new PNotify({
        title: `ERROR consolidating ${item_type}`,
        text: data.responseJSON.description,
        type: 'error',
        hide: true,
        icon: 'fa fa-warning',
        delay: 5000,
        opacity: 1
      })
    }
  })
}