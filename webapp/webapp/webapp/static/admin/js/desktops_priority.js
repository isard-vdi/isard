/*
 * Copyright 2017 the Isard-vdi project authors:
 *      Josep Maria Viñolas Auquer
 *      Alberto Larraz Dalmases
 * License: AGPLv3
 */

$(document).ready(function () {
  $desktops_priority_detail = $(".desktops_priority_detail");
  desktops_priority = $("#desktops_priority").DataTable({
    ajax: {
      url: "/admin/table/desktops_priority",
      contentType: "application/json",
      type: "POST",
      data: function (d) {
        return JSON.stringify({ order_by: "name" });
      },
    },
    sAjaxDataProp: "",
    language: {
      loadingRecords:
        '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
    },
    rowId: "id",
    deferRender: true,
    columns: [
      {
        className: "details-control",
        orderable: false,
        data: null,
        defaultContent: '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
      },
      { data: "name" },
      { data: "description" },
      { data: "priority" },
      { data: "max_time", defaultContent: "-" }, 
      { data: "warning_time", defaultContent: "-" },
      { data: "danger_time", defaultContent: "-" }, 
      { data: "op", defaultContent: "-" },
      {
        className: "actions-control",
        orderable: false,
        data: null,
        defaultContent: '<button id="btn-alloweds" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-users" style="color:darkblue"></i></button> \
                         <button id="btn-edit" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button> \
                         <button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>',
      },
    ],
    order: [[1, "asc"]],
    columnDefs: [
      {
        targets: 4,
        render: function (data, type, full, meta) {
          var action = full.op;
          if (full[action]) {
            return full[action].max
          }
        }
      },
      {
        targets: 5,
        render: function (data, type, full, meta) {
          var action = full.op;
          if (full[action]) {
            const intervals = full[action].notify_intervals;
            for (var i = 0; i < intervals.length; i++) {
              if (intervals[i].type == "warning") {
                return(intervals[i].time)
              }
            }
          }
        },
      },
      {
        targets: 6,
        render: function (data, type, full, meta) {
          var action = full.op;
          if (full[action]) {
            const intervals = full[action].notify_intervals;
            for (var i = 0; i < intervals.length; i++) {
              if (intervals[i].type == "danger") {
                return(intervals[i].time)
              }
            }
          }
        }
      },
    ],
  });
  
  $("#desktops_priority").find(" tbody").on("click", "button", function () {
    var data = desktops_priority.row($(this).parents("tr")).data();
    switch ($(this).attr("id")) {
      case "btn-delete":
        new PNotify({
          title: "<b>WARNING</b>",
          type: "error",
          text: "Are you sure you want to delete timeout " + data["name"] + "?",
          hide: false,
          opacity: 0.9,
          confirm: {
            confirm: true,
          },
          buttons: {
            closer: false,
            sticker: false,
          },
          history: {
            history: false,
          },
          addclass: 'pnotify-center-large',
          width: '550'
        }).get().on("pnotify.confirm", function () {
          $.ajax({
            type: "DELETE",
            url: "/admin/table/desktops_priority/"+data["id"],
            contentType: "application/json",
            success: function (data) {
              desktops_priority.ajax.reload();
            },
            error: function (xhr, ajaxOptions, thrownError) {
              new PNotify({
                title: "ERROR deleting timeout",
                text: xhr.responseJSON.description,
                hide: true,
                delay: 3000,
                icon: 'fa fa-warning',
                opacity: 1,
                type: 'error'
              });
            }
          });
        }).on("pnotify.cancel", function () {});
        break;
      case "btn-edit":
        $("#modalEditPriority #modalEdit")[0].reset();
        $("#modalEditPriority").modal({
          backdrop: "static",
          keyboard: false,
        }).modal("show");
        $("#modalEditPriority #modalEdit").parsley();
        $("#modalEdit #id").val(data.id);
        $("#modalEdit #op").val(data.op);
        $("#modalEdit #name").val(data.name);
        $("#modalEdit #description").val(data.description);
        $("#modalEdit #priority").val(data.priority);
        var action = data.op
        $("#modalEdit #max_time").val(data[action].max);
        const intervals = data[action].notify_intervals;
        for (var i = 0; i < intervals.length; i++) {
          if (intervals[i].type == "warning") {
            $("#modalEdit #warning_time").val(intervals[i].time);
          } else if (intervals[i].type == "danger") {
            $("#modalEdit #danger_time").val(intervals[i].time);
          }
        }
        break;
      case "btn-alloweds":
        modalAllowedsFormShow("desktops_priority", data);
        break;
    }
  });
  
  $(".add-new").on("click", function () {
    $("#modalAddPriority #modalAdd").attr("disabled", false);
    $("#modalAdd")[0].reset();
    $("#modalAddPriority").modal({
      backdrop: "static",
      keyboard: false,
    }).modal("show");
    $("modalAddPriority modalAdd").parsley();
    setAlloweds_add("#alloweds-priority-add");
    $("#modalAddPriority #modalAdd #alloweds_panel").attr("style", "display: block;");
  });
  
  $("#modalAddPriority #send").on("click", function (e) {
    var form = $("#modalAdd");
    data = form.serializeObject();
    data = data2integers(data)
    data = replaceAlloweds_arrays("#modalAddPriority #alloweds-priority-add", data);
    data = parseTimeValues(data)

    form.parsley().validate();
    if (form.parsley().isValid()) {
      $.ajax({
        type: "POST",
        url: "/admin/table/add/desktops_priority",
        data: JSON.stringify(data),
        contentType: "application/json",
        success: function (data) {
          desktops_priority.ajax.reload();
          $("form").each(function () {
            this.reset();
          });
          $(".modal").modal("hide");
        },
        error: function (xhr, ajaxOptions, thrownError) {
          if (xhr.status == 409) {
            new PNotify({
              title: "ERROR creating timeout",
              text: "There is already another timeout with that name",
              hide: true,
              delay: 3000,
              icon: 'fa fa-warning',
              opacity: 1,
              type: 'error'
            });
          }
        }
      });
    }
  });
  
  $("#modalEditPriority #send").on("click", function (e) {
    var form = $("#modalEdit");
    data = $("#modalEdit").serializeObject();
    data = data2integers(data)
    data["id"]=data.priority_id
    data = parseTimeValues(data)

    delete data.priority_id
    delete data.max_time
    delete data.danger_time
    delete data.warning_time

    form.parsley().validate();
    if (form.parsley().isValid()) {
      $.ajax({
        type: "PUT",
        url: "/admin/table/update/desktops_priority",
        data: JSON.stringify(data),
        contentType: "application/json",
        success: function (data) {
          desktops_priority.ajax.reload();
          $("form").each(function () {
            this.reset();
          });
          $(".modal").modal("hide");
        },
        error: function (xhr, ajaxOptions, thrownError) {
          if (xhr.status == 409) {
            new PNotify({
              title: "ERROR updating timeout",
              text: "There is already another timeout with that name",
              hide: true,
              delay: 3000,
              icon: 'fa fa-warning',
              opacity: 1,
              type: 'error'
            });
          }
        }
      });
    }
  });
  
  $('#desktops_priority').find('tbody').on('click', 'td.details-control', function() {
    var tr = $(this).closest('tr');
    var row = desktops_priority.row(tr);
    if (row.child.isShown()) {
      // This row is already open - close it
      row.child.hide();
      tr.removeClass('shown');
    } else {
      // Close other rows
      if (desktops_priority.row('.shown').length) {
          $('.details-control', desktops_priority.row('.shown').node()).click();
      }
      // Open this row
      row.child(renderDesktopPriorityDetail(row.data())).show()
      tr.addClass('shown');
      $('#status-detail-' + row.data().id).html(row.data().detail);

      setAlloweds_viewer('#alloweds-' + row.data().id, row.data().id, "desktops_priority");
    }
  });
});

