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
  storagesOtherTable = null;
  $('#status').attr('disabled', 'disabled')
  addCheckboxListeners();
  addRadioButtonsListeners();
  addSelectMethodListeners();

  // Storage ready table
  let tableId = '#storage'
  storage_ready = createDatatable(tableId, 'ready', function () {
    let searchStorageId = getGroupParam()
    if (searchStorageId) {
      storage_ready.column(3).search(searchStorageId).draw();
      $(tableId + ' tfoot input').eq(2).val(searchStorageId);
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
        if (currentStatus.status) {
          $('#status').append($('<option>', {
            value: currentStatus.status,
            id: currentStatus.status,
            text: `${currentStatus.status} (${currentStatus.count} items)`
          }));
        }
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

    storagesOtherTable = createDatatable(tableId, newStatus, function () {
      let searchStorageId = getGroupParam()
      if (searchStorageId) {
        storagesOtherTable.column(3).search(searchStorageId).draw();
        $(tableId + ' tfoot input').eq(2).val(searchStorageId);
      }
    })

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
        var notify = new PNotify();
        $.ajax({
          type: "PUT",
          url: '/api/v3/storages/status',
          data: JSON.stringify({
            ids: ids
          }),
          contentType: "application/json",
          success: function (data) {
            $('.mactionsStorage option[value="none"]').prop("selected", true);
            $('thead #select-all').prop("checked", false);
            notify.update({
              title: 'Processing',
              text: `Processing action: ${action} on ${ids.length} storage(s)`,
              type: 'info',
              hide: false,
              icon: 'fa fa-spinner fa-pulse',
              opacity: 1
            });
          },
          error: function (xhr) {
            document.body.classList.remove('loading-cursor')
            $('.mactionsStorage option[value="none"]').prop("selected", true);
            notify.update({
              title: "ERROR " + action + " storage(s)",
              text: data.responseJSON ? data.responseJSON.description : "Something went wrong",
              hide: true,
              delay: 3000,
              icon: 'fa fa-alert-sign',
              opacity: 1,
              type: 'error'
            });
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
                  var notify = new PNotify();
                  $.ajax({
                    type: "PUT",
                    url: '/api/v3/storages/find/' + status,
                    contentType: "application/json",
                    success: function (data) {
                      $('.mactionsStorage option[value="none"]').prop("selected", true);
                      $('thead #select-all').prop("checked", false);
                      notify.update({
                        title: 'Processing',
                        text: `Processing action: ${action} to ALL storage(s)`,
                        type: 'info',
                        hide: false,
                        icon: 'fa fa-spinner fa-pulse',
                        opacity: 1
                      });
                    },
                    error: function (xhr) {
                      document.body.classList.remove('loading-cursor')
                      $('.mactionsStorage option[value="none"]').prop("selected", true);
                      notify.update({
                        title: "ERROR " + action + " storage(s)",
                        text: data.responseJSON ? data.responseJSON.description : "Something went wrong",
                        hide: true,
                        delay: 3000,
                        icon: 'fa fa-alert-sign',
                        opacity: 1,
                        type: 'error'
                      });
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

// $(document).on('click', '.btn-check-qemu-img-info', function () {
//   element = $(this);
//   var id = element.data("id");
//   element.html('<i class="fa fa-spinner fa-pulse"></i>')
//   $.ajax({
//     type: 'PUT',
//     url: '/api/v3/storage/' + id + '/check_backing_chain',
//     contentType: 'application/json',
//     success: function (result) {
//       element.html('<i class="fa fa-refresh"></i>')
//       new PNotify({
//         title: 'Updated',
//         text: 'Storage backing chain succesfully',
//         hide: true,
//         delay: 2000,
//         icon: '',
//         opacity: 1,
//         type: 'success'
//       })
//     },
//     error: function (xhr, ajaxOptions, thrownError) {
//       element.html('<i class="fa fa-refresh" style="color:red" title="Error checking backing chain!"></i>')
//       new PNotify({
//         title: 'Error',
//         text: xhr.responseJSON.description,
//         hide: true,
//         delay: 3000,
//         icon: 'fa fa-warning',
//         opacity: 1,
//         type: 'error'
//       });
//     }
//   });
// });

$(document).on('click', '.btn-delete-scheduler', function () {
  element = $(this);
  var id = element.data("id");
  new PNotify({
    title: 'Confirmation Needed',
    text: "Are you sure you want to delete the scheduler associated with this storage, if any?",
    hide: false,
    opacity: 0.9,
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
    addclass: 'pnotify-center'
  }).get().on('pnotify.confirm', function () {
    $.ajax({
      type: 'DELETE',
      url: `/scheduler/${id}.stg_action`,
      contentType: 'application/json',
      success: function (result) {
        new PNotify({
          title: 'Deleted',
          text: 'Job deleted',
          hide: true,
          delay: 2000,
          icon: '',
          opacity: 1,
          type: 'success'
        })
      },
      error: function (data) {
        new PNotify({
          title: 'ERROR deleting scheduler',
          text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
          hide: true,
          delay: 3000,
          icon: 'fa fa-warning',
          opacity: 1,
          type: 'error'
        });
      }
    });
  });
});

$(document).on('click', '.btn-find', function () {
  element = $(this);
  var id = element.data("id");
  $.ajax({
    type: 'GET',
    url: '/api/v3/storage/' + id + '/find',
    contentType: 'application/json',
    success: function (result) {
      new PNotify({
        title: 'Find',
        text: 'Storage found',
        hide: true,
        delay: 2000,
        icon: '',
        opacity: 1,
        type: 'success'
      })
    },
    error: function (xhr, ajaxOptions, thrownError) {
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
});


$(document).on('click', '.btn-convert', function () {
  element = $(this);
  var storageId = element.data("id");
  $.ajax({
    url: `/api/v3/storage/${storageId}/has_derivatives`,
    type: 'GET',
    contentType: "application/json",
  }).done(function (data) {
    if (data.derivatives > 1) {
      new PNotify({
        title: `ERROR`,
        text: "This storage has derivatives",
        type: 'error',
        hide: true,
        icon: 'fa fa-warning',
        delay: 5000,
        opacity: 1
      });
    } else {
      populateDiskFormatSelects(element.data("current_type"));
      modal = "#modalConvertStorage";
      $(modal + " select").empty();
      $(modal + " #id").val(storageId);
      populatePrioritySelect(modal);
      $(modal).modal({ backdrop: 'static', keyboard: false }).modal('show');
    }
  });
});


$("#modalConvertStorage #send").on("click", function () {
  var form = $('#modalConvertStorageForm');
  form.parsley().validate();
  if (form.parsley().isValid()) {
    formData = form.serializeObject();
    var priority = formData.priority ? formData.priority : "low";
    var new_storage_status = formData["change_status-cb"] ? "/" + formData["new_status"] : "";
    var compress = formData["compress-cb"] ? "/compress" : "";

    $.ajax({
      url: `/api/v3/storage/${formData.storage_id}/convert/${formData.new_storage_type}${new_storage_status}${compress}/priority/${priority}`,
      type: 'POST',
      data: JSON.stringify(formData),
      contentType: 'application/json'
    }).done(function () {
      new PNotify({
        title: 'Task created successfully',
        text: `Performing convert on storage...`,
        hide: true,
        delay: 2000,
        opacity: 1,
        type: 'success'
      });
      $('.modal').modal('hide')
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
  $(modal + " select#priority").empty();

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
    $.ajax({
      url: `/api/v3/storage/${storageId}/has_derivatives`,
    }).done(function (data) {
      if (data.derivatives <= 1) {
        var virtual_size = storage.virtual_size / 1024 / 1024 / 1024
        $(modal + " #current-size").text(virtual_size.toFixed(0) + " GB");
        $(modal + " #current_size").val(virtual_size);
        $(modal + " #new-size").val(virtual_size.toFixed(0)).prop("min", (virtual_size + 1).toFixed(0));

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
      } else {
        new PNotify({
          title: `ERROR`,
          text: 'Size of disks with derivatives cannot be modified',
          type: 'error',
          hide: true,
          icon: 'fa fa-warning',
          delay: 5000,
          opacity: 1
        });
      }
    }).fail(function (data) {
      new PNotify({
        title: `ERROR`,
        text: 'Something went wrong',
        type: 'error',
        hide: true,
        icon: 'fa fa-warning',
        delay: 5000,
        opacity: 1
      });
    });

  }).fail(function (data) {
    new PNotify({
      title: `ERROR`,
      text: 'Something went wrong',
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
    formData = form.serializeObject();
    var priority = formData.priority ? formData.priority : "low";
    formData.increment = (formData.new_size - formData.current_size).toFixed(0);
    delete formData.new_size;
    var url = `/api/v3/storage/${formData.storage_id}/priority/${priority}/increase/${formData.increment}`;
    performStorageOperation(formData, formData.storage_id, "increase", url);
  }
});

$(document).on('click', '.btn-add-storage', function () {
  var modal = "#modalCreateStorage";
  $(modal + " #storage_id").val(null);
  $(modal + " #id").attr("disabled", true);
  $(modal + " #storage_id-wrapper").hide();
  $(modal + " #storage_pool").attr("disabled", false).empty();
  $(modal + " #owner-wrapper").show();
  $(modal + " .modal-body h4").text("Add new unattached storage disk");
  resetCreateDiskForm();

  $(modal + " #user").select2({
    placeholder: "Type at least 2 letters to search.",
    minimumInputLength: 2,
    dropdownParent: $(modal),
    ajax: {
      type: "POST",
      url: '/admin/allowed/term/users',
      dataType: 'json',
      contentType: "application/json",
      delay: 250,
      data: function (params) {
        return JSON.stringify({
          term: params.term,
          pluck: ['id', 'name']
        });
      },
      processResults: function (data) {
        return {
          results: $.map(data, function (item, i) {
            return {
              text: item.name + '[' + item['uid'] + '] ',
              id: item.id
            }
          })
        };
      }
    },
  });

  $(modal).modal({ backdrop: 'static', keyboard: false }).modal('show');
});


$(document).on('click', '.btn-create', function () {
  element = $(this);
  var id = element.data("id");
  var modal = "#modalCreateStorage";
  resetCreateDiskForm();

  $.ajax({
    url: `/api/v3/admin/storage/info/${id}`,
    type: 'GET',
    contentType: "application/json",
  }).done(function (data) {
    $.ajax({
      url: `/api/v3/admin/storage_pool/path`,
      type: 'PUT',
      data: JSON.stringify({ "path": data["directory_path"] }),
      contentType: "application/json",
    }).done(function (pool) {
      var subpath = data["directory_path"].split(pool.mountpoint + "/")[1];
      $.each(pool.paths, function (key, value) {
        $.each(value, function (_, value) {
          if (subpath.endsWith(value.path)) {
            $(modal + " #kind").val(key);
          }
        });
      });
      if ($(modal + " #kind").val() != "template") {
        new PNotify({
          title: `ERROR`,
          text: 'Disks can only be derived from template disks',
          type: 'error',
          hide: true,
          icon: 'fa fa-warning',
          delay: 5000,
          opacity: 1
        });
      } else {
        $(modal + " #id").attr("disabled", false).val(id);
        $(modal + " .modal-body h4").text("Create derived storage disk");
        $(modal + " #storage_id-wrapper").show();
        $(modal + " #owner-wrapper").hide();
        $(modal + " #storage_pool").attr("disabled", true);
        $(modal + " #storage_id").text(id);
        $(modal).modal({ backdrop: 'static', keyboard: false }).modal('show');
      }
    });
  });

});


$("#modalCreateStorage #send").on("click", function () {
  var form = $('#modalCreateStorageForm');
  form.parsley().validate();
  if (form.parsley().isValid()) {
    formData = form.serializeObject();
    unit = formData.size_unit != undefined ? formData.size_unit : "G";
    formData.size = formData.size + unit;
    var priority = $("#user_data").data("role") == "admin" ? formData.priority : "low";
    formData.storage_type = "qcow2";
    delete formData.size_unit;
    if (formData.parent) {
      performStorageOperation(formData, formData.parent, "create", "/api/v3/storage/priority/" + priority);
    } else {
      $.ajax({
        url: "/api/v3/storage/priority/" + priority,
        type: 'POST',
        data: JSON.stringify(formData),
        contentType: 'application/json',
      }).done(function () {
        new PNotify({
          title: 'Task created successfully',
          text: `Creating storage...`,
          hide: true,
          delay: 2000,
          opacity: 1,
          type: 'success'
        });
        $('.modal').modal('hide');
      }).fail(function (data) {
        new PNotify({
          title: "ERROR trying to create new storage",
          text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
          type: 'error',
          hide: true,
          icon: 'fa fa-warning',
          delay: 5000,
          opacity: 1
        });
      });
    }
  }
});


$(document).on('click', '.btn-virt_win_reg', function () {
  element = $(this);
  var storageId = element.data("id");
  modal = "#modalVirtWinReg";
  $.ajax({
    url: `/api/v3/storage/${storageId}/has_derivatives`,
    type: 'GET',
    contentType: "application/json",
  }).done(function (data) {
    if (data.derivatives > 1) {
      new PNotify({
        title: `ERROR`,
        text: "This storage has derivatives",
        type: 'error',
        hide: true,
        icon: 'fa fa-warning',
        delay: 5000,
        opacity: 1
      });
    } else {
      $(modal + " #registry_file").prop("value", "")
      $(modal + " #id").val(storageId);
      populatePrioritySelect(modal);
      $(modal).modal({ backdrop: 'static', keyboard: false }).modal('show');
    }
  }).fail(function (data) {
    new PNotify({
      title: `ERROR trying to edit Windows registry`,
      text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
      type: 'error',
      hide: true,
      icon: 'fa fa-warning',
      delay: 5000,
      opacity: 1
    });

  });
});


$("#modalVirtWinReg #send").on("click", function () {
  var form = $('#modalVirtWinRegForm');
  form.parsley().validate();
  if (form.parsley().isValid()) {
    data = form.serializeObject();
    var file = $('#registry_file')[0].files[0];
    if (file.type !== "text/x-ms-regedit") {
      new PNotify({
        title: `ERROR uploading file`,
        text: 'File must be a regedit file',
        type: 'error',
        hide: true,
        icon: 'fa fa-warning',
        delay: 5000,
        opacity: 1
      });
    } else if (file.size > 1 * 1024 * 1024) { //1MB
      new PNotify({
        title: `ERROR uploading file`,
        text: 'File size must be less than 1MB',
        type: 'error',
        hide: true,
        icon: 'fa fa-warning',
        delay: 5000,
        opacity: 1
      });
    } else {
      filecontents = "";
      var reader = new FileReader();
      reader.onload = function (event) {
        var fileContents = event.target.result;
        data["registry_patch"] = fileContents;
        var priority = $("#user_data").data("role") == "admin" ? data.priority : "low";
        var url = "/api/v3/storage/virt-win-reg/" + data["storage_id"] + "/priority/" + priority;
        performStorageOperation(data, data["storage_id"], "virt_win_reg", url);
      }
      reader.readAsText(file, 'UTF-8');
    }
  }
});


$(document).on('click', '.btn-move', function () {
  element = $(this);
  var storageId = element.data("id");
  modal = "#modalMoveStorage";
  $(modal + " #id").val(storageId);
  resetMoveForm();
  populateSelectMethod(modal);
  populateSelectAfterRSync(modal);
  $.ajax({
    url: `/api/v3/storage/${storageId}/has_derivatives`,
    type: 'GET',
    contentType: "application/json",
  }).done(function (data) {
    if (data.derivatives > 1) {
      new PNotify({
        title: `ERROR`,
        text: "This storage has derivatives",
        type: 'error',
        hide: true,
        icon: 'fa fa-warning',
        delay: 5000,
        opacity: 1
      });
    } else {
      $.ajax({
        url: `/api/v3/admin/storage/info/${storageId}`,
        type: 'GET',
        contentType: "application/json",
      }).done(function (data) {
        $.ajax({
          url: `/api/v3/admin/storage_pool/path`,
          type: 'PUT',
          data: JSON.stringify({ "path": data["directory_path"] }),
          contentType: "application/json",
        }).done(function (pool) {
          var subpath = data["directory_path"].split(pool.mountpoint + "/")[1];
          $.each(pool.paths, function (key, value) {
            $.each(value, function (_, value) {
              if (subpath.endsWith(value.path)) {
                $(modal + " #kind").val(key);
              }
            });
          });
          $(modal + " #storage_pool-name").empty().append(`<option selected value="${pool.id}">${pool.name}</option>`);
          populateSelectByPool(modal, pool, data, pool.is_default);
          // addSelectStoragePoolListeners(data);
          $.ajax({
            url: `/api/v3/admin/storage_pools`,
            type: 'GET',
          }).done(function (data) {
            $(modal + " #storage_pool").append(`<option disabled>-- Select a destination storage pool --</option>`)
            $.each(data, function (key, value) {
              if (value.id != pool.id) {
                $(modal + " #storage_pool").append(`<option value="${value.id}">${value.name}</option>`);
              }
            })
          });
          $(modal).modal({ backdrop: 'static', keyboard: false }).modal('show');
        });
      }).fail(function (data) {
        new PNotify({
          title: 'ERROR',
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
});


$("#modalMoveStorage #send").on("click", function () {
  var form = $("#modalMoveStorageForm");
  form.parsley().validate();
  if (form.parsley().isValid()) {
    data = form.serializeObject();
    const type = data["pool-radio"] == "same_pool" ? "byPath" : "byStoragePool";
    data["storage_pool"] = $("#modalMoveStorage #storage_pool").val();
    delete data["pool-radio"];
    delete data["moving-tool"];
    performMoveOperation(data, type);
  }
});


function socketio_on() {
  socket.on('storage', function (data) {
    var data = JSON.parse(data);
    if (data) {
      let id = '#' + data.id.replaceAll("/", "_");
      let actual_data;
      let table;

      if (typeof (storage_ready.row(id).id()) != 'undefined') {
        table = storage_ready;
      } else if (storagesOtherTable && (typeof (storagesOtherTable.row(id).id()) != 'undefined')) {
        table = storagesOtherTable;
      }

      if (table) {
        actual_data = table.row(id).data();
        if ("status" in data) {
          if (data.status != 'ready') {
            if (!$("#status #" + data.status).length) {
              $('#status').append($('<option>', {
                value: data.status,
                id: data.status,
                text: `${data.status} (1 item)`
              }));
            }
            table.row(id).remove().draw();
            if (newStatus && newStatus == data.status) {
              storagesOtherTable.row.add({ ...actual_data, ...data }).draw();
              showNotification(data.status);
            }
          } else {
            if (storagesOtherTable) {
              storagesOtherTable.row(id).remove().draw();
              if (typeof (storage_ready.row(id).id()) == 'undefined') {
                storage_ready.row.add({ ...actual_data, ...data }).draw();
                showNotification(data.status);
              }
            }
          }
        } else {
          table.row(id).data({ ...actual_data, ...data }).invalidate();
        }
      } else if (newStatus) {
        if (typeof (storagesOtherTable.row(id).id()) != 'undefined') {
          actual_data = storagesOtherTable.row(id).data();
          if ("status" in data && data.status != newStatus) {
            storagesOtherTable.row(id).remove().draw();
            storagesOtherTable.row.add({ ...actual_data, ...data }).draw();
            showNotification(data.status);
          } else {
            storagesOtherTable.row(id).data({ ...actual_data, ...data }).invalidate();
          }
        } else if (newStatus == data.status) {
          storagesOtherTable.row.add(data).draw();
        }
      }

    }
  });
  socket.on('task', function (data) {
    if (storagesOtherTable && storagesOtherTable.selector) {
      var data = JSON.parse(data);
      var taskRow = $(`tr[data-task="${data.id}"]`);
      if (taskRow.length > 0) {
        var rowData = storagesOtherTable.row(taskRow).data();
        if (rowData) {
          rowData.progress = data.progress;
          storagesOtherTable.row(taskRow).data(rowData).draw();
        }
      }
    }
  });
  socket.on('storage_action', function (data) {
    PNotify.removeAll();
    var data = JSON.parse(data);
    if (data.status === 'failed') {
      new PNotify({
        title: `ERROR: ${data.action} on ${data.count} storage(s)`,
        text: data.msg,
        hide: false,
        icon: 'fa fa-warning',
        opacity: 1,
        type: 'error'
      });
    } else if (data.status === 'completed') {
      storage_ready.ajax.reload();
      new PNotify({
        title: `Action Succeeded: ${data.action}`,
        text: `The action "${data.action}" completed on ${data.count} storage(s).`,
        hide: true,
        delay: 4000,
        icon: 'fa fa-success',
        opacity: 1,
        type: 'success'
      });
    }
  });
}

function showNotification(status) {
  let storageTable = status === "ready" ? "ready" : "other status";
  new PNotify({
    title: `Disk status changed to ${status}`,
    text: `Disk is now ${status} and moved to the ${storageTable} storage table`,
    hide: true,
    delay: 5000,
    icon: '',
    opacity: 1,
    type: 'warning'
  });
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
        render: function (last, type, full, meta) {
          if (type == "display" || type === 'filter') {
            try {
              return moment.unix(last.time).fromNow();
            } catch {
              return "N/A";
            }
          }
          return last.time
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
        width: '65px',
        visible: $('meta[id=user_data]').attr('data-role') === 'admin',
        render: function (data, type, row, meta) {
          return `<button type="button" data-id="${row.id}" class="btn btn-pill-right btn-info btn-xs btn-find" title="Find in storage"><i class="fa fa-search  "></i></button>\
                  ${data.status == "ready" ? `<button type="button" data-id="${row.id}" class="btn btn-pill-right btn-danger btn-xs btn-delete-scheduler" title="Delete scheduler"><i class="fa fa-calendar-times-o"></i></button>` : ""}`;
          // <button type="button" data-id="${row.id}" class="btn btn-pill-right btn-success btn-xs btn-check-qemu-img-info" title="Check disk info"><i class="fa fa-refresh"></i></button>\

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
                    <button class="btn btn-success btn-xs btn-move" data-id="${storage.id}" type="button"
                      data-placement="top" title="Move to another path"><i class="fa fa-truck m-right-xs"></i>
                      Move
                    </button>
                    <!--<button class="btn btn-success btn-xs btn-convert" data-id="${storage.id}" data-current_type=${storage.type} type="button"
                      data-placement="top" title="Convert to another disk format"><i class="fa fa-exchange m-right-xs"></i>
                      Convert
                    </button>-->
                    <button class="btn btn-primary btn-xs btn-virt_win_reg" data-id="${storage.id}" type="button"
                      data-placement="top" title="Add windows registry"><i class="fa fa-edit m-right-xs"></i>
                      Windows registry
                    </button>
                    <button class="btn btn-info btn-xs btn-increase" data-id="${storage.id}" type="button"
                      data-placement="top" title="Increase disk size"><i class="fa fa-external-link-square m-right-xs"></i>
                      Increase
                    </button>
		    ${(function () {
      return ($("#user_data").data("role") == "admin") ? `
	              <button class="btn btn-info btn-xs btn-create" data-id="${storage.id}" type="button"
			 data-placement="top" title="Create new disk derivated from this one"><i class="fa fa-plus m-right-xs"></i>
		       	 Add disk
		      </button>` : ""
    })()}
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

function populatePrioritySelect(modal) {
  $(modal + " select#priority").empty();
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
  }
}

function resetCreateDiskForm() {
  var modal = "#modalCreateStorageForm";
  $(modal + " #user").val("");
  $(modal + " #usage_type").val("desktop");
  $(modal + " #storage_type").val("qcow2");
  $(modal + " #size").val(10);
  $(modal + " #size_unit").val("G");
  populatePrioritySelect(modal);
}

function stopAllDesktops(storageId) {
  $.ajax({
    type: "PUT",
    url: `/api/v3/storage/${storageId}/stop`
  }).done(function (data) {
    new PNotify({
      title: 'Stopping desktops...',
      hide: true,
      delay: 2000,
      icon: 'fa fa-' + data.icon,
      opacity: 1,
      type: 'success'
    });
  }).fail(function (data) {
    new PNotify({
      title: 'ERROR stopping desktops',
      text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
      type: 'error',
      hide: true,
      icon: 'fa fa-warning',
      delay: 5000,
      opacity: 1
    });
  });
}

function scheduleUntilDesktopsAreStopped(storageId, action, kwargs) {
  data = {}
  data["kwargs"] = {
    storage_id: storageId,
    action: action,
    ...kwargs
  };
  $.ajax({
    url: "/scheduler/system/interval/wait_desktops_to_do_storage_action/00/05/" + storageId + ".stg_action",
    type: "POST",
    data: JSON.stringify(data),
    contentType: "application/json",
  }).done(function () {
    new PNotify({
      title: 'Success',
      text: ' Storages ' + action + ' scheduled successfully',
      hide: true,
      delay: 2000,
      icon: 'fa fa-' + data.icon,
      opacity: 1,
      type: 'success'
    });
    $('.modal').modal('hide');
  }).fail(function (data) {
    new PNotify({
      title: 'ERROR scheduling the action ' + action,
      text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
      type: 'error',
      hide: true,
      icon: 'fa fa-warning',
      delay: 5000,
      opacity: 1
    });
  });
}

function performStorageOperation(formData, storageId, action, url) {
  $.ajax({
    url: url,
    type: action === "create" ? 'POST' : 'PUT',
    data: JSON.stringify(formData),
    contentType: 'application/json'
  }).done(function () {
    new PNotify({
      title: 'Task created successfully',
      text: `Performing ${action} on storage...`,
      hide: true,
      delay: 2000,
      opacity: 1,
      type: 'success'
    });
    $('.modal').modal('hide');
  }).fail(function (data) {
    if (data.responseJSON && data.responseJSON.description_code === "desktops_not_stopped" && $("#user_data").data("role") == "admin") {
      new PNotify({
        title: "All desktops must be 'Stopped' for storage operations",
        text: "You can force stop now all desktops associated with the storage" + ($("#user_data").data("role") == "admin" ? " or schedule the action when desktops are stopped" : ""),
        hide: false,
        opacity: 0.9,
        type: "error",
        confirm: {
          confirm: true,
          buttons: [
            {
              text: "Force Stop desktops", click: function (notice) {
                stopAllDesktops(storageId);
                scheduleUntilDesktopsAreStopped(storageId, action, formData)
                notice.remove();
              }
            },
            {
              text: "Schedule", click: function (notice) {
                scheduleUntilDesktopsAreStopped(storageId, action, formData);
                notice.remove();
              }
            },
            { text: "Cancel", click: function (notice) { notice.remove(); } }
          ]
        },
        buttons: { closer: false, sticker: false },
        history: { history: false },
        addclass: 'pnotify-center-large',
        width: '550'
      });
    } else {
      new PNotify({
        title: `ERROR trying to ${action} storage`,
        text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
        type: 'error',
        hide: true,
        icon: 'fa fa-warning',
        delay: 5000,
        opacity: 1
      });
    }
  });
}

function performMoveOperation(formData, type) {
  var url = "";
  var data = {};
  switch (formData.method) {
    case "rsync":
      switch (type) {
        case "byStoragePool":
          url = `/api/v3/storage/${formData.storage_id}/rsync/to-storage-pool`;
          data = {
            storage_id: formData.storage_id,
            destination_storage_pool_id: formData.storage_pool,
            priority: formData.priority,
            bwlimit: parseInt(formData.bwlimit),
            remove_source_file: formData["remove_source_file"] === "true",
          };
          break;
        case "byPath":
          url = `/api/v3/storage/${formData.storage_id}/rsync/to-path`;
          data = {
            storage_id: formData.storage_id,
            destination_path: formData.destination_path,
            priority: formData.priority,
            bwlimit: parseInt(formData.bwlimit),
            remove_source_file: formData["remove_source_file"] === "true",
          };
          break;
      }
      break;
    case "move":
      switch (type) {
        case "byPath":
          url = `/api/v3/storage/${formData.storage_id}/move/by-path`;
          data = {
            storage_id: formData.storage_id,
            dest_path: formData.destination_path,
            priority: formData.priority,
          };
          break;
      }
      break;
  }
  $.ajax({
    url: url,
    type: "PUT",
    data: JSON.stringify(data),
    contentType: "application/json",
  })
    .done(function () {
      new PNotify({
        title: "Task created successfully",
        text: `Moving storage...`,
        hide: true,
        delay: 2000,
        opacity: 1,
        type: "success",
      });
      $(".modal").modal("hide");
    })
    .fail(function (data) {
      new PNotify({
        title: `ERROR trying to move storage`,
        text: data.responseJSON
          ? data.responseJSON.description
          : "Something went wrong",
        type: "error",
        hide: true,
        icon: "fa fa-warning",
        delay: 5000,
        opacity: 1,
      });
    });
}

function populateSelectByPool(modal, pool, data, isDefault) {
  var emptySelect = true;
  $(modal + " .new_path").empty();
  var kind = $(modal + " #kind").val();
  $.each(pool.paths[kind], function (key, kindPath) {
    var category = isDefault ? "" : data.category + "/";
    if ($("#user_data").data("role") == "admin" && category) {
      $.each(pool.categories, function (key, cat) {
        optionPath = pool.mountpoint + "/" + cat + "/" + kindPath.path;
        if (data.directory_path != optionPath) {
          $(modal + " .new_path").append(`<option ${optionPath == data["directory_path"] ? 'selected' : ''} value="${optionPath}">${optionPath}</option>`);
          emptySelect = false;
        }
      });
    } else {
      optionPath = pool.mountpoint + "/" + category + kindPath.path;
      if (data.directory_path != optionPath) {
        $(modal + " .new_path").append(`<option ${optionPath == data["directory_path"] ? 'selected' : ''} value="${optionPath}">${optionPath}</option>`);
        emptySelect = false;
      }
    }
    $(modal + " #origin_path").empty().text(data["directory_path"]);
  });
  if (emptySelect) {
    $(modal + " .new_path").append(`<option selected disabled>-- No ${kind} paths available for this pool and category --</option>`);
  }
}

function populateSelectMethod(modal) {
  $(modal + " #method").empty().append(`
    <option selected value="move">mv (Recommended)</option>
    <option value="rsync">rsync</option>
  `);
}

function populateSelectAfterRSync(modal) {
  $(modal + " #after-rsync").empty().append(`
      <option selected value="true">Remove original file</option>
      <option value="false">Move original file to deleted subfolder</option>
    `);
}

function addRadioButtonsListeners() {
  $("#modalMoveStorageForm .radio-title input").on("ifChecked", function () {
    $("#modalMoveStorageForm ." + $(this).val() + "-display").show();
    if ($(this).val() == "same_pool") {
      $("#modalMoveStorageForm #method").empty().append(`
        <option selected value="move" selected>mv (Recommended)</option>
        <option value="rsync">rsync</option>
        `).trigger("change");
      $("#modalMoveStorageForm #move-from-panel").show();
      $("#modalMoveStorageForm #move-from-panel select").attr("required", true);
      $("#modalMoveStorageForm #storage_pool").attr("required", false);
      $("#modalMoveStorageForm #storage_pool").val(
        $("#modalMoveStorageForm #storage_pool-name").val()
      )
      $("#modalMoveStorageForm #storage_pool-name").trigger("change");
    } else {
      $("#modalMoveStorageForm #method").empty().append(`
        <option value="move">mv</option>
        <option value="rsync" selected>rsync (Recommended)</option>
        `).trigger("change");
      $("#modalMoveStorageForm #move-from-panel").hide();
      $("#modalMoveStorageForm #move-from-panel select").attr("required", false);
      $("#modalMoveStorageForm #storage_pool").attr("required", true);
      $("#modalMoveStorageForm #storage_pool").prop('selectedIndex', 0);
    }
  });
  $("#modalMoveStorageForm .radio-title input").on("ifUnchecked", function () {
    $("#modalMoveStorageForm ." + $(this).val() + "-display").hide();
  });
}

function addSelectStoragePoolListeners(storageData) {
  $("#modalMoveStorageForm #storage_pool").off('change').on('change', function () {
    const pool_id = $(this).val();
    $.ajax({
      url: `/api/v3/admin/storage_pool/${pool_id}`,
      type: "GET",
    }).done(function (pool) {
      populateSelectByPool("#modalMoveStorageForm", pool, storageData, pool.is_default);
    });
  });
}

function addSelectMethodListeners() {
  $("#modalMoveStorageForm #method").on('change', function () {
    if ($(this).val() == "rsync") {
      $("#modalMoveStorageForm #rsync-display").show();
    } else {
      $("#modalMoveStorageForm #rsync-display").hide();
    }
  });
}

function resetMoveForm() {
  var modal = "#modalMoveStorageForm";
  $(modal + " select").empty();
  $(modal + " #move").iCheck("check").iCheck("update")
  $(modal + " #same_pool").iCheck("check").iCheck("update")
  populatePrioritySelect(modal);
}
