//   Copyright © 2017-2024 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases, Miriam Melina Gamboa Valdez
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

function getGroupParam() {
  return window.location.href.slice(window.location.href.indexOf('?') + 1).split('searchStorageId=')[1];
}

$(document).ready(function () {
  $template = $(".template-storage-detail");
  $('#status').attr('disabled', 'disabled')
  addCheckboxListeners();

  // Storage ready table
  let tableId = '#storage'
  storage_ready = createDatatable(tableId, 'ready', function () {
    let searchStorageId = getGroupParam()
    if (searchStorageId) {
      storage_ready.api().column(3).search(searchStorageId).draw();
      storage_other.column(3).footer(3).firstChild.value = searchStorageId;
    }
  })
  $(tableId + " tbody").off('click').on('click', 'button', function () {
    let tr = $(this).closest("tr")
    let row = storage_ready.row(tr)
    switch ($(this).attr('id')) {
      case 'btn-details':
        showRowDetails(storage_ready, tr, row);
        break;
    }
  })

  // Other storage status dropdown populate
  $.ajax({
    type: "GET",
    url: "/api/v3/storage/status",
    success: function (data) {
      $('#status').removeAttr('disabled')
      let notShownStatus = ['ready']
      let status = data.filter((s) => !notShownStatus.includes(s.status))
      $.each(status, function (index, currentStatus) {
        $('#status').append($('<option>', {
          value: currentStatus.status,
          text: `${currentStatus.status} (${currentStatus.count} items)`
        }));
      })
    }
  });

  newStatus = null

  // Other status table
  $('#status').on('change', (event) => {
    newStatus = event.target.value
    $(".mactionsStorage").attr("status", newStatus)
    let tableId = '#storagesOtherTable'
    if ($.fn.dataTable.isDataTable(tableId)) {
      $(tableId).DataTable().destroy();
      $(tableId).empty()
    }

    storagesOtherTable = createDatatable(tableId, newStatus)

    $(tableId + " tbody").off('click').on('click', 'button', function () {
      let tr = $(this).closest("tr")
      let row = storagesOtherTable.row(tr)
      switch ($(this).attr('id')) {
        case 'btn-details':
          showRowDetails(storagesOtherTable, tr, row);
          break;
      }
    })
  })

  $('.mactionsStorage').on('change', function () {
    let action = $(this).val();
    let actionText = $(this).find('option:selected').text();
    let status = $(this).attr('status')
    let tableId = '#' + $(this).attr('selectedTableId')
    let appliedFilter = $(tableId).DataTable().search();

    if (appliedFilter) {
      let ids = []
      $(tableId).DataTable().rows({ filter: 'applied' }).every(function () {
        ids.push(this.data().id);
      })
      new PNotify({
        title: "Confirmation Needed",
        text: "The action '" + actionText + "' will be performed in " + ids.length + " storages. Are you sure?",
        hide: false,
        opacity: 0.9,
        type: "error",
        confirm: {
          confirm: true
        },
        buttons: {
          closer: false,
          sticker: false
        },
        history: {
          history: false
        },
        addclass: 'pnotify-center-large',
        width: '550'
      }).get().on('pnotify.confirm', function () {
        document.body.classList.add('loading-cursor')
        $.ajax({
          type: "PUT",
          url: '/api/v3/storages/status',
          data: JSON.stringify({
            ids: ids
          }),
          contentType: "application/json",
          success: function (data) {
            document.body.classList.remove('loading-cursor')
            $('.mactionsStorage option[value="none"]').prop("selected", true);
            $('thead #select-all').prop("checked", false);
            new PNotify({
              title: 'Success',
              text: ' Storages ' + action + ' performed successfully',
              hide: true,
              delay: 2000,
              icon: 'fa fa-' + data.icon,
              opacity: 1,
              type: 'success'
            });
          },
          error: function (xhr) {
            document.body.classList.remove('loading-cursor')
            $('.mactionsStorage option[value="none"]').prop("selected", true);
            new PNotify({
              title: 'Error',
              text: 'Couldn\'t perform the action \'' + actionText + '\' correctly',
              type: 'error',
              hide: true,
              icon: 'fa fa-warning',
              delay: 5000,
              opacity: 1
            })
          }
        })
      }).on('pnotify.cancel', function () {
        $('.mactionsStorage option[value="none"]').prop("selected", true);
      })
      // No rows selected will perform the action over all table data
    } else {
      new PNotify({
        title: 'Warning!',
        text: "You are about to perform the action '" + actionText + "' in all the storages in the table!\nPlease write <b>\"I'm aware\"</b> in order to confirm the action",
        hide: false,
        opacity: 0.9,
        type: 'error',
        confirm: {
          confirm: true,
          prompt: true,
          prompt_multi_line: false,
          buttons: [
            {
              text: "Ok",
              addClass: "",
              promptTrigger: true,
              click: function (notice, value) {
                if (value == "I'm aware") {
                  notice.remove();
                  document.body.classList.add('loading-cursor')
                  $.ajax({
                    type: "PUT",
                    url: '/api/v3/storages/status/' + status,
                    contentType: "application/json",
                    success: function (data) {
                      document.body.classList.remove('loading-cursor')
                      $('.mactionsStorage option[value="none"]').prop("selected", true);
                      $('thead #select-all').prop("checked", false);
                      new PNotify({
                        title: 'Success',
                        text: ' Storages ' + action + ' performed successfully',
                        hide: true,
                        delay: 2000,
                        icon: 'fa fa-' + data.icon,
                        opacity: 1,
                        type: 'success'
                      });
                    },
                    error: function (xhr) {
                      document.body.classList.remove('loading-cursor')
                      $('.mactionsStorage option[value="none"]').prop("selected", true);
                      new PNotify({
                        title: 'Error',
                        text: 'Couldn\'t perform the action \'' + actionText + '\' correctly',
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 5000,
                        opacity: 1
                      })
                    }
                  })
                }
              }
            },
            {
              text: "Cancel",
              addClass: "",
              click: function (notice) {
                notice.remove();
                $('.mactionsStorage option[value="none"]').prop("selected", true);
              }
            }]
        },
        buttons: {
          closer: false,
          sticker: false
        },
        history: {
          history: false
        },
        addclass: 'pnotify-center-large',
        width: '550'
      })
    }
  });

  // WS
  $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on)
})