function renderDesktopPriorityDetail ( d ) {
  $newPanel = $desktops_priority_detail.clone();
  $newPanel.html(function(i, oldHtml){
    return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name).replace(/d.description/g, d.description);
  });
  return $newPanel
}

function parseTimeValues (data) {
  var action = data.op;
  if ((data["warning_time"] >= 0) || (data["danger_time"] >= 0)) {
    return new PNotify({
      title: "ERROR",
      text: "Warning (min) and Danger (min) time values must be under zero",
      hide: true,
      delay: 3000,
      icon: 'fa fa-warning',
      opacity: 1,
      type: 'error'
    });
  }

  if (data["max_time"] <= 0) {
    return new PNotify({
      title: "ERROR",
      text: "Max (min) must be over zero",
      hide: true,
      delay: 3000,
      icon: 'fa fa-warning',
      opacity: 1,
      type: 'error'
    });
  }

  if ((data["max_time"] <= data["warning_time"]) || (data["max_time"] <= data["danger_time"])) {
    return new PNotify({
      title: "ERROR",
      text: "Max (min) must be the greatest value",
      hide: true,
      delay: 3000,
      icon: 'fa fa-warning',
      opacity: 1,
      type: 'error'
    });
  }

  if (data["warning_time"] >= data["danger_time"]) {
    return new PNotify({
      title: "ERROR",
      text: "Warning (min) must be minor than Danger (min)",
      hide: true,
      delay: 3000,
      icon: 'fa fa-warning',
      opacity: 1,
      type: 'error'
    });
  }

  data[action] = {
    "max": data["max_time"],
    "notify_intervals": [
      {
        "time": (data["danger_time"]),
        "type": "danger"
      },
      {
        "time": (data["warning_time"]),
        "type": "warning"
      }
    ],
    "server": false
  }
  return data
}

function data2integers(data){
  data["priority"]=parseInt(data["priority"]);
  data["max_time"]=parseInt(data["max_time"]);
  data["danger_time"]=parseInt(data["danger_time"]);
  data["warning_time"]=parseInt(data["warning_time"]);
  return data
}