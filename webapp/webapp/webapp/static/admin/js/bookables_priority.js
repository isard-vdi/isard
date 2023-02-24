/*
 * Copyright 2017 the Isard-vdi project authors:
 *      Josep Maria Viñolas Auquer
 *      Alberto Larraz Dalmases
 * License: AGPLv3
 */

$(document).ready(function () {
  $bookable = $(".bookings_priority_detail");
  // RESERVABLE VGPUS
  bookings_priority = $("#bookings_priority").DataTable({
    ajax: {
      url: "/admin/table/bookings_priority",
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
      { data: "rule_id" },
      { data: "name" },
      { data: "description" },
      { data: "roles", defaultContent: "-" },
      { data: "categories", defaultContent: "-" },
      { data: "groups", defaultContent: "-" },
      { data: "users", defaultContent: "-" },
      { data: "priority" },
      { data: "forbid_time" },
      { data: "max_time" },
      { data: "max_items" },
      {
        className: "actions-control",
        orderable: false,
        data: null,
        defaultContent:
          '<button id="btn-alloweds" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-users" style="color:darkblue"></i></button> \
            <button id="btn-edit" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button> \
            <button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>',
      },
    ],
    order: [[1, "asc"]],
    columnDefs: [
      {
        targets: 4,
        render: function (data, type, full, meta) {
          var string = full.role_names.join(",");
          var res = string.substring(0,20)+"...";
          return res
        },
      },
      {
        targets: 5,
        render: function (data, type, full, meta) {
          var string = full.category_names.join(",");
          var res = string.substring(0,20)+"...";
          return res
        },
      },
      {
        targets: 6,
        render: function (data, type, full, meta) {
          var string = full.group_names.join(",");
          var res = string.substring(0,20)+"...";
          return res
        },
      },
      {
        targets: 7,
        render: function (data, type, full, meta) {
          var string = full.user_names.join(",");
          var res = string.substring(0,20)+"...";
          return res
        },
      },
    ],
  });

  $("#bookings_priority")
    .find(" tbody")
    .on("click", "button", function () {
      var data = bookings_priority.row($(this).parents("tr")).data();
      switch ($(this).attr("id")) {
        case "btn-delete":
          new PNotify({
            title: "Confirmation Needed",
            text: "Are you sure you want to delete: " + data["name"] + "?",
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
            addclass: "pnotify-center",
          })
            .get()
            .on("pnotify.confirm", function () {
              data["table"] = "remotevpn";
              $.ajax({
                type: "DELETE",
                url: "/admin/table/bookings_priority/"+data["id"],
                contentType: "application/json",
                success: function (data) {
                  $("form").each(function () {
                    this.reset();
                  });
                  $(".modal").modal("hide");
                  bookings_priority.ajax.reload();
                },
                error: function (xhr, ajaxOptions, thrownError) {
                  new PNotify({
                      title: "ERROR deleting priority",
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
            .on("pnotify.cancel", function () {});
          break;
        case "btn-edit":
          $("#modalEditPriority #modalEdit")[0].reset();
          $("#modalEditPriority")
            .modal({
              backdrop: "static",
              keyboard: false,
            })
            .modal("show");
          $("#modalEditPriority #modalEdit").parsley();
          $("#modalEdit #priority_id").val(data.id);
          $("#modalEdit #name").val(data.name);
          $("#modalEdit #description").val(data.description);
          $("#modalEdit #rule_id").val(data.rule_id);
          $("#modalEdit #priority").val(data.priority);
          $("#modalEdit #forbid_time").val(data.forbid_time);
          $("#modalEdit #max_time").val(data.max_time);
          $("#modalEdit #max_items").val(data.max_items);
          break;
        case "btn-alloweds":
          modalAllowedsFormShow("bookings_priority", data);
          break;
      }
    });

  $(".add-new").on("click", function () {
    $("#modalAddPriority #modalAdd").attr("disabled", false);
    $("#modalAdd")[0].reset();
    $("#modalAddPriority")
      .modal({
        backdrop: "static",
        keyboard: false,
      })
      .modal("show");
    $("modalAddPriority modalAdd").parsley();
    setAlloweds_add("#alloweds-priority-add");
    $("#modalAddPriority #modalAdd #alloweds_panel").attr("style", "display: block;");
  });

  $("#modalAddPriority #send").on("click", function (e) {
    var form = $("#modalAdd");
    data = form.serializeObject();
    data = data2integers(data)


    data = replaceAlloweds_arrays(
      "#modalAddPriority #alloweds-priority-add",
      data
    );
    form.parsley().validate();
    if (form.parsley().isValid()) {
      //Insert
      $.ajax({
        type: "POST",
        url: "/admin/table/add/bookings_priority",
        data: JSON.stringify(data),
        contentType: "application/json",
        success: function (data) {
          bookings_priority.ajax.reload();
          $("form").each(function () {
            this.reset();
          });
          $(".modal").modal("hide");
        },
        error: function (xhr, ajaxOptions, thrownError) {
          if (xhr.status == 409) {
            new PNotify({
                title: "ERROR creating priority",
                text: xhr.responseJSON.description,
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
    form.parsley().validate();
    data = $("#modalEdit").serializeObject();
    data = data2integers(data)

    data["id"]=data.priority_id
    if (form.parsley().isValid()) {
      $.ajax({
        type: "PUT",
        url: "/admin/table/update/bookings_priority",
        data: JSON.stringify(data),
        contentType: "application/json",
        success: function (data) {
          bookings_priority.ajax.reload();
          $("form").each(function () {
            this.reset();
          });
          $(".modal").modal("hide");
        },
        error: function (xhr, ajaxOptions, thrownError) {
          new PNotify({
              title: "ERROR updating priority",
              text: xhr.responseJSON.description,
              hide: true,
              delay: 3000,
              icon: 'fa fa-warning',
              opacity: 1,
              type: 'error'
          });
        }
      });
    }
  });

  $('#bookings_priority').find('tbody').on('click', 'td.details-control', function() {
    var tr = $(this).closest('tr');
    var row = bookings_priority.row(tr);
    if (row.child.isShown()) {
        // This row is already open - close it
        row.child.hide();
        tr.removeClass('shown');
    } else {
        // Close other rows
        if (bookings_priority.row('.shown').length) {
            $('.details-control', bookings_priority.row('.shown').node()).click();
        }
        // Open this row
        row.child(renderBookableDetailPannel(row.data())).show()
        tr.addClass('shown');
        $('#status-detail-' + row.data().id).html(row.data().detail);

        setAlloweds_viewer('#alloweds-' + row.data().id, row.data().id, "bookings_priority");
    }
});

bookings_priority_computed = $("#bookings_priority_computed").DataTable({
  sAjaxDataProp: "",
  language: {
    loadingRecords:
      '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
  },
  rowId: "id",
  deferRender: true,
  columns: [
    { data: "username" },
    { data: "rule_id" },
    { data: "role" },
    { data: "category" },
    { data: "group" },
    { data: "priority" },
    { data: "forbid_time" },
    { data: "max_time" },
    { data: "max_items" },
  ],
  order: [[1, "asc"]],
  columnDefs: [],
});

$(".btn-compute").on("click", function () {
  new PNotify({
    title: "Compute users priorities",
    text: "WARNING! This can take a while and be quite process consuming. Continue?",
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
        type: "POST",
        url:
          "/api/v3/bookings/priorities",
        data: JSON.stringify({"rule_id":$('#priority').val()}),
        contentType: "application/json",
        success: function (data) {
          data = JSON.parse(data);
          bookings_priority_computed.clear();
          bookings_priority_computed.rows.add(data).draw();
        },
      });
    })
    .on("pnotify.cancel", function () {});
});

  $.ajax({
    type: "GET",
    url: "/api/v3/admin/priority/rules",
    contentType: "application/json",
    dataType: "json",
    success: function (response) {
      $("#priority").find('option').remove();
      response.forEach(function(rule) {
        $("#priority").append(
          "<option value=" + rule.rule_id + ">" + rule.rule_id + "</option>"
        );
      })
      $('#priority option[value="' + response.priority_id + '"]').prop("selected",true);
    },
  });
    $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on)
})
function socketio_on(){
  socket.on("add_form_result", function (data) {
    console.log("received result");
    var data = JSON.parse(data);
    if (data.result) {
      $("#modalAddScheduler")[0].reset();
      $("#modalScheduler").modal("hide");
    }
    new PNotify({
      title: data.title,
      text: data.text,
      hide: true,
      delay: 4000,
      icon: "fa fa-" + data.icon,
      opacity: 1,
      type: data.type,
    });
  });
}

function renderBookableDetailPannel ( d ) {

  $newPanel = $bookable.clone();
  $newPanel.html(function(i, oldHtml){
    return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name).replace(/d.description/g, d.description);
  });
      return $newPanel
}

function data2integers(data){
  data["forbid_time"]=parseInt(data["forbid_time"]);
  data["max_items"]=parseInt(data["max_items"]);
  data["max_time"]=parseInt(data["max_time"]);
  data["priority"]=parseInt(data["priority"]);
  return data
}