// FUNCTIONS

//// TABLE BUTTON EVENTS
$(document).on('click', '.btn-task-info', function () {
  var element = $(this);
  var task = element.data("task");
  element.html('<i class="fa fa-spinner fa-pulse"></i>')
  $.ajax({
    type: 'GET',
    url: '/api/v3/task/' + task,
    contentType: 'application/json',
    success: function (result) {
      element.html('<i class="fa fa-tasks"></i>')
      new PNotify({
        title: 'Last task info',
        text: '<pre><li><b>TASK ID</b>: ' + result.id + '</li><li><b>TASK</b>: ' + result.task + '</li><li><b>USER ID</b>: ' + result.user_id + '</li><li><b>TASK STATUS</b>: ' + result.status + '</li><li><b>RESULT</b>: ' + JSON.stringify(result.result, undefined, 2) + '</li></pre>',
        hide: false,
        icon: '',
        opacity: 1,
        type: 'info',
        addclass: 'pnotify-center-large',
      })
    },
    error: function (xhr, ajaxOptions, thrownError) {
      element.html('<i class="fa fa-tasks" style="color:red" title="Task not found!"></i>')
      new PNotify({
        title: 'Error',
        text: xhr.responseJSON.description,
        hide: true,
        delay: 3000,
        icon: 'fa fa-warning',
        opacity: 1,
        type: 'error'
      });
    }
  });
})

