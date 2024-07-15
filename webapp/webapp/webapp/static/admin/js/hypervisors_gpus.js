/*
 * Copyright 2017 the Isard-vdi project authors:
 *      Josep Maria Viñolas Auquer
 *      Alberto Larraz Dalmases
 * License: AGPLv3
 */

$(document).ready(function () {
  function format(rowData) {
    var childTable =
      '<table id="cl' +
      rowData.id +
      '" class="display compact nowrap w-100" width="100%">' +
      "</table>";
    return $(childTable).toArray();
  }

  $(".btn-assing-vgpus").on("click", function () {
    new PNotify({
      title: "Reassign physical devices GPU",
      text: "Do you really want to reassign all them?",
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
          url:
            "/api/v3/hypervisors/gpus",
          data: JSON.stringify({}),
          contentType: "application/json",
          success: function (data) {
            gpus_table.ajax.reload();
          },
        });
      })
      .on("pnotify.cancel", function () {});
  });

  modal_add_gpu = $("#modal_add_gpu").DataTable();
  initalize_bookables_modal_events();
  $(".btn-new-gpu").on("click", function () {
    $("#modalAddGpu")
      .modal({ backdrop: "static", keyboard: false })
      .modal("show");
    let reservable_type = $(this).attr("data-panel");
    modal_add_gpu_datatables(reservable_type);
  });

  gpus_table = $("#table-gpus").DataTable({
    ajax: {
      url: "/api/v3/admin/reservables/gpus",
      contentType: "application/json",
      type: "GET",
    },
    sAjaxDataProp: "",
    language: {
      loadingRecords:
        '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
    },
    bLengthChange: false,
    bFilter: false,
    rowId: "id",
    deferRender: true,
    columns: [
      {
        className: "details-control",
        orderable: false,
        data: null,
        defaultContent:
          '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>',
      },
      { data: "name", width: "300px" },
      { data: "description" },
      { data: "physical_device", render: function (data, type, full) {
        return data ? data : `<i class='fa fa-exclamation-triangle' style='color:darkred' title='No physical device assigned'> None</i>`;
      }},
      {
        data: null, render: function (data, type, full, meta) {
          var text = "Err"
          if (data.physical_device != null) {
              if (data.changing_to_profile != false) {
                text = data.active_profile + "->" + data.changing_to_profile
              } else {
                text = data.active_profile
              }
          } else {
            text = "-"
          }
          return text + ' <button id="btn-force_active_profile" class="btn btn-xs btn-danger" type="button" style="margin-left:10px" data-toggle="tooltip" data-placement="right" title="Force active profile"><i class="fa fa-flash"></i></button>'
        }
      },
      {
        data: "plans", width: "85px", render: function (data, type, full) {
          const color = data.active && data.current ? "darkgreen" : "darkred";
          const hasPlans = data.current ? data.profile : "None";
          const content = (data.active || !data.current) || full.active_profile
            ? `${hasPlans}`
            : `<i class='fa fa-exclamation-triangle' style='color:darkred' title='The current plan does not match this GPU&#39;s active profile: ${full.active_profile}'> ${hasPlans}</i>`;
          return `<span style="color:${color}">${content}</span>`;
        }
      },
      {
        data: "desktops_started", render: function (data, type, full, meta) {
          if (full["active_profile"]) {
            return renderProgressGPU(data.length, full["available_units"])
          } else {
            return "0";
          }

        }
      },
      { data: "brand", width: "10px" },
      { data: "model", width: "10px" },
      { data: "architecture" },
      { data: "memory" },
      {
        className: "actions-control",
        orderable: false,
        data: null,
        width: "150px",
        defaultContent:
          '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top"><i class="fa fa-times" style="color:darkred"></i></button>'
      },
    ],
    order: [[7, "desc"]]
  });

  // Add event listener for opening and closing first level childdetails
  $("#table-gpus tbody").on("click", "td.details-control", function () {
    var tr = $(this).closest("tr");
    var row = gpus_table.row(tr);
    var rowData = row.data();

    if (row.child.isShown()) {
      // This row is already open - close it
      row.child.hide();
      tr.removeClass("shown");
      gpus_table.ajax.reload();

      // Destroy the Child Datatable
      $("#cl" + rowData.clientID)
        .DataTable()
        .destroy();
    } else {
      // Open this row
      row.child(format(rowData)).show();
      var id = rowData.id;

      childTable = $("#cl" + id).DataTable({
        dom: "t",
        ajax: {
          url: "/admin/reservables/gpus/" + id,
          contentType: "application/json",
          type: "GET",
        },
        createdRow: function (row, data, dataIndex) {
          $(row).attr("data-reservabletype", "gpus");
          $(row).attr("data-itemId", id);
          $(row).attr("data-subitemId", data.id);
        },
        sAjaxDataProp: "",
        language: {
          loadingRecords:
            '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
        },
        pageLength: 50,
        columns: [
          {
            className: "text-center",
            data: null,
            orderable: false,
            defaultContent:
              "<input id='chk-enabled' type='checkbox' class='form-check-input'></input>",
          },
          { data: "name" },
          { data: "description" },
          { data: "profile" },
          { data: "memory" },
          { data: "units" },
        ],
        columnDefs: [
          {
            targets: 0,
            render: function (data, type, full, meta) {
              if (rowData.profiles_enabled.includes(full.id)) {
                return '<input id="chk-enabled" type="checkbox" class="form-check-input" checked></input>';
              } else {
                return '<input id="chk-enabled" type="checkbox" class="form-check-input"></input>';
              }
            },
          },
        ],
        order: [[5, "asc"]],
        select: false,
      });

      tr.addClass("shown");
    }
  });

  $("#table-gpus")
    .find(" tbody")
    .on("click", "input", function () {
      profile_checkbox = $(this)
      let reservable_type = $(this).parents("tr").attr("data-reservableType");
      let item_id = $(this).parents("tr").attr("data-itemId");
      let subitem_id = $(this).parents("tr").attr("data-subitemId");

      switch ($(this).attr("id")) {
        case "chk-enabled":
          if ($(this).is(":checked")) {
            enabled = true;
          } else {
            enabled = false;
          }

          if (!enabled) {
            // check if it's the last profile of this kind
            $.ajax({
              type: "GET",
              url:
                "/api/v3/admin/reservables/check/last/" +
                reservable_type +
                "/" +
                subitem_id +
                "/" +
                item_id,
              contentType: "application/json",
              error: function (data) {
                new PNotify({
                  title: 'ERROR: Could not ' + (enabled? 'enable': 'disable') + ' GPU profile',
                  text: data.responseJSON ? data.responseJSON.description : "Something went wrong",
                  hide: true,
                  delay: 2000,
                  icon: 'fa fa-' + data.icon,
                  opacity: 1,
                  type: 'error'
              })
              profile_checkbox.prop("checked", true)
            },
            }).done(function(data) {
              data = JSON.parse(data)
              // check if the profile is in any domain or has plans
              if (data['last'].includes(true)) {
                if (data['desktops'].length > 0 || data['plans'].length > 0) {
                  showDeleteGPUModal(subitem_id, item_id, reservable_type, data);
                } else {
                  enableProfile(reservable_type, item_id, subitem_id, enabled, null, null, false);
                }
              } else {
                enableProfile(reservable_type, item_id, subitem_id, enabled, null, null, false)
              }
            });
          } else {
            enableProfile(reservable_type, item_id, subitem_id, enabled, null, null, false);
          }
      }
    });

  $('#modalDeleteGPUForm #notify-user').on("ifUnchecked", function () {
    $('#modalDeleteGPU #send').prop('disabled', false);
  });

  $("#modalDeleteGPU #send").on('click', function (e) {
    $("#modalDeleteGPU #send").prop('disabled', true);
    var form = $('#modalDeleteGPUForm');
    if (form.parsley().isValid()) {
      data = $('#modalDeleteGPUForm').serializeObject();
      var item_id = $('#modalDeleteGPUForm #item_id').val();
      var subitem_id = $('#modalDeleteGPUForm #subitem_id').val();
      var reservable_type = $('#modalDeleteGPUForm #reservable_type').val();
      var desktops = JSON.parse($('#modalDeleteGPUForm #desktops').val());
      var plans = JSON.parse($('#modalDeleteGPUForm #plans').val());
      if (subitem_id) {
        enableProfile(reservable_type, item_id, subitem_id, false, desktops, plans, data["notify-user"] === "on")
      } else {
        deleteReservable(reservable_type, item_id, data["notify-user"] === "on");
      }
    }
  });

  $("#modalDeleteGPU #cancel").on('click', function (e) {
    if (typeof profile_checkbox !== 'undefined') {
      profile_checkbox.prop("checked", true);
    }
  });

  $("#table-gpus")
    .find("tbody")
    .on("click", "button", function () {
      let reservable_type = "gpus";
      let item_id = $(this).closest('tr').attr("id");
      if ($(this).attr("id") == "btn-delete") {
        new PNotify({
          title: "Delete GPU",
          text: "Do you really want to delete this gpu?",
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
              type: "GET",
              url:
                "/api/v3/admin/reservables/check/last/" +
                reservable_type +
                "/" +
                item_id,
              contentType: "application/json",
              error: function (data) {
                new PNotify({
                  title: 'ERROR: Could not delete GPU profile',
                  text: data.responseJSON ? data.responseJSON.description : "Something went wrong",
                  hide: true,
                  delay: 2000,
                  icon: 'fa fa-' + data.icon,
                  opacity: 1,
                  type: 'error'
                });
              }
            }).done(function (data) {
              data = JSON.parse(data);
              if (data['last'].includes(true)) {
                if (data['desktops'].length > 0 || data['plans'].length > 0) {
                  showDeleteGPUModal(null, item_id, reservable_type, data);
                } else {
                  deleteReservable(reservable_type, item_id);
                }
              } else {
                deleteReservable(reservable_type, item_id);
              }
            });
          })
          .on("pnotify.cancel", function () { });
      } else if ($(this).attr("id") == "btn-force_active_profile") {
        var data=gpus_table.row($(this).parents('tr')).data();
        $("#modalForcedProfileForm")[0].reset();
        $('#modalForcedProfileForm #id').val(data.id);
        $('#modalForcedProfileForm #physical_device').val(data.physical_device);
        $('#modalForcedProfile').modal({
          backdrop: 'static',
          keyboard: false
        }).modal('show');
        GpuEnabledProfilesDropdown(data.id);
      }
    });

    $("#modalForcedProfile #send").off('click').on('click', function(e){
        var notice = new PNotify({
            text: 'Updating profile...',
            hide: false,
            opacity: 1,
            icon: 'fa fa-spinner fa-pulse'
        })
        data=$('#modalForcedProfileForm').serializeObject();
        profile_id = data["forced_active_profile"].split("-")[2];
        data["actual_active_profile"] = document.getElementById(data.id).children[4].textContent.trim();
        if (data["actual_active_profile"] == profile_id) {
          return notice.update({
            title: 'ERROR',
            text: 'Selected profile is already the active profile',
            type: 'error',
            hide: true,
            icon: 'fa fa-warning',
            delay: 5000,
            opacity: 1
          })
        }
        $.ajax({
            type: 'PUT',
            url: '/engine/profile/gpu/'+data["physical_device"],
            data: JSON.stringify({"profile_id":profile_id}),
            contentType: 'application/json',
            error: function(data) {
                notice.update({
                    title: 'ERROR updating profile',
                    text: data.statusText,
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 5000,
                    opacity: 1
                })
            },
            success: function(data) {
                $('form').each(function() { this.reset() });
                $('.modal').modal('hide');
                notice.update({
                    title: 'Updated',
                    text: 'GPU active profile updated successfully',
                    hide: true,
                    delay: 2000,
                    icon: 'fa fa-' + data.icon,
                    opacity: 1,
                    type: 'success'
                })
            }
        })
    });
});

