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
      // Dedicated bookables endpoint: returns each reservable enriched with the
      // distinct categories of its backing cards (the generic items/table feed
      // returned raw rows with no card join).
      url: "/api/v4/items/bookables/gpus",
      contentType: "application/json",
      type: "GET",
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
      {
        data: "name",
        render: function (data, type, full, meta) {
          if (type !== "display") return data;
          var esc = function (s) {
            return String(s).replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
          };
          // The "~<variant>" rides in the reservable id; the stored name has it
          // appended as " [<variant>]". Strip that exact suffix (model names also
          // contain brackets, so never parse "[...]" out of the name) and render
          // the variant as a blue tag instead of inline text.
          var variant = full.id && full.id.indexOf("~") >= 0 ? full.id.split("~").pop() : null;
          var name = data || "";
          var tail = " [" + variant + "]";
          if (variant && name.slice(-tail.length) === tail) name = name.slice(0, -tail.length);
          var html = esc(name);
          if (variant) {
            html += ' <span class="label label-info" title="Variant">' + esc(variant) + "</span>";
          }
          // Categories backing this reservable (server-computed: distinct
          // categories of the cards whose profiles_enabled include it). Green tag,
          // matching the GPU admin delegated-category colour.
          (full.categories || []).forEach(function (cat) {
            html +=
              ' <span class="label label-success" title="Delegated to category"><i class="fa fa-users"></i> ' +
              esc(cat) +
              "</span>";
          });
          return html;
        },
      },
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
            url: "/api/v4/items/bookings/priority-rules",
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
    if (!form.parsley().isValid()) return;
    data = $("#modalEdit").serializeObject();
    payload = {
      id: data.bookable_id,
      name: data.name,
      description: data.description,
      priority_id: data.priority
    };
    $.ajax({
      type: "PUT",
      url: "/api/v4/admin/item/table/update/" + data.bookable_table,
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
})

function renderVGPUPannel ( d ) {

  $newPanel = $vgpu.clone();
  $newPanel.html(function(i, oldHtml){
    return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name).replace(/d.description/g, d.description);
  });
  return $newPanel
}