$(document).on('click', '.btn-check-qemu-img-info', function () {
  element = $(this);
  var id = element.data("id");
  element.html('<i class="fa fa-spinner fa-pulse"></i>')
  $.ajax({
    type: 'PUT',
    url: '/api/v3/storage/' + id + '/check_backing_chain',
    contentType: 'application/json',
    success: function (result) {
      element.html('<i class="fa fa-refresh"></i>')
      new PNotify({
        title: 'Updated',
        text: 'Storage backing chain succesfully',
        hide: true,
        delay: 2000,
        icon: '',
        opacity: 1,
        type: 'success'
      })
    },
    error: function (xhr, ajaxOptions, thrownError) {
      element.html('<i class="fa fa-refresh" style="color:red" title="Error checking backing chain!"></i>')
      new PNotify({
        title: 'Error',
        text: xhr.responseJSON.description,
        hide: true,
        delay: 3000,
        icon: 'fa fa-warning',
        opacity: 1,
        type: 'error'
      });
    }
  });
})

$(document).on('click', '.btn-convert', function () {
  element = $(this);
  var storageId = element.data("id");
  modal = "#modalConvertStorage";
  $(modal + " select").empty();
  $(modal + " #id").val(storageId);
  populateDiskFormatSelects(element.data("current_type"));
  $(modal).modal({ backdrop: 'static', keyboard: false }).modal('show');
});


$("#modalConvertStorage #send").on("click", function () {
  var form = $('#modalConvertStorageForm');
  form.parsley().validate();
  if (form.parsley().isValid()) {
    data = form.serializeObject();
    var new_storage_status = data["change_status-cb"] ? "/" + data["new_status"] : "";
    var compress = data["compress-cb"] ? "/compress" : "";
    url = `/api/v3/storage/${data.storage_id}/convert/${data.disk_format}${new_storage_status}${compress}`
    $.ajax({
      url: url,
      type: 'POST',
    }).done(function () {
      new PNotify({
        title: 'Task created successfully',
        text: `Converting storage...`,
        hide: true,
        delay: 2000,
        opacity: 1,
        type: 'success'
      });
      $('.modal').modal('hide');
    }).fail(function (data) {
      new PNotify({
        title: `ERROR trying to convert storage`,
        text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
        type: 'error',
        hide: true,
        icon: 'fa fa-warning',
        delay: 5000,
        opacity: 1
      });
    });
  }
});

$(document).on('click', '.btn-increase', function () {
  element = $(this);
  var storageId = element.data("id");
  modal = "#modalIncreaseStorage";
  $(modal + " input").empty();
  $(modal + " #id").val(storageId);

  if ($("#user_data").data("role") == "admin") {
    $(modal + " select#priority").append(`
      <option selected value="low">Low</option>
      <option value="default">Default</option>
      <option value="high">High</option>
    `);
  } else {
    $(modal + " select#priority").append(`
    <option selected disabled value="low">Low</option>
    `);
    $(modal + " .different_pool").hide();
  }

  $.ajax({
    url: `/api/v3/admin/storage/info/${storageId}`,
    type: 'GET',
    contentType: "application/json",
  }).done(function (storage) {
    var virtual_size = storage.virtual_size / 1024 / 1024 / 1024
    $(modal + " #current-size").text(virtual_size.toFixed(0) + " GB");
    $(modal + " #current_size").val(virtual_size);
    $(modal + " #new-size").val(virtual_size.toFixed(0)).prop("min", virtual_size.toFixed(0));

    $.ajax({
      url: "/api/v3/admin/user/appliedquota/" + storage["user_id"],
      type: 'GET',
    }).done(function (quota) {
      if (quota.quota) {
        $(modal + " #max-quota-div").show();
        $(modal + " #max-quota").text(quota.quota.desktops_disk_size);
        $(modal + " #new-size").prop("max", quota.quota.desktops_disk_size);
      } else {
        $(modal + " #max-quota-div").hide();
        $(modal + " #new-size").removeAttr("max");
      }
    });

    $(modal).modal({ backdrop: 'static', keyboard: false }).modal('show');
  }).fail(function (data) {
    new PNotify({
      title: `ERROR trying to fetch storage size`,
      text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
      type: 'error',
      hide: true,
      icon: 'fa fa-warning',
      delay: 5000,
      opacity: 1
    });
  });

});


