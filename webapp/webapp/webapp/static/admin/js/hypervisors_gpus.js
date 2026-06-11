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
    bLengthChange: true,
    bFilter: true,
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
      { data: "name", width: "300px", render: function (data, type, full) {
        var suffix = '';
        if (full.gpu_warnings && full.gpu_warnings.length > 0) {
          var tooltip = full.gpu_warnings.join('&#10;');
          suffix += ' <i class="fa fa-microchip" style="color:orange" title="' + tooltip + '"></i>';
        }
        if (full.gpu_notes && full.gpu_notes.length > 0) {
          var notes_tooltip = full.gpu_notes.join('&#10;');
          suffix += ' <i class="fa fa-info-circle" style="color:#3c8dbc" title="' + notes_tooltip + '"></i>';
        }
        return data + suffix;
      }},
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
          if (data.last_apply_error) {
            text += ' <i class="fa fa-exclamation-triangle" style="color:darkred" title="' + String(data.last_apply_error).replace(/"/g, '&quot;') + '"></i>'
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
          '<button id="btn-edit" class="btn btn-xs" type="button" data-placement="top"><i class="fa fa-pencil" style="color:darkblue"></i></button> ' +
          '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top"><i class="fa fa-times" style="color:darkred"></i></button>'
      },
    ],
    order: [[7, "desc"]]
  });

  // Real-time updates for GPU profile changes
  waitDefined("socket", function () {
    socket.on('vgpu_data', function (raw) {
      var data = JSON.parse(raw);
      gpus_table.rows().every(function () {
        var rowData = this.data();
        if (rowData.physical_device === data.id) {
          rowData.active_profile = data.vgpu_profile;
          rowData.changing_to_profile = data.changing_to_profile;
          rowData.last_apply_error = data.last_apply_error;
          rowData.desktops_started = data.desktops_started;
          // Operator-intent fields surface "what the operator asked for"
          // separately from "what is currently bound on the card". When
          // the two diverge (profile_mismatch=true) the table renders the
          // requested profile with a warning chip so the operator can
          // either retry the change or pick a new profile. We never
          // auto-resolve the mismatch from the client side — that mirrors
          // the engine policy of never auto-mutating operator intent.
          rowData.requested_profile = data.requested_profile;
          rowData.operator_passthrough = data.operator_passthrough;
          rowData.profile_mismatch = data.profile_mismatch;
          if (typeof data.available_units !== 'undefined') {
            rowData.available_units = data.available_units;
          }
          this.data(rowData).invalidate();
          gpus_table.draw(false);
        }
      });
    });
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
          // The id actually enabled on this card for this base profile: the
          // bare base, or "<base>~<variant>". Empty when not enabled. Used so a
          // disable/re-key targets the real id (not a recomputed one).
          var enabledId =
            (rowData.profiles_enabled || []).find(function (p) {
              return p === data.id || p.indexOf(data.id + "~") === 0;
            }) || "";
          $(row).attr("data-enabledId", enabledId);
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
          { data: null, title: "Variant", orderable: false, defaultContent: "" },
        ],
        columnDefs: [
          {
            targets: 0,
            render: function (data, type, full, meta) {
              // Checked when the base profile OR any "<base>~<variant>" of it is
              // enabled on this card.
              var en = (rowData.profiles_enabled || []).some(function (p) {
                return p === full.id || p.indexOf(full.id + "~") === 0;
              });
              return en
                ? '<input id="chk-enabled" type="checkbox" class="form-check-input" checked></input>'
                : '<input id="chk-enabled" type="checkbox" class="form-check-input"></input>';
            },
          },
          {
            // Optional variant name: differentiates same brand-model-profile
            // cards into distinct selectable reservables ("<base>~<variant>").
            // Read-only display + an Edit button that opens modalEditVariant; the
            // variant is no longer free-typed inline (it must drive reservable
            // create/delete + total_units, so it goes through a confirmed flow).
            targets: 6,
            orderable: false,
            render: function (data, type, full, meta) {
              var enabledId = (rowData.profiles_enabled || []).find(function (p) {
                return p === full.id || p.indexOf(full.id + "~") === 0;
              });
              var variant =
                enabledId && enabledId.indexOf("~") >= 0
                  ? enabledId.split("~")[1]
                  : "";
              var label = variant
                ? '<span class="label label-info">' + variant + "</span>"
                : '<span class="text-muted">&mdash;</span>';
              // Names already defined for this base profile (other cards), passed
              // to the editor so the admin can re-use one without retyping it.
              var existing = (full.variants || []).join(",");
              return (
                '<span style="display:inline-block;min-width:70px">' + label + "</span> " +
                '<button type="button" class="btn btn-xs btn-default btn-edit-variant" ' +
                'data-base="' + full.id + '" ' +
                'data-memory="' + (full.memory || "") + '" ' +
                'data-variants="' + existing + '" ' +
                'title="Manage variant"><i class="fa fa-pencil"></i></button>'
              );
            },
          },
        ],
        order: [[5, "asc"]],
        select: false,
      });

      tr.addClass("shown");
    }
  });

  // Click handler for GPU desktops progress bar
  $("#table-gpus tbody").on("click", ".gpu-desktops-click", function (e) {
    e.stopPropagation();
    var tr = $(this).closest("tr");
    var data = gpus_table.row(tr).data();
    if (!data || !data.desktops_started || data.desktops_started.length === 0) return;

    $.ajax({
      type: "POST",
      url: "/admin/domains",
      contentType: "application/json",
      data: JSON.stringify({
        kind: "desktop",
        domain_ids: JSON.stringify(data.desktops_started),
      }),
      success: function (domains) {
        if ($.fn.DataTable.isDataTable("#table-gpu-desktops")) {
          $("#table-gpu-desktops").DataTable().destroy();
          $("#table-gpu-desktops tbody").empty();
        }
        var gpuName = data.brand + " " + data.model + " - " + data.physical_device;
        $("#modalGpuDesktopsLabel").text("Running desktops on " + gpuName);
        $("#table-gpu-desktops").DataTable({
          data: domains,
          dom: "t",
          pageLength: 50,
          columns: [
            {
              data: "id",
              orderable: false,
              render: function (data) {
                return '<button class="btn btn-xs btn-info" data-domain-info="' + data + '" title="View details"><i class="fa fa-info-circle"></i></button>';
              },
            },
            { data: "name" },
            {
              data: "status",
              render: function (data) {
                var statusClass = "default";
                if (data === "Started") statusClass = "success";
                else if (data === "Stopped" || data === "Failed") statusClass = "danger";
                else if (data === "Starting" || data === "Shutting-down") statusClass = "warning";
                return '<span class="label label-' + statusClass + '">' + data + '</span>';
              },
            },
            { data: "user_name" },
            { data: "group_name" },
            { data: "category_name" },
            {
              data: "accessed",
              render: function (data) {
                return data ? moment.unix(data).fromNow() : "Never";
              },
            },
          ],
        });
        $("#modalGpuDesktops").modal("show");
      },
      error: function (data) {
        new PNotify({
          title: "ERROR loading desktops",
          text: data.responseJSON ? data.responseJSON.description : "Something went wrong",
          hide: true,
          delay: 2000,
          opacity: 1,
          type: "error",
        });
      },
    });
  });

  $("#table-gpus")
    .find(" tbody")
    .on("click", "input", function () {
      profile_checkbox = $(this)
      let reservable_type = $(this).parents("tr").attr("data-reservableType");
      let item_id = $(this).parents("tr").attr("data-itemId");
      let base_id = $(this).parents("tr").attr("data-subitemId");
      // The variant is now managed through the Edit button / modalEditVariant, not
      // here: the checkbox simply enables the BARE profile and disables whatever id
      // is actually enabled on this card (bare or "<base>~<variant>").
      let subitem_id = base_id;
      let enabledId =
        $(this).parents("tr").attr("data-enabledId") || subitem_id;

      switch ($(this).attr("id")) {
        case "chk-enabled":
          if ($(this).is(":checked")) {
            enabled = true;
          } else {
            enabled = false;
          }

          if (!enabled) {
            // Disable the id that is ACTUALLY enabled (so unchecking a variant
            // removes "<base>~<variant>", not a reconstructed base).
            subitem_id = enabledId;
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
                // Last card for this profile: the whole reservable is removed and
                // the cascade destroys desktops/deployments/plans/bookings. Warn
                // whenever ANY reference exists.
                if (data['desktops'].length > 0 || data['plans'].length > 0 ||
                    data['deployments'].length > 0 || data['bookings'].length > 0) {
                  showDeleteGPUModal(subitem_id, item_id, reservable_type, data, true);
                } else {
                  enableProfile(reservable_type, item_id, subitem_id, enabled, null, null, false);
                }
              } else {
                // Other cards still realize the profile, so desktops/deployments
                // keep their GPU. But this card's planned availability is dropped
                // and any booking tied solely to it is removed -- warn if so.
                if (data['plans'].length > 0 || data['bookings'].length > 0) {
                  showDeleteGPUModal(subitem_id, item_id, reservable_type, data, false);
                } else {
                  enableProfile(reservable_type, item_id, subitem_id, enabled, null, null, false)
                }
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
      var rekey_to = $('#modalDeleteGPUForm #rekey_to').val();
      var desktops = JSON.parse($('#modalDeleteGPUForm #desktops').val());
      var plans = JSON.parse($('#modalDeleteGPUForm #plans').val());
      if (subitem_id && rekey_to) {
        // Variant re-key: disable the old id (cascade confirmed above) then enable
        // the new one, sequentially.
        rekeyVariant(reservable_type, item_id, subitem_id, rekey_to, desktops, plans, data["notify-user"] === "on")
      } else if (subitem_id) {
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
                // Warn whenever ANY reference exists -- a deployment-only or
                // booking-only GPU is destroyed by the cascade too.
                if (data['desktops'].length > 0 || data['plans'].length > 0 ||
                    data['deployments'].length > 0 || data['bookings'].length > 0) {
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
      } else if ($(this).attr("id") == "btn-edit") {
        var data = gpus_table.row($(this).parents('tr')).data();
        $("#modalEditGpuForm")[0].reset();
        $('#modalEditGpuForm #id').val(data.id);
        $('#modalEditGpuForm #name').val(data.name);
        $('#modalEditGpuForm #description').val(data.description);
        $('#modalEditGpu').modal({
          backdrop: 'static',
          keyboard: false
        }).modal('show');
      } else if ($(this).attr("id") == "btn-force_active_profile") {
        var data=gpus_table.row($(this).parents('tr')).data();
        if (!data.profiles_enabled || data.profiles_enabled.length === 0) {
            new PNotify({
                title: 'No profiles enabled',
                text: 'Enable at least one GPU profile first by expanding the GPU row and checking a profile.',
                type: 'warning',
                hide: true,
                delay: 4000,
                icon: 'fa fa-warning',
                opacity: 1
            });
            return;
        }
        $("#modalForcedProfileForm")[0].reset();
        $('#modalForcedProfileForm #id').val(data.id);
        $('#modalForcedProfileForm #physical_device').val(data.physical_device);
        $('#modalForcedProfile').modal({
          backdrop: 'static',
          keyboard: false
        }).modal('show');
        GpuEnabledProfilesDropdown(data.id);
        // Admin pre-flight: preview which desktops would be stopped and which
        // reservables would be removed (no other card provides them) for the
        // selected target profile, before the admin confirms.
        $('#forced_active_profile').off('change.preview').on('change.preview', function(){
          forceProfilePreview(data.id, $(this).val());
        });
        forceProfilePreview(data.id, $('#forced_active_profile').val());
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
        profile_id = data["forced_active_profile"].split("-").slice(2).join("-");
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
        // Detect MIG ↔ vGPU/passthrough mode switch and warn user
        var oldIsMig = /^\d+g\./.test(data["actual_active_profile"]);
        var newIsMig = /^\d+g\./.test(profile_id);
        if (oldIsMig !== newIsMig) {
          if (!confirm("This will switch the GPU between MIG and vGPU/passthrough mode. " +
              "The GPU will be reset and all running instances on it will be stopped. Continue?")) {
            notice.remove();
            return;
          }
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

    $("#modalEditGpu #send").off('click').on('click', function(e) {
        var form = $('#modalEditGpuForm');
        form.parsley().validate();
        if (form.parsley().isValid()) {
            var data = form.serializeObject();
            var item_id = data.id;
            $.ajax({
                type: 'PUT',
                url: '/api/v3/admin/reservables/gpus/' + item_id,
                data: JSON.stringify({ name: data.name, description: data.description }),
                contentType: 'application/json',
                success: function(data) {
                    $('form').each(function() { this.reset() });
                    $('.modal').modal('hide');
                    gpus_table.ajax.reload();
                    new PNotify({
                        title: 'Updated',
                        text: 'GPU updated successfully',
                        hide: true,
                        delay: 2000,
                        opacity: 1,
                        type: 'success'
                    });
                },
                error: function(data) {
                    new PNotify({
                        title: 'ERROR updating GPU',
                        text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                        hide: true,
                        delay: 2000,
                        opacity: 1,
                        type: 'error'
                    });
                }
            });
        }
    });

    // --- Profile variant editor -------------------------------------------------
    // Open the editor with the variant names already defined for this base profile
    // (so the admin can re-use one to join cards) plus a "new variant" option.
    $("#table-gpus").find("tbody").on("click", ".btn-edit-variant", function (e) {
      e.stopPropagation();
      profile_checkbox = undefined; // not a checkbox flow; avoid cancel re-check
      var $tr = $(this).closest("tr");
      var item_id = $tr.attr("data-itemId");
      var base = $(this).attr("data-base") || $tr.attr("data-subitemId");
      var enabledId = $tr.attr("data-enabledId") || "";
      var memory = $(this).attr("data-memory");
      var current =
        enabledId && enabledId.indexOf("~") >= 0 ? enabledId.split("~")[1] : "";
      var existing = ($(this).attr("data-variants") || "")
        .split(",")
        .filter(function (v) { return v; });

      $("#modalEditVariant #variant_item_id").val(item_id);
      $("#modalEditVariant #variant_base").val(base);
      $("#modalEditVariant #variant_enabled_id").val(enabledId);
      $("#modalEditVariant #variant_profile_label").text(
        base + (memory ? " (" + memory + " vRAM)" : "")
      );

      var names = existing.slice();
      if (current && names.indexOf(current) < 0) names.push(current);
      names.sort();
      var $sel = $("#modalEditVariant #variant_select").empty();
      $sel.append('<option value="">none (bare)</option>');
      names.forEach(function (n) {
        $sel.append('<option value="' + n + '">' + n + "</option>");
      });
      $sel.append('<option value="__new__">new variant…</option>');
      $sel.val(current || "");
      $("#modalEditVariant #variant_new").val("");
      $("#modalEditVariant #variant_new_group").hide();

      $("#modalEditVariant").modal({ backdrop: "static", keyboard: false }).modal("show");
    });

    $("#modalEditVariant #variant_select").off("change").on("change", function () {
      $("#modalEditVariant #variant_new_group").toggle($(this).val() === "__new__");
    });

    $("#modalEditVariant #send").off("click").on("click", function () {
      var item_id = $("#modalEditVariant #variant_item_id").val();
      var base = $("#modalEditVariant #variant_base").val();
      var enabledId = $("#modalEditVariant #variant_enabled_id").val();
      var reservable_type =
        $("#modalEditVariant #variant_reservable_type").val() || "gpus";
      var sel = $("#modalEditVariant #variant_select").val();
      var newVariant = (sel === "__new__")
        ? ($("#modalEditVariant #variant_new").val() || "").trim()
        : (sel || "");
      if (newVariant && !/^[a-z0-9]{1,20}$/.test(newVariant)) {
        new PNotify({
          title: "Invalid variant name",
          text: "Use 1-20 lowercase alphanumerics (a-z, 0-9).",
          hide: true, delay: 3000, icon: "fa fa-warning", opacity: 1, type: "error",
        });
        return;
      }
      var newId = base + (newVariant ? "~" + newVariant : "");

      if (!enabledId) {
        // Not enabled on this card yet: enable it directly with the chosen variant.
        $("#modalEditVariant").modal("hide");
        enableProfile(reservable_type, item_id, newId, true, null, null, false);
        return;
      }
      if (newId === enabledId) {
        $("#modalEditVariant").modal("hide");
        new PNotify({
          title: "No change", text: "Variant unchanged.",
          type: "info", hide: true, delay: 2000, opacity: 1,
        });
        return;
      }
      // Re-key: the old reservable is removed (its bookings/plans on this card go
      // with it; if it is the last card, its desktops/deployments lose the GPU) and
      // a new one is created with default permissions/priority. Show the impact.
      $("#modalEditVariant").modal("hide");
      $.ajax({
        type: "GET",
        url: "/api/v3/admin/reservables/check/last/" +
          reservable_type + "/" + enabledId + "/" + item_id,
        contentType: "application/json",
        error: function (data) {
          new PNotify({
            title: "ERROR checking variant impact",
            text: data.responseJSON ? data.responseJSON.description : "Something went wrong",
            hide: true, delay: 3000, opacity: 1, type: "error",
          });
        },
      }).done(function (data) {
        data = JSON.parse(data);
        var isLast = data["last"].includes(true);
        var hasRefs = isLast
          ? (data["desktops"].length > 0 || data["plans"].length > 0 ||
             data["deployments"].length > 0 || data["bookings"].length > 0)
          : (data["plans"].length > 0 || data["bookings"].length > 0);
        if (hasRefs) {
          showDeleteGPUModal(enabledId, item_id, reservable_type, data, isLast, newId);
        } else {
          rekeyVariant(reservable_type, item_id, enabledId, newId, null, null, false);
        }
      });
    });
});

function showDeleteGPUModal(subitem_id, item_id, reservable_type, data, isLast, rekeyTo) {
  // isLast === false is a NON-LAST disable: the profile survives on other cards,
  // so desktops/deployments keep their GPU and only THIS card's plans/bookings
  // are removed. Don't list desktops/deployments as affected in that case.
  // rekeyTo (optional): when set, this is a variant RE-KEY -- after the old id is
  // disabled (with the cascade shown here), the new id is enabled. The Save button
  // in the modal chains both via rekeyVariant().
  if (isLast === undefined) isLast = true;
  $('#modalDeleteGPUForm #rekey_to').val(rekeyTo || "");
  if (subitem_id) {
    $('#modalDeleteGPUForm #subitem_id').val(subitem_id);
    $("#modalDeleteGPU #title").text(
      rekeyTo ? " Change variant" : (isLast ? " Disable profile" : " Disable profile on this card")
    );
    $("#modalDeleteGPU .item_type").text("profile");
  } else {
    $("#modalDeleteGPU #title").text(" Delete GPU");
    $("#modalDeleteGPU .item_type").text("GPU");
  }
  // On a non-last disable the profile remains realizable on other cards, so no
  // desktop/deployment loses its GPU -- present empty lists for those.
  var desktopsAffected = isLast ? data['desktops'] : [];
  var deploymentsAffected = isLast ? data['deployments'] : [];
  $("#modalDeleteGPU #send").prop('disabled', false);
  $('#modalDeleteGPUForm #item_id').val(item_id);
  $('#modalDeleteGPUForm #reservable_type').val(reservable_type);
  $('#modalDeleteGPUForm #desktops').val(JSON.stringify(desktopsAffected));
  $('#modalDeleteGPUForm #plans').val(JSON.stringify(data['plans']));
  $('#modalDeleteGPUForm #bookings').val(JSON.stringify(data['bookings']));
  $('#modalDeleteGPUForm #deployments').val(JSON.stringify(deploymentsAffected));
  $('#modalDeleteGPUForm #notify-user').iCheck('uncheck').iCheck('update');
  $('#modalDeleteGPUForm .table tbody').empty();
  data = Object.assign({}, data, {desktops: desktopsAffected, deployments: deploymentsAffected});
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
              text: 'GPU created successfully.',
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

function rekeyVariant(reservable_type, item_id, oldId, newId, desktops, plans, notify_user) {
  // Sequential disable(old) -> enable(new): the order matters so the new
  // reservable's total_units card-count is computed after the old id is gone.
  // disable goes through the same choke point a plain profile disable uses, so it
  // recomputes total_units (if other cards still realize it) or deletes + cascades.
  $.ajax({
    type: "PUT",
    url:
      "/api/v3/admin/reservables/enable/" + reservable_type + "/" + item_id + "/" +
      oldId + (notify_user ? "/notify_user" : ""),
    data: JSON.stringify({ enabled: false, desktops: desktops, plans: plans }),
    contentType: "application/json",
    error: function (data) {
      new PNotify({
        title: "ERROR removing old variant",
        text: data.responseJSON ? data.responseJSON.description : "Something went wrong",
        hide: true, delay: 3000, opacity: 1, type: "error",
      });
    },
  }).done(function () {
    $.ajax({
      type: "PUT",
      url: "/api/v3/admin/reservables/enable/" + reservable_type + "/" + item_id + "/" + newId,
      data: JSON.stringify({ enabled: true, desktops: null, plans: null }),
      contentType: "application/json",
      success: function (data) {
        $(".modal").modal("hide");
        gpus_table.ajax.reload();
        new PNotify({
          title: "Variant updated",
          text: "Re-keyed to " + newId,
          hide: true, delay: 2500, icon: "fa fa-" + data.icon, opacity: 1, type: "success",
        });
      },
      error: function (data) {
        gpus_table.ajax.reload();
        new PNotify({
          title: "ERROR setting new variant",
          text: data.responseJSON ? data.responseJSON.description : "Something went wrong",
          hide: true, delay: 4000, opacity: 1, type: "error",
        });
      },
    });
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

function forceProfilePreview(card_id, target_profile) {
  var $panel = $('#forcedProfilePreview');
  if (!target_profile) { $panel.html(''); return; }
  $panel.html('<span class="text-muted"><i class="fa fa-spinner fa-pulse"></i> Checking impact…</span>');
  $.ajax({
    method: "POST",
    url: "/api/v3/admin/gpu/" + card_id + "/force_profile_preview",
    data: JSON.stringify({ "target_profile": target_profile }),
    contentType: "application/json",
  }).done(function (p) {
    var stop = p.desktops_to_stop || [];
    var remove = p.resources_to_remove || [];
    var html = '';
    if (stop.length) {
      html += '<div class="alert alert-warning" style="margin:0 0 6px">' +
        '<i class="fa fa-warning"></i> ' + stop.length +
        ' running desktop(s) will be STOPPED on this card: ' +
        $('<div>').text(stop.join(', ')).html() + '</div>';
    }
    if (remove.length) {
      html += '<div class="alert alert-danger" style="margin:0 0 6px">' +
        '<i class="fa fa-trash"></i> No other card provides these reservables — ' +
        'they may be REMOVED (with their bookings) when the change takes effect: ' +
        $('<div>').text(remove.join(', ')).html() + '</div>';
    }
    if (!stop.length && !remove.length) {
      html = '<span class="text-success"><i class="fa fa-check"></i> ' +
        'No desktops stopped, no resources removed.</span>';
    }
    $panel.html(html);
  }).fail(function () {
    $panel.html('<span class="text-muted">Impact preview unavailable.</span>');
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
  return `<span class="gpu-desktops-click" style="cursor:pointer"> ${progress}/${total}  <div class="progress">
            <div class="progress-bar" role="progressbar" aria-valuenow="${progress}"
              aria-valuemin="0" aria-valuemax="${total}" style="width:${(progress / total) * 100}%;">
            </div>
          </div></span>`;
}
