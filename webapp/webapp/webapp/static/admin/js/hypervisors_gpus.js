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
      url: "/admin/table/gpus",
      contentType: "application/json",
      type: "POST",
      data: function (d) {
        return JSON.stringify({ order: "id" });
      },
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
      { data: "physical_device" },
      { data: null },
      { data: "brand", width: "10px" },
      { data: "model", width: "10px" },
      { data: "architecture" },
      { data: "memory" },
      // {
      //   className: "actions-control",
      //   orderable: false,
      //   data: null,
      //   width: "150px",
      //   defaultContent:
      //     '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top"><i class="fa fa-times" style="color:darkred"></i></button>'
      // },
    ],
    order: [[7, "desc"]],
    "columnDefs": [ {
        "targets": 4,
        "render": function ( data, type, full, meta ) {
          var text ="Err"
          if( data.physical_device != null ){
              $.ajax({
                method: "GET",
                async: false,
                url: "/engine/profile/gpu/"+data.physical_device,
              }).success(function (response) {
                if( response.changing_to_profile != false ){
                  text= response.vgpu_profile+"->"+response.changing_to_profile
                }else{
                  text= response.vgpu_profile
                }
              }).error(function (XMLHttpRequest, textStatus, errorThrown) {
                console.log("Status: " + textStatus); console.log("Error: " + errorThrown);
              })
          }else{
            text = "-"
          }
          return text
        }},]
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
                subitem_id,
              contentType: "application/json",
            }).done(function(data) {
              data = JSON.parse(data)
              // check if the profile is in any domain
              if((data['last'] == true) && (data['desktops'].length > 0)) {
                $('#modalDeleteProfile').modal({
                    backdrop: 'static',
                    keyboard: false
                }).modal('show');

                $('#modalDeleteProfileForm #subitem_id').val(subitem_id);
                $('#modalDeleteProfileForm #item_id').val(item_id);
                $('#modalDeleteProfileForm #reservable_type').val(reservable_type);
                $('#modalDeleteProfileForm #desktops').val(JSON.stringify(data['desktops']));

                $('#table_modal_profile_delete tbody').empty()
                $.each(data['desktops'], function(key, value) {
                  value['user_name'] = value['username']
                  infoDomains(value, $('#table_modal_profile_delete tbody'));
              });      
              }
              else {
                enableProfile(reservable_type, item_id, subitem_id, enabled, null) 
              }
            })
          } else {
            enableProfile(reservable_type, item_id, subitem_id, enabled, null) 
          }
          break;
      }
    });

  $("#modalDeleteProfile #send").on('click', function(e){
      var form = $('#modalDeleteProfileForm');
      if (form.parsley().isValid()){
        data = $('#modalDeleteProfileForm').serializeObject()
        var item_id = $('#modalDeleteProfileForm #item_id').val()
        var subitem_id = $('#modalDeleteProfileForm #subitem_id').val()
        var reservable_type = $('#modalDeleteProfileForm #reservable_type').val()
        var desktops = JSON.parse($('#modalDeleteProfileForm #desktops').val())

        enableProfile(reservable_type, item_id, subitem_id, false, desktops)  
      }
  });

  $("#modalDeleteProfile #cancel").on('click', function(e){
    profile_checkbox.prop("checked", true)
  });

  $("#table-gpus")
    .find("tbody")
    .on("click", "button", function () {
      let reservable_type = $(this).parents("tr").attr("data-reservableType");
      let item_id = $(this).parents("tr").attr("data-itemId");
      let subitem_id = $(this).parents("tr").attr("data-subitemId");
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
              type: "DELETE",
              url:
                "/api/v3/admin/reservables/" +
                reservable_type +
                "/" +
                item_id +
                "/" +
                subitem_id,
              data: JSON.stringify({ enabled }),
              contentType: "application/json",
            });
          })
          .on("pnotify.cancel", function () {});
      }
      if ($(this).attr("id") == "btn-edit") {
      }
    });
});

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
          '<b style="color:DarkSeaGreen">Bookable selected: ' +
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

function enableProfile(reservable_type, item_id, subitem_id, enabled, desktops) {
  $.ajax({
    type: "PUT",
    url:
      "/api/v3/admin/reservables/enable/" +
      reservable_type +
      "/" +
      item_id +
      "/" +
      subitem_id,
    data: JSON.stringify({ enabled, desktops }),
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
        title: "ERROR",
        text: 'Could not ' + (enabled? 'enable': 'disable') + ' GPU profile ' + subitem_id,
        hide: true,
        delay: 2000,
        icon: 'fa fa-' + data.icon,
        opacity: 1,
        type: 'error'
    })
    }
  });
}