$("#modalIncreaseStorage #send").on("click", function () {
  var form = $('#modalIncreaseStorageForm');
  form.parsley().validate();
  if (form.parsley().isValid()) {
    data = form.serializeObject();
    var priority = data.priority ? data.priority : "low";
    var increment = data.new_size - data.current_size;
    $.ajax({
      url: `/api/v3/storage/${data.storage_id}/priority/${priority}/increase/${increment.toFixed(0)}`,
      type: 'PUT',
    }).done(function () {
      new PNotify({
        title: 'Task created successfully',
        text: `Increasing storage size...`,
        hide: true,
        delay: 2000,
        opacity: 1,
        type: 'success'
      });
      $('.modal').modal('hide');
    }).fail(function (data) {
      new PNotify({
        title: `ERROR trying to increase storage size`,
        text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
        type: 'error',
        hide: true,
        icon: 'fa fa-warning',
        delay: 5000,
        opacity: 1
      });
    });
  }
});

function socketio_on() {
  socket.on('storage', function (data) {
    var data = JSON.parse(data);
    if (data) {
      if (typeof (storage_ready.row('#' + data.id.replaceAll("/", "_")).id()) != 'undefined') {
        actual_data = storage_ready.row("#" + data.id.replaceAll("/", "_")).data()
        if ("status" in data && data.status != 'ready') {
          storage_ready.row('#' + data.id.replaceAll("/", "_")).remove().draw();
          showNotification(data.status)
          if (newStatus && newStatus == data.status) {
            if (typeof (storagesOtherTable.row('#' + data.id.replaceAll("/", "_")).id()) != 'undefined') {
              actual_data = storagesOtherTable.row("#" + data.id.replaceAll("/", "_")).data()
              storagesOtherTable.row('#' + data.id.replaceAll("/", "_")).remove().draw();
              storagesOtherTable.row.add({ ...actual_data, ...data }).draw()
            } else {
              storagesOtherTable.row.add({ ...actual_data, ...data }).draw()
            }
          }
        } else {
          storage_ready.row('#' + data.id.replaceAll("/", "_")).data({ ...actual_data, ...data }).invalidate();
        }
      } else if (newStatus) {
        if (typeof (storagesOtherTable.row('#' + data.id.replaceAll("/", "_")).id()) != 'undefined') {
          actual_data = storagesOtherTable.row("#" + data.id.replaceAll("/", "_")).data()
          if ("status" in data && data.status != newStatus) {
            storagesOtherTable.row('#' + data.id.replaceAll("/", "_")).remove().draw();
            storagesOtherTable.row.add({ ...actual_data, ...data }).draw()
            showNotification(data.status)
          } else {
            storagesOtherTable.row('#' + data.id.replaceAll("/", "_")).data({ ...actual_data, ...data }).invalidate();
          }
        } else if (newStatus == data.status) {
          storagesOtherTable.row.add(data).draw()
        }
      }
    }
  });
  socket.on('task', function (data) {
    if (storagesOtherTable.selector) {
      var data = JSON.parse(data);
      var taskRow = $(`tr[data-task="${data.id}"]`);
      if (taskRow.length > 0) {
        var rowData = storagesOtherTable.row(taskRow).data();
        rowData.progress = data.progress;
        storagesOtherTable.row(taskRow).data(rowData).draw();
      }
    }
  });
}

function showNotification(status) {
  switch (status) {
    default:
      new PNotify({
        title: 'Disk status changed to ' + status,
        text: 'Disk is now ' + status + ' and moved to the other status disks table',
        hide: true,
        delay: 5000,
        icon: '',
        opacity: 1,
        type: 'warning'
      })
  }
}

function format(rowData) {
  var childTable =
    '<table id="cl' +
    rowData.id.replaceAll("/", "_") +
    '" class="display compact nowrap w-100" width="100%">' +
    "</table>";
  return $(childTable).toArray();
}

function loadTableFilters(table) {
  // Create the table footer
  var tfoot = $('<tfoot><tr></tr><tr><th colspan="13" style="text-align:right" class="storagesOtherTableTotalSize"></th></tr></tfoot>').appendTo($(table.api().table().node()));

  // Add footer filters
  $(table.api().table().header()).find('th').each(function (index) {
    if (![0, 12, 13].includes(index)) { // Exclude specific columns like the checkbox, actions and task columns
      $('<th></th>')
        .appendTo(tfoot.find('tr:first'))
        .append($(`<input type="text" placeholder="Filter"/>`)
          .on('keyup change', function () {
            table.api().column(index).search($(this).val()).draw();
          })
        );
    } else {
      $('<th></th>').appendTo(tfoot.find('tr'));
    }
  });
}

function createDatatable(tableId, status, initCompleteFn = null) {
  return $(tableId).DataTable({
    ajax: {
      url: `/api/v3/admin/storage/${status}`,
      contentType: 'application/json',
      type: 'GET',
    },
    sAjaxDataProp: '',
    language: {
      loadingRecords: '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
    },
    rowId: 'id',
    deferRender: true,
    createdRow: function (row, data, dataIndex) {
      if (status = "maintenance") {
        $(row).attr('data-task', data.task);
      }
    },
    columns: [
      {
        className: "details-control",
        orderable: false,
        data: null,
        defaultContent: '<button id="btn-details" class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>',
      },
      {
        title: 'Status',
        data: 'status',
        filter: true
      },
      {
        title: 'Path',
        data: 'directory_path'
      },
      {
        title: 'Id',
        data: 'id'
      },
      {
        title: 'Format',
        data: 'type',
      },
      {
        title: 'Size',
        data: 'qemu-img-info.virtual-size',
        defaultContent: '-',
        render: function (data, type, row, meta) {
          if (data) {
            return Math.round(data / 1024 / 1024 / 1024) + " GB";
          } else {
            '-';
          }
        }
      },
      {
        title: 'Used',
        data: 'qemu-img-info.actual-size',
        defaultContent: '-',
        render: function (data, type, row, meta) {
          if (data) {
            return Math.round(data / 1024 / 1024 / 1024) + ' GB';
          } else {
            '-';
          }
        }
      },
      {
        title: 'Parent',
        data: 'parent',
        defaultContent: '-'
      },
      {
        title: 'User',
        data: 'user_name'
      },
      {
        title: 'Category',
        data: 'category'
      },
      {
        title: 'Progress',
        data: 'progress',
        visible: status == "maintenance",
        render: function (data) {
          if (data != undefined || status != "maintenance") {
            return renderProgress(data);
          } else { return '-' }
        }
      },
      {
        title: 'Domains',
        data: 'domains'
      },
      { data: "perms", title: "Perms" },
      {
        title: 'Last',
        data: 'last',
        render: function (last) {
          try {
            return moment.unix(last.time).fromNow();
          } catch {
            return "N/A";
          }
        }
      },
      {
        title: 'Task',
        data: 'task',
        defaultContent: '-',
        visible: $('meta[id=user_data]').attr('data-role') === 'admin',
        render: function (data, type, row, meta) {
          if (data) {
            return '<button type="button" data-task="' + data + '" class="btn btn-pill-right btn-info btn-xs btn-task-info" title="Show last task info"><i class="fa fa-tasks"></i></button>'
          } else {
            '-'
          }
        }
      },
      {
        className: 'actions-control',
        orderable: false,
        data: null,
        width: '60px',
        visible: $('meta[id=user_data]').attr('data-role') === 'admin',
        render: function (data, type, row, meta) {
          return '<button type="button" data-id="' + row.id + '" class="btn btn-pill-right btn-success btn-xs btn-check-qemu-img-info" title="Check disk info"><i class="fa fa-refresh"></i></button>';
        }
      }
    ],
    initComplete: function () {
      loadTableFilters(this);
      if (initCompleteFn) {
        initCompleteFn()
      }
    },
  });
}