function showDeleteGPUModal(subitem_id, item_id, reservable_type, data) {
  if (subitem_id) {
    $('#modalDeleteGPUForm #subitem_id').val(subitem_id);
    $("#modalDeleteGPU #title").text(" Disable profile");
    $("#modalDeleteGPU .item_type").text("profile");
  } else {
    $("#modalDeleteGPU #title").text(" Delete GPU");
    $("#modalDeleteGPU .item_type").text("GPU");
  }
  $("#modalDeleteGPU #send").prop('disabled', false);
  $('#modalDeleteGPUForm #item_id').val(item_id);
  $('#modalDeleteGPUForm #reservable_type').val(reservable_type);
  $('#modalDeleteGPUForm #desktops').val(JSON.stringify(data['desktops']));
  $('#modalDeleteGPUForm #plans').val(JSON.stringify(data['plans']));
  $('#modalDeleteGPUForm #bookings').val(JSON.stringify(data['bookings']));
  $('#modalDeleteGPUForm #deployments').val(JSON.stringify(data['deployments']));
  $('#modalDeleteGPUForm #notify-user').iCheck('uncheck').iCheck('update');
  $('#modalDeleteGPUForm .table tbody').empty();
  if (data['desktops'].length > 0) {
    $.each(data['desktops'], function (key, value) {
      value['user_name'] = value['username'];
      infoDomains(value, $('#desktops_table tbody'));
    });
  } else {
    $('#desktops_table tbody').append(`<tr class="active"><td/><td colspan="3" style="text-align:center;">No items</td></tr>`);
  }
  if (data['plans'].length > 0) {
    $.each(data['plans'], function (key, value) {
      value['kind'] = 'plan';
      start = new Date(value['start']).toLocaleString('es-ES');
      end = new Date(value['end']).toLocaleString('es-ES');
      value['name'] = "from <i>" + start + "</i> to <i>" + end + "<i>";
      infoDomains(value, $('#plans_table tbody'));
    });
  } else {
    $('#plans_table tbody').append(`<tr class="active"><td/><td colspan="3" style="text-align:center;">No items</td></tr>`);
  }
  if (data['bookings'].length > 0) {
    $.each(data['bookings'], function (key, value) {
      value['kind'] = 'booking';
      start = new Date(value['start']).toLocaleString('es-ES');
      end = new Date(value['end']).toLocaleString('es-ES');
      value['name'] = "from <i>" + start + "</i> to <i>" + end + "<i>";
      value['user_name'] = value['username'];
      infoDomains(value, $('#bookings_table tbody'));
    });
  } else {
    $('#bookings_table tbody').append(`<tr class="active"><td/><td colspan="3" style="text-align:center;">No items</td></tr>`);

  }
  if (data['deployments'].length > 0) {
    $.each(data['deployments'], function (key, value) {
      value['kind'] = 'deployment';
      value['name'] = value["tag_name"];
      value['user_name'] = value['username'];
      infoDomains(value, $('#deployments_table tbody'));
    });
  } else {
    $('#deployments_table tbody').append(`<tr class="active"><td/><td colspan="3" style="text-align:center;">No items</td></tr>`);

  }
  $('#modalDeleteGPUForm .table tbody tr td:first-child').remove()  
  $('#modalDeleteGPU').modal({
    backdrop: 'static',
    keyboard: false
  }).modal('show');
}

