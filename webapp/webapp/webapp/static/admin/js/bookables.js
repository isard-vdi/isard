/*
 * Copyright 2017 the Isard-vdi project authors:
 *      Josep Maria Viñolas Auquer
 *      Alberto Larraz Dalmases
 * License: AGPLv3
 */

$(document).ready(function () {
  $vgpu = $(".bookables_detail")
  // RESERVABLE VGPUS
  vgpus_table = $("#reservables_vgpus").DataTable({
    ajax: {
      url: "/admin/table/reservables_vgpus",
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
      { data: "priority_id" },
      { data: "brand", defaultContent: "system" },
      { data: "model" },
      { data: "profile", defaultContent: "-" },
      { data: "units", defaultContent: "Any" },
      { data: "total_units" },
      {
        className: "actions-control",
        orderable: false,
        data: null,
        defaultContent:
          '<button id="btn-alloweds" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-users" style="color:darkblue"></i></button>\
                                 <button id="btn-edit" class="btn btn-xs btn-edit-interface" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>',
      },
    ],
    "columnDefs": [
      {
          "targets": 3,
          "render": function ( data, type, full, meta ) {
              return full.priority_id ? full.priority_id: '-';
          }
      },
      {
        "targets": 8,
        "render": function ( data, type, full, meta ) {
            return full.total_units ? full.total_units: '-';
        }
      },
    ],
    order: [[1, "asc"]],
  });

  $("#reservables_vgpus")
    .find(" tbody")
    .on("click", "button", function () {
      var data = vgpus_table.row($(this).parents("tr")).data();
      switch ($(this).attr("id")) {
        case "btn-alloweds":
          modalAllowedsFormShow("reservables_vgpus", data);
          break;
        case "btn-edit":
          $("#modalEditBookable #modalEdit")[0].reset();
          $("#modalEditBookable")
            .modal({
              backdrop: "static",
              keyboard: false,
            })
            .modal("show");
          $("#modalEditBookable #modalEdit").parsley();
          $("#modalEdit #bookable_id").val(data.id);
          $("#modalEdit #bookable_table").val("reservables_vgpus");
          $("#modalEdit #name").val(data.name);
          $("#modalEdit #description").val(data.description);
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
              $('#priority option[value="' + data.priority_id + '"]').prop("selected",true);
            },
          });
          break;
      }
    });

  $("#modalEditBookable #send").on("click", function (e) {
    var form = $("#modalEdit");
    form.parsley().validate();
    data = $("#modalEdit").serializeObject();
    payload = {
      id: data.bookable_id,
      name: data.name,
      description: data.description,
      priority_id: data.priority
    };
    $.ajax({
      type: "PUT",
      url: "/admin/table/update/" + data.bookable_table,
      data: JSON.stringify(payload),
      contentType: "application/json",
      success: function (data) {
        vgpus_table.ajax.reload();
        $("form").each(function () {
          this.reset();
        });
        $(".modal").modal("hide");
      },
    });
  });

  $('#reservables_vgpus').find('tbody').on('click', 'td.details-control', function() {
    var tr = $(this).closest('tr');
    var row = vgpus_table.row(tr);
    if (row.child.isShown()) {
        // This row is already open - close it
        row.child.hide();
        tr.removeClass('shown');
    } else {
        // Close other rows
        if (vgpus_table.row('.shown').length) {
            $('.details-control', vgpus_table.row('.shown').node()).click();
        }
        // Open this row
        row.child(renderVGPUPannel(row.data())).show()
        tr.addClass('shown');
        $('#status-detail-' + row.data().id).html(row.data().detail);

        setAlloweds_viewer('#alloweds-' + row.data().id, row.data().id, "reservables_vgpus");
    }
});


  // SocketIO
  socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/administrators', {
    'query': {'jwt': localStorage.getItem("token")},
    'path': '/api/v3/socket.io/',
    'transports': ['websocket']
  });

  socket.on("connect", function () {
    connection_done();
    console.log("Listening admins namespace");
  });

  socket.on("connect_error", function (data) {
    connection_lost();
  });

  socket.on('user_quota', function(data) {
    var data = JSON.parse(data);
    drawUserQuota(data);
  });

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
});

function renderVGPUPannel ( d ) {

  $newPanel = $vgpu.clone();
  $newPanel.html(function(i, oldHtml){
    return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name).replace(/d.description/g, d.description);
  });
  return $newPanel
}