function showRowDetails(table, tr, row) {
  if (row.child.isShown()) {
    row.child.hide();
    tr.removeClass('shown');
  } else {
    table.rows('.shown').every(function () {
      this.child.hide();
      $(this.node()).removeClass('shown');
    });

    row.child(format(row.data())).show();
    if ($("#user_data").data("role") == "admin") {
      $('#cl' + row.data().id).parent().prepend(detailButtons(row.data()));
    }

    childTable = $('#cl' + row.data().id).DataTable({
      dom: "t",
      ajax: {
        url: "/api/v3/storage/" + row.data().id + "/parents",
        contentType: "application/json",
        type: "GET",
      },
      sAjaxDataProp: "",
      language: {
        loadingRecords:
          '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
      },
      columns: [
        { data: null, title: "#", render: function (data, type, full, meta) { return meta.row + 1; } },
        { data: "id", title: "storage id", render: function (data, type, full, meta) { if (meta.row == 0) { return '<b>' + data + '</b>' } else { return data } } },
        { data: "status", title: "storage status" },
        { data: "parent_id", title: "parent storage id" },
        {
          data: "domains", title: "domains",
          render: function (data, type, full, meta) {
            links = []
            $(data).each(function (index, value) {
              let kind = value.kind.charAt(0).toUpperCase() + value.kind.slice(1).replace(/_/g, ' ')
              links[index] = '<a href="/isard-admin/admin/domains/render/' + kind + 's?searchDomainId=' + value.id + '"><b>' + kind[0] + ': </b>' + value.name + '</a>'
            });
            return links.join(', ')
          }
        },
      ],
      columnDefs: [
      ],
      order: [],
      select: false,
    });
    tr.addClass('shown')
  }
}


function detailButtons(storage) {
  return storage.status == "ready" ?
    `<div class="col-md-12 col-sm-12 col-xs-12">
      <div class="x_panel" style="background-color: #F7F7F7;">
        <div class="row">
          <div class="col-md-12 col-sm-12 col-xs-12">
            <div class="x_content">
              <div class="row">
                <div class="col-md-12 col-sm-12 col-xs-12">
                  <div class="x_panel" style="margin:3px;">
                  
                    <!--<button class="btn btn-success btn-xs btn-move" data-id="${storage.id}" type="button"
                      data-placement="top" title="Move to another path"><i class="fa fa-truck m-right-xs"></i>
                      Move
                    </button>-->
                    <button class="btn btn-success btn-xs btn-convert" data-id="${storage.id}" data-current_type=${storage.type} type="button"
                      data-placement="top" title="Convert to another disk format"><i class="fa fa-exchange m-right-xs"></i>
                      Convert
                    </button>
                    <!--<button class="btn btn-primary btn-xs btn-virt_win_reg" data-id="${storage.id}" type="button"
                      data-placement="top" title="Add windows registry"><i class="fa fa-edit m-right-xs"></i>
                      Windows registry
                    </button>-->
                    <button class="btn btn-info btn-xs btn-increase" data-id="${storage.id}" type="button"
                      data-placement="top" title="Increase disk size"><i class="fa fa-external-link-square m-right-xs"></i>
                      Increase
                    </button>

                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>` : "";
}

function populateDiskFormatSelects(currentType) {
  $("#current-disk_format").append(`<option selected disabled value="${currentType}">.${currentType}</option>`);

  $("#modalConvertStorageForm #new-disk_format").append(`
    <option value="qcow2">.qcow2</option>
    <option value="vmdk">.vmdk</option>
  `);
  $(`#modalConvertStorageForm #new-disk_format option[value="${currentType}"]`).remove();

  $("#modalConvertStorageForm #new-status").append(`
    <option value="ready">Ready</option>
    <option value="downloadable">Downloadable</option>
  `);

}

function addCheckboxListeners() {
  $("#modalConvertStorageForm #change_status-cb").on('ifChecked', function (event) {
    $("#modalConvertStorageForm #new_status-content").show();
  });
  $("#modalConvertStorageForm #change_status-cb").on('ifUnchecked', function (event) {
    $("#modalConvertStorageForm #new_status-content").hide();
  });
}

function renderProgress(perc) {
  perc = (perc * 100).toFixed(1);
  return '<div class="progress"> \
            <div class="progress-bar" role="progressbar" aria-valuenow="' + perc + '" \
              aria-valuemin="0" aria-valuemax="100" style="width:'+ perc + '%"> \
              '+ perc + '%  \
            </div> \
          </<div>';
}