// Modals functions
function modal_add_gpu_datatables(reservable_type) {
  modal_add_gpu.destroy();
  $("#modalAddGpu #bookable").val("");
  $("#modalAddGpu #reservable_type").val(reservable_type);
  $("#modalAddGpu #datatables-error-status").empty();

  modal_add_gpu = $("#modal_add_gpu").DataTable({
    ajax: {
      url: "/api/v3/admin/profiles/" + reservable_type, // defined through attribute data-panel in add new button
      dataSrc: "",
    },
    scrollY: "125px",
    scrollCollapse: true,
    paging: false,
    language: {
      loadingRecords:
        '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
      zeroRecords: "No matching " + reservable_type + " found",
      info: "Showing _START_ to _END_ of _TOTAL_ " + reservable_type,
      infoEmpty: "Showing 0 to 0 of 0 " + reservable_type,
      infoFiltered: "(filtered from _MAX_ total " + reservable_type + ")",
    },
    rowId: "id",
    deferRender: true,
    columns: [
      { data: "name" },
      { data: "brand", width: "10px" },
      { data: "model" },
      { data: "description" },
    ],
    order: [[0, "asc"]],
    pageLength: 5,
  });
  modal_add_gpu.columns().every(function () {
    var that = this;

    $("input", this.header()).on("keyup change", function () {
      if (that.search() !== this.value) {
        that.search(this.value).draw();
      }
    });
  });
}

function initalize_bookables_modal_events() {
  $("#modal_add_gpu tbody").on("click", "tr", function () {
    let rdata = modal_add_gpu.row(this).data();
    if ($(this).hasClass("selected")) {
      $(this).removeClass("selected");
      $("#modal_add_gpu").closest(".x_panel").addClass("datatables-error");
      $("#modalAddGpu #datatables-error-status")
        .html("No bookable selected")
        .addClass("my-error");
      $("#modalAddGpu #bookable").val("");
    } else {
      modal_add_gpu.$("tr.selected").removeClass("selected");
      $(this).addClass("selected");
      $("#modal_add_gpu").closest(".x_panel").removeClass("datatables-error");
      $("#modalAddGpu #datatables-error-status")
        .empty()
        .html(
          '<b style="color:DarkSeaGreen">vGPU Profile selected: ' +
            rdata["name"] +
            "</b>"
        )
        .removeClass("my-error");
      $("#modalAddGpu #bookable").val(rdata["id"]);
    }
  });

  $("#modalAddGpu #send").on("click", function (e) {
    var form = $("#modalAddGpu #modalAdd");
    form.parsley().validate();

    if (form.parsley().isValid()) {
      bookable = $("#modalAddGpu #bookable").val();
      reservable_type = $("#modalAddGpu #reservable_type").val();
      if (bookable != "" && reservable_type != "") {
        data = $("#modalAddGpu #modalAdd").serializeObject();
        $.ajax({
          type: "POST",
          url:
            "/api/v3/admin/reservables/" +
            $("#modalAddGpu #reservable_type").val(),
          data: JSON.stringify(data),
          contentType: "application/json",
          success: function (data) {
            gpus_table.ajax.reload();
            $("form").each(function () {
              this.reset();
            });
            $(".modal").modal("hide");
            var notice = new PNotify({
              title: "Created",
              text: 'GPU created successfully. Please, reassing physical devices',
              hide: true,
              delay: 2000,
              icon: 'fa fa-' + data.icon,
              opacity: 1,
              type: 'success'
          })
          },
        });
      } else {
        $("#modal_add_desktops")
          .closest(".x_panel")
          .addClass("datatables-error");
        $("#modalAddGpu #datatables-error-status")
          .html("No bookable selected")
          .addClass("my-error");
      }
    }
  });
}

function enableProfile(reservable_type, item_id, subitem_id, enabled, desktops, plans, notify_user) {
  $.ajax({
    type: "PUT",
    url:
      "/api/v3/admin/reservables/enable/" +
      reservable_type +
      "/" +
      item_id +
      "/" +
      subitem_id  + (notify_user ? "/notify_user" : ""),
    data: JSON.stringify({ enabled, desktops, plans }),
    contentType: "application/json",
    success: function(data)
      {
          $('form').each(function() { this.reset() });
          $('.modal').modal('hide');
          new PNotify({
              title: "GPU profile " + (enabled? 'enabled': 'disabled'),
              text: 'Updated ' + subitem_id,
              hide: true,
              delay: 2000,
              icon: 'fa fa-' + data.icon,
              opacity: 1,
              type: 'success'
          })
      },
    error: function(data) 
    {
      new PNotify({
        title: "ERROR enabling/disabling profile",
        text: data.responseJSON ? data.responseJSON.description : "Something went wrong",
        hide: true,
        delay: 2000,
        icon: 'fa fa-' + data.icon,
        opacity: 1,
        type: 'error'
    })
    }
  });
}

function GpuEnabledProfilesDropdown(gpu_id) {
  $("#modalForcedProfileForm #forced_active_profile").empty();
  $.ajax({
    method: "POST",
    async: false,
    url: "/api/v3/admin/table/gpus",
    data: JSON.stringify({"id": gpu_id}),
    contentType: "application/json",
    accept: "application/json",
  }).done(function (data) {
    data.profiles_enabled.forEach(function(profile){
      $("#modalForcedProfileForm #forced_active_profile").append('<option value=' + profile + '>' + profile+'</option>');
    });
  });
}

function deleteReservable(reservable_type, item_id, notify_user) {
  $.ajax({
    type: "DELETE",
    url:
      "/api/v3/admin/reservables/delete/" +
      reservable_type +
      "/" +
      item_id + (notify_user ? "/notify_user" : ""),
    contentType: "application/json",
    success: function (data) {
      $('form').each(function () { this.reset() });
      $('.modal').modal('hide');
      new PNotify({
        title: "Success",
        text: 'Deleted GPU',
        hide: true,
        delay: 2000,
        opacity: 1,
        type: 'success'
      });
      $("#table-gpus").DataTable().row('#' + item_id).remove().draw();
    },
    error: function (data) {
      new PNotify({
        title: "ERROR deleting GPU",
        text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
        hide: true,
        delay: 2000,
        opacity: 1,
        type: 'error'
      });
    }
  });
}

function renderProgressGPU(progress, total) {
  return ` ${progress}/${total}  <div class="progress"> 
            <div class="progress-bar" role="progressbar" aria-valuenow="${progress}" 
              aria-valuemin="0" aria-valuemax="${total}" style="width:${(progress / total) * 100}%;">
            </div> 
          </div>`;
}
