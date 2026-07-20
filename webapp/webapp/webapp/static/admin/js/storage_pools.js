/*
 *   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
 *   Copyright (C) 2022 Lídia Montero Gutiérrez
 *
 *   This program is free software: you can redistribute it and/or modify
 *   it under the terms of the GNU Affero General Public License as published by
 *   the Free Software Foundation, either version 3 of the License, or
 *   (at your option) any later version.
 *
 *   This program is distributed in the hope that it will be useful,
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *   GNU Affero General Public License for more details.
 *
 *   You should have received a copy of the GNU Affero General Public License
 *   along with this program.  If not, see <https://www.gnu.org/licenses/>.
 *
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

// --------------------------------------------------------------------------- //
// Lazy per-pool disk-item counts.
//
// The count is NOT in the /storage-pools payload (it needs a storage-tree walk,
// which is why the migration pool-plan endpoint is uncached). So it is fetched
// on demand — only when the admin toggles the "Disk items" column visible — and
// cached in the browser (localStorage) so it survives re-toggles and reloads. A
// Refresh button forces a re-fetch. Mirrors the migration panel's caching idea.
// --------------------------------------------------------------------------- //
const SP_DISKCOUNT_LS = "sp_diskcounts_v1";      // poolId -> {items_total, items_by_kind, bytes_total, ts}
const SP_DISKCOL_VIS_LS = "sp_diskcount_visible_v1";
let spDiskCounts = {};
try { spDiskCounts = JSON.parse(localStorage.getItem(SP_DISKCOUNT_LS) || "{}") || {}; } catch (e) { spDiskCounts = {}; }
const spDiskLoading = {};   // poolId -> true while its fetch is in flight

function spPersistCounts() {
  try { localStorage.setItem(SP_DISKCOUNT_LS, JSON.stringify(spDiskCounts)); } catch (e) { /* quota/full — ignore */ }
}

function spHumanBytes(n) {
  n = Number(n) || 0;
  const u = ["B", "KB", "MB", "GB", "TB", "PB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (i === 0 ? n : n.toFixed(1)) + " " + u[i];
}

// Per-type disk kinds shown in the "Items" cell, with the same icons the pool
// paths use for each usage.
const SP_ITEM_KINDS = [
  { key: "template", icon: "fa-cubes", label: "Templates" },
  { key: "desktop", icon: "fa-desktop", label: "Desktops" },
  { key: "media", icon: "fa-circle-o", label: "Media" }
];

// One cell's content for a pool id, off the client cache / loading state.
// Shows a per-type breakdown (templates / desktops / media), each with its icon;
// a zero type is dimmed so rows still line up. The cell tooltip carries the
// total + size + fetch time.
function spDiskCountCell(poolId) {
  if (spDiskLoading[poolId]) return '<i class="fa fa-spinner fa-pulse" title="Loading…"></i>';
  const c = spDiskCounts[poolId];
  if (!c) return '<span class="text-muted" title="Click Refresh to load the disk-item counts.">—</span>';
  if (c.items_total === "?") return '<span class="text-muted" title="Could not load — click Refresh to retry.">?</span>';
  const k = c.items_by_kind || {};
  const parts = SP_ITEM_KINDS.map(function (x) {
    const n = k[x.key] || 0;
    const dim = n ? "" : ' style="color:#ccc;"';
    return `<span title="${x.label}: ${n}"${dim}><i class="fa ${x.icon}"></i>&nbsp;${n}</span>`;
  }).join("&nbsp;&nbsp;&nbsp;");
  const tip = `Total ${c.items_total} disks · ${spHumanBytes(c.bytes_total)}` +
    (c.ts ? ` · as of ${new Date(c.ts).toLocaleString()}` : "");
  return `<span title="${tip}" style="white-space:nowrap;font-size:12px;">${parts}</span>`;
}

// Re-render just the diskcount column cells (render reads the external cache).
function spRedrawCounts() {
  if (typeof storage_pools_table !== "undefined" && storage_pools_table) {
    storage_pools_table.draw(false);
  }
}

// Fetch counts for every pool row. `force` re-fetches even cached pools; else
// only the ones missing from the cache. Concurrency-limited so a big install
// does not fire dozens of tree-walk requests at once.
function spLoadDiskCounts(force) {
  if (typeof storage_pools_table === "undefined" || !storage_pools_table) return;
  const pools = storage_pools_table.rows().data().toArray();
  const targets = pools.filter(function (p) { return p && p.id && (force || !spDiskCounts[p.id]); });
  if (!targets.length) { spRedrawCounts(); return; }
  let idx = 0;
  const MAX = 4;
  function next() {
    if (idx >= targets.length) return;
    const p = targets[idx++];
    spDiskLoading[p.id] = true;
    spRedrawCounts();
    $.ajax({ type: "GET", url: `/api/v4/admin/storage-pool/${p.id}/migration/plan` })
      .done(function (data) {
        const t = (data && data.totals) || {};
        spDiskCounts[p.id] = {
          items_total: t.items_total || 0,
          items_by_kind: t.items_by_kind || {},
          bytes_total: t.bytes_total || 0,
          ts: Date.now()
        };
        spPersistCounts();
      })
      .fail(function () {
        spDiskCounts[p.id] = { items_total: "?", items_by_kind: {}, bytes_total: 0 };
      })
      .always(function () {
        spDiskLoading[p.id] = false;
        spRedrawCounts();
        next();
      });
  }
  for (let c = 0; c < Math.min(MAX, targets.length); c++) next();
}

$(document).ready(function () {
  DEFAULT_STORAGE_POOL_ID = ""
  $.ajax({
    type: "GET",
    url: "/api/v4/storage-pool/default",
    success: function (data) {
      DEFAULT_STORAGE_POOL_ID = data.id;
    }
  });

  checkStorageLaneHealth();

  storage_pools_table = $('#storage_pools').DataTable({
    "ajax": {
      "type": 'GET',
      "url": "/api/v4/storage-pools",
      "dataSrc": "storage_pools",
      "contentType": "application/json",
    },
    "language": {
      "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
    },
    "columns": [
      {
        "className": 'details-control',
        "orderable": false,
        "data": null,
        "width": "10px",
        "defaultContent": '<button id="btn-details" class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
      },
      {
        "data": "enabled",
        "title": '<span title="Storage pool enabled — its category disks use the pool paths">Enab.</span>',
        "width": '46px',
        "className": "text-center",
        render: function (enabled, type) {
          return renderEnabled(enabled, 'check');
        }
      },
      { "data": "enabled_virt", "title": '<span title="Virtualization enabled on this pool">Virt.</span>', "width": '42px', "className": "text-center", render: function (data, type, full, meta) { return renderEnabled(data, 'check'); } },
      { "data": "id", "title": "Pool ID" },
      { "data": "name", "title": "Name" },
      { "data": "mountpoint", "title": "Mountpoint" },
      {
        "data": "categories_names", "title": "Categories", "render": function (data, type, full, meta) {
          var categoryList = []
          $.each(data, function (index, category) {
            categoryList.push(category["name"])
          })
          return categoryList.join(", ");
        }
      },
      {
        "data": "storages", "title": '<span title="Available disk operations — storage workers ready to serve this pool">Disk ops</span>', "width": "62px", "className": "text-center", "render": function (data, type, full, meta) {
          return (data == 0 && full.enabled) ?
            `<i title="No disk operations available for this pool. Disk operations will fail" class="fa fa-warning" style="color:red;"> ${data}</i> ` :
            data
        }
      },
      {
        "data": "hypers", "title": '<span title="Available virt operations — hypervisors serving this pool">Virt ops</span>', "width": "62px", "className": "text-center", "render": function (data, type, full, meta) {
          return (data == 0 && full.enabled) ?
            `<i title="No hypervisors virt operations available for this pool. Virt operations will fail" class="fa fa-warning" style="color:red;"> ${data}</i> ` :
            data
        }
      },
      { "data": "qos_disk_id", "title": '<span title="QoS Disk ID applied to this pool">QoS</span>', "width": "64px", "render": function (data, type, full, meta) { return data ? data : '<span class="text-muted">Ignore</span>' } },
      { "data": "description", "title": "Description", 'defaultContent': '' },
      {
        // Lazy per-pool disk-item count. Hidden by default; toggling it visible
        // (colvis) gathers the counts from the migration pool-plan endpoint and
        // caches them in the browser (localStorage). Not part of the pool row
        // payload, so `data:null` and render off the client-side cache.
        "className": "group-diskcount text-center",
        "data": null,
        "title": '<span title="Disk items in this pool by type: templates, desktops, media. Lazy-loaded; hover a value for its type, or the row for the total + size."><i class="fa fa-hdd-o"></i> Items <small class="text-muted">(T/D/M)</small></span>',
        "visible": false,
        "orderable": true,
        "width": "130px",
        "render": function (data, type, full, meta) {
          if (type === "sort" || type === "type") {
            var c = spDiskCounts[full.id];
            return c && typeof c.items_total === "number" ? c.items_total : -1;
          }
          return spDiskCountCell(full.id);
        }
      },
      // { 
      //   "data": "startable",
      //   "title": "Startable",
      //   "render": function(data, type, full, meta) {
      //     return renderEnabled(full.startable, 'circle');
      //   }
      // },
      // { 
      //   "data": "read", 
      //   "title": "Read",
      //   "render": function(data, type, full, meta) {
      //     return renderEnabled(full.read, 'circle');
      //   }
      // },
      // { 
      //   "data": "write", 
      //   "title": "Write",
      //   "render": function(data, type, full, meta) {
      //     return renderEnabled(full.write, 'circle');
      //   }
      // },
      {
        className: "actions-control",
        orderable: false,
        width: '125px',
        data: null,
        title: "Action",
        render: function (data, type, full, meta) {
          if (data.is_default) {
            return `<button id="btn-edit" class="btn btn-xs" type="button" data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>
                    <button id="btn-qos" class="btn btn-xs" type="button" data-placement="top" ><i class="fa fa-road" style="color:darkblue"></i></button>`
          } else {
            return data.enabled ?
              `<!--'<button id="btn-allowed" class="btn btn-xs" type="button" data-placement="top" ><i class="fa fa-users" style="color:darkblue"></i></button>--> \
                  <button id="btn-edit" class="btn btn-xs" type="button" data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button> \
                  <button id="btn-enable" class="btn btn-xs" type="button" data-placement="top" title="Enable storage pool"><i class="fa fa-power-off" style="color:darkgreen"></i></button>
                  <button id="btn-enable-virt" class="btn btn-xs" type="button" data-placement="top" title="Enable virtualization"><i class="fa fa-rocket" style="color:darkgreen"></i></button>
                  <button id="btn-qos" class="btn btn-xs" type="button" data-placement="top" ><i class="fa fa-road" style="color:darkblue"></i></button>`
              :
              `<!--'<button id="btn-allowed" class="btn btn-xs" type="button" data-placement="top" ><i class="fa fa-users" style="color:darkblue"></i></button>--> \
                  <button id="btn-edit" class="btn btn-xs" type="button" data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button> \
                  <button id="btn-enable" class="btn btn-xs" type="button" data-placement="top" title="Enable storage pool"><i class="fa fa-power-off" style="color:darkgreen"></i></button> \
                  <button id="btn-delete" class="btn btn-xs" type="button" data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>
                  <button id="btn-qos" class="btn btn-xs" type="button" data-placement="top" ><i class="fa fa-road" style="color:darkblue"></i></button>`
          }
        }
      },
    ],
  })

  // Column customiser (show/hide, incl. the lazy "Disk items" column) + a
  // Refresh button to re-gather the cached counts. Standalone Buttons container
  // appended above the table (same pattern as the hypervisors panel).
  new $.fn.dataTable.Buttons(storage_pools_table, {
    buttons: [
      {
        extend: 'colvis',
        text: '<i class="fa fa-columns"></i> Columns',
        titleAttr: 'Show or hide columns',
        columns: ':not(.details-control):not(.actions-control)'
      },
      {
        text: '<i class="fa fa-refresh"></i> Refresh disk counts',
        titleAttr: 'Re-fetch the per-pool disk-item counts (otherwise cached in this browser)',
        className: 'btn-sp-refresh-counts',
        action: function () { spLoadDiskCounts(true); }
      }
    ]
  }).container().appendTo($('.sp-buttons-row'));

  // Lazy-load the counts the first time the "Disk items" column is shown, and
  // remember the choice so a reload restores it (re-triggering the fetch).
  storage_pools_table.on('column-visibility.dt', function (e, settings, colIdx, visible) {
    var col = storage_pools_table.column(colIdx);
    if ($(col.header()).hasClass('group-diskcount')) {
      try { localStorage.setItem(SP_DISKCOL_VIS_LS, visible ? '1' : '0'); } catch (err) { /* ignore */ }
      if (visible) spLoadDiskCounts(false);
    }
  });
  // Restore the last visibility once the rows are in (fires the handler above).
  storage_pools_table.on('init.dt', function () {
    if (localStorage.getItem(SP_DISKCOL_VIS_LS) === '1') {
      storage_pools_table.column('.group-diskcount').visible(true);
    }
  });

  $('.btn-add-new').on('click', function () {
    $("#modalAddStoragePool #modalAdd")[0].reset();
    $("#modalAddStoragePool #category").select2({
      dropdownParent: $("#modalAddStoragePool"),
    });
    populateCategory("#modalAddStoragePool", null);
    populateQosDisk("#modalAddStoragePool", null);
    addPath("#modalAddStoragePool .path_base_mountpoint", "");

    addDefaultCheckboxListeners("#modalAdd", $("#modalAdd .checkbox .default-cb"));
    $("#modalAdd .checkbox .default-cb").trigger("ifUnchecked");
    $(`#modalAdd .table-wrapper input`).attr("disabled", false);

    $("#modalAddStoragePool").modal({
      backdrop: "static",
      keyboard: false,
    }).modal("show");
    $("#modalAddStoragePool #modalAdd").parsley();
  });

  $('#storage_pools tbody').on('click', 'button', function (e) {
    tr = $(this).closest("tr");
    data = storage_pools_table.row($(this).parents('tr')).data();
    row = storage_pools_table.row(tr)
    switch ($(this).attr('id')) {
      case 'btn-details':
        if (row.child.isShown()) {
          row.child.hide();
          tr.removeClass('shown');
        } else {
          storage_pools_table.rows('.shown').every(function () {
            this.child.hide();
            $(this.node()).removeClass('shown');
          });
          tr.addClass('shown');
          row.child(renderStoragePoolsPaths(row.data())).show();
        }
        break;
      case 'btn-allowed':
        modalAllowedsFormShow("storage_pool", data);
        break;
      case 'btn-qos':
        let modal = "#modalQoSStoragePool";
        populateQosDisk(modal, data.qos_disk_id);
        $(modal + " #id").val(data.id);
        $(modal).modal({
          backdrop: "static",
          keyboard: false,
        }).modal("show");
        break;

      case 'btn-edit':
        var isDefault = isDefaultPool(data.id);
        if (isDefault) {
          new PNotify({
            title: "ERROR editing pool",
            text: "Default pool can't be edited",
            hide: true,
            delay: 3000,
            icon: 'fa fa-warning',
            opacity: 1,
            type: 'error'
          });
        return;
        }

        $("#modalEditStoragePool #modalEdit #category").attr("disabled", isDefault);
        $("#modalEditStoragePool #modalEdit #name").attr("disabled", isDefault);
        $("#modalEditStoragePool #modalEdit #description").attr("disabled", isDefault);
        $("#modalEditStoragePool #modalEdit #mountpoint").attr("disabled", isDefault);

        $("#modalEditStoragePool #modalEdit")[0].reset();
        $('#modalEdit #pathsTableEdit tbody').html('');
        $("#modalEditStoragePool #category").select2({
          dropdownParent: $("#modalEditStoragePool"),
        });
        populateCategory("#modalEditStoragePool", data.categories);

        $("#modalEditStoragePool").modal({
          backdrop: "static",
          keyboard: false,
        }).modal("show");
        $("#modalEditStoragePool #modalEdit").parsley();
        $("#modalEdit #id").val(data.id);
        $("#modalEdit #name").val(data.name);
        $("#modalEdit #description").val(data.description);

          var fullMountpoint = data.mountpoint.split("/");
          var mountpointVar = fullMountpoint.pop();

          $("#modalEdit .path_base_mountpoint").text(fullMountpoint.join("/") + "/")

          $("#modalEdit #mountpoint").val(mountpointVar);
          $('#modalEdit #startable').iCheck(data.startable ? 'check' : 'uncheck').iCheck('update');
          $('#modalEdit #read').iCheck(data.read ? 'check' : 'uncheck').iCheck('update');
          $('#modalEdit #write').iCheck(data.write ? 'check' : 'uncheck').iCheck('update');

          const pathsTableEdit = $('#modalEdit #pathsTableEdit tbody')[0];
          paths = data.paths;

          for (const type in paths) {
            title = `<i class="fa ${getTypeDefaultValue(type).icon} fa-1x"></i><b id="${type}"> ${getTypeDefaultValue(type).title}</b>`;
            const pathArray = paths[type];
            if (pathArray.length == 0) {
              var row = renderNewRow(type, null) + `<tr><td colspan="100%" style="border-top: 3px solid rgb(221, 221, 221);"></td></tr>`;
              $('#modalEdit #pathsTableEdit tbody').append(row);
              addDefaultCheckboxListeners("#modalEdit", $('#modalEdit #' + type + ' .default-cb'));
              $('#modalEdit #' + type + ' .default-cb').iCheck('check').iCheck('update').trigger('ifChecked');
            }

            for (let i = 0; i < pathArray.length; i++) {
              const pathObj = pathArray[i];
              const row = pathsTableEdit.insertRow();
              row.setAttribute('id', type);

              const checkboxCell = row.insertCell(0);
              const typeCell = row.insertCell(1);
              typeCell.setAttribute('id', 'type');
              const pathCell = row.insertCell(2);
              const weightCell = row.insertCell(3);
              const buttonAddDelCell = row.insertCell(4);
              checkboxCell.innerHTML = "";
              if (i == 0) {
                checkboxCell.innerHTML = `<div class="checkbox"><label class="">
                                            <div class="icheckbox_flat-green" style="position: relative;">
                                              <input type="checkbox" name="default-${type}" data-type="${type}" class="flat default-cb" style="position: absolute; opacity: 0;">
                                              <ins class="iCheck-helper"
                                                style="position: absolute; top: 0%; left: 0%; display: block; width: 100%; height: 100%; margin: 0px; padding: 0px; background: rgb(255, 255, 255); border: 0px; opacity: 0;">
                                              </ins>
                                            </div>
                                          </label>
                                        </div>`
                addDefaultCheckboxListeners("#modalEdit", $(checkboxCell).find("input"));
              }
              pathText = "";
              if (isDefault) {
                pathText = pathObj.path.split(getTypeDefaultValue(type).path + "/")[1];
                pathText = pathText ? pathText : "";

              } else {
                pathText = pathObj.path;
              }
              typeCell.innerHTML = title;
              pathCell.innerHTML = `<span class="path_base"></span><input id="path" name="${type}-path" class="roundbox" pattern="^(\\{category\\}|[\\-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇa-zA-Z0-9]+)(/(\\{category\\}|[\\-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇa-zA-Z0-9]+))*$" data-parsley-trigger="change" type="text" value="${pathText}">`;
              weightCell.innerHTML = `<input id="weight" name="${type}-weight" type="number" value="${pathObj.weight}">`;
              buttonAddDelCell.innerHTML = `<input id='modalEdit-addrow-${type}' type='button' value='+' onclick='addRow("${type}", "modalEdit", ${isDefault})'/> \
                                          <input class='modalEdit-delrow-${type}' type='button' value='-' onclick='delRow("${type}", "modalEdit")'/>`;

              if (i === pathArray.length - 1) {
                const additionalRow = pathsTableEdit.insertRow();
                const additionalCell = additionalRow.insertCell();
                additionalCell.setAttribute('colspan', '100%');
                additionalCell.style.borderTop = '3px solid rgb(221, 221, 221)';
              }
            }

          if (isDefault) {
            $("#modalEdit #category").attr("disabled", true);
            $("#modalEditStoragePool #modalEdit .checkbox").remove();
            $.each($("#modalEdit #pathsTableEdit tr input"), function () {
              if ($(this).attr("name")) {
                var type = $(this).attr("name").split("-")[0];
                $(this).siblings("span").text(getTypeDefaultValue(type).path);
                if ($(this).val().length == 0) {
                  $(this).remove();
                } else {
                  $(this).siblings("span").text(getTypeDefaultValue(type).path + "/");
                }
              }
            });
          } else {
            $("#modalEdit #category").attr("disabled", false);
          }
        }
        break;
      case 'btn-enable':
        var change = data["enabled"] ? "disable" : "enable";

        let prompt_msg = (change == "enable") ?
          "From now on, disks from this pool's categories will be created in the new paths defined"
          :
          "From now on, disks from this pool's categories will be created in default paths";

        let msg = (change == "enable") ?
          "This pool <b>only becomes operational</b> after a hypervisor/storage node that serves it is restarted (each node reads the pools it serves at startup). Ensure at least one hypervisor is associated with this storage pool. Editing an existing pool's paths or mountpoints takes effect automatically, with no restart."
          :
          "";

        new PNotify({
          title: "<b>WARNING</b>",
          type: "error",
          text: "Are you sure you want to <b>" + change + "</b> pool " + data["name"] + "? " + prompt_msg,
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
          addclass: 'pnotify-center-large',
          width: '550'
        }).get().on('pnotify.confirm', function () {
          $.ajax({
            type: "PUT",
            url: "/api/v4/storage-pool/" + data["id"],
            data: JSON.stringify({ 'name': data["name"], 'enabled': !data.enabled }),
            contentType: "application/json",
            success: function (data) {
              new PNotify({
                title: 'Pool ' + change + 'd successfully',
                text: msg,
                hide: true,
                delay: 7000,
                icon: 'fa fa-' + data?.icon,
                opacity: 1,
                type: change == "enable" ? 'warning' : 'success'
              });
              showPoolWarnings(data);
              storage_pools_table.ajax.reload();
            },
            error: function (xhr, ajaxOptions, thrownError) {
              new PNotify({
                title: "ERROR updating pool",
                text: xhr.responseJSON ? xhr.responseJSON.description : "Something went wrong",
                hide: true,
                delay: 3000,
                icon: 'fa fa-warning',
                opacity: 1,
                type: 'error'
              });
            }
          });
        }).on('pnotify.cancel', function () { });
        break;
      case 'btn-enable-virt':
        var change = data["enabled_virt"] ? "disable" : "enable";
        new PNotify({
          title: "<b>WARNING</b>",
          type: "error",
          text: "Are you sure you want to <b>" + change + "</b> pool " + data["name"] + "'s virtualization?",
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
          addclass: 'pnotify-center-large',
          width: '550'
        }).get().on('pnotify.confirm', function () {
          $.ajax({
            type: "PUT",
            url: "/api/v4/storage-pool/" + data["id"],
            data: JSON.stringify({ 'enabled_virt': !data.enabled_virt }),
            contentType: "application/json",
            success: function (data) {
              new PNotify({
                title: 'Virtualization ' + change + 'd successfully',
                text: '',
                hide: true,
                delay: 7000,
                icon: 'fa fa-' + data?.icon,
                opacity: 1,
                type: 'success'
              });
              storage_pools_table.ajax.reload();
            },
            error: function (xhr, ajaxOptions, thrownError) {
              new PNotify({
                title: "ERROR updating virtualization on storage pool",
                text: xhr.responseJSON ? xhr.responseJSON.description : "Something went wrong",
                hide: true,
                delay: 3000,
                icon: 'fa fa-warning',
                opacity: 1,
                type: 'error'
              });
            }
          });
        }).on('pnotify.cancel', function () { });
        break;
      case 'btn-delete':
        isDefault = isDefaultPool(data.id);
        if (isDefault) {
          return new PNotify({
            title: "ERROR deleting pool",
            text: "Default pool can't be removed",
            hide: true,
            delay: 3000,
            icon: 'fa fa-warning',
            opacity: 1,
            type: 'error'
          });
        }
        new PNotify({
          title: "<b>WARNING</b>",
          type: "error",
          text: `Are you sure you want to <b>delete</b> pool ${data["name"]}?
                \nNote: Deleting a pool only fully takes effect after the hypervisor/storage nodes that served it are <strong>restarted</strong> (they stop serving its queue at startup).`,
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
            url: "/api/v4/storage-pool/" + data["id"],
            contentType: "application/json",
            success: function (data) {
              new PNotify({
                title: 'Deleted',
                text: 'Pool deleted successfully',
                hide: true,
                delay: 1000,
                icon: 'fa fa-' + data?.icon,
                opacity: 1,
                type: 'success'
              })
              storage_pools_table.ajax.reload();
            },
            error: function (xhr, ajaxOptions, thrownError) {
              new PNotify({
                title: "ERROR deleting pool",
                text: xhr.responseJSON.description,
                hide: true,
                delay: 3000,
                icon: 'fa fa-warning',
                opacity: 1,
                type: 'error'
              });
            }
          });
        }).on("pnotify.cancel", function () { });
        break;
    }
  });

  $.getScript("/isard-admin/static/admin/js/socketio.js");
})

function renderEnabled(enabled, kind) {
  let icon = kind == 'check' ? 'check' : 'circle'
  let color = enabled ? 'green' : 'darkgray'
  return '<i class="fa fa-' + icon + '" style="color:' + color + '"></i>'
}

function storagePoolOnDiskPath(mountpoint, category, subpath) {
  // Mirror build_category_pool_dir: with the {category} token present the token
  // is substituted in place and the category is NOT auto-prepended; without it
  // the category id is inserted after the mountpoint; the default pool (no
  // category) uses the subpath as-is.
  var token = "{category}";
  if (category && subpath.indexOf(token) !== -1) {
    return `${mountpoint}/${subpath.split(token).join(category["id"])}`;
  }
  if (category) {
    return `${mountpoint}/${category["id"]}/${subpath}`;
  }
  return `${mountpoint}/${subpath}`;
}

function renderStoragePoolsPaths(data) {
  var $newPanel = "";
  if (data["categories_names"].length) {
    $.each(data["categories_names"], function (index, category) {
      $panel = $(".template-storage_pools-detail").clone();
      $panel.find(".x_title h3").text(category["name"] + " paths");
      $pathsTBody = $panel.find("tbody");
      $pathsTBody.empty();
      $.each(data.paths, function (type, paths) {
        createDetailPanel(type, paths, category);
      });
      $newPanel.length ? $newPanel.find(".category-panel-container").append($panel.find(".detail-col")) : $newPanel = $panel;
    });
  } else {
    $panel = $(".template-storage_pools-detail").clone();
    $pathsTBody = $panel.find("tbody");
    $pathsTBody.empty();
    $.each(data.paths, function (type, paths) {
      createDetailPanel(type, paths, null);
    });
    $newPanel = $panel;
  }
  return $newPanel;

  function createDetailPanel(type, paths, category) {
    $.each(paths, function (index, path) {
      $pathsTBody.append(
        $('<tr>').append(
          $('<td>').append($('<i class="fa">').addClass(getTypeDefaultValue(type).icon)).append(' ').append(`<b> ${getTypeDefaultValue(type).title}</b>`),
          $('<td>').text(storagePoolOnDiskPath(data.mountpoint, category, path.path)),
          $('<td>').text(path.weight)
        )
      );
    });
  }
}

function addRow(type, modal, isDefault) {
  var currentRow = document.getElementById(`${modal}-addrow-${type}`).parentNode.parentNode;
  var newRow = document.createElement("tr");
  newRow.setAttribute("id", type)
  newRow.innerHTML = renderNewRow(type, isDefault);
  currentRow.parentNode.insertBefore(newRow, currentRow.nextSibling);
}

function delRow(type, modal) {
  currentRow = $(`.${modal}-delrow-${type}`).parent().parent().last();
  currentRow.remove();
}

// A pool's mountpoint is its on-disk identity: the backend resolves a disk path
// back to a pool by mountpoint, so two pools sharing one make that lookup
// ambiguous (the API rejects it with 400). Pre-check against the already-loaded
// pools so the admin gets immediate feedback instead of a round-trip. excludeId
// skips the pool itself when editing/renaming it.
function mountpointInUse(mountpoint, excludeId) {
  var clash = false;
  storage_pools_table.rows().every(function () {
    var row = this.data();
    if (row && row.mountpoint === mountpoint && row.id !== excludeId) {
      clash = true;
    }
  });
  return clash;
}

function notifyMountpointInUse(mountpoint) {
  new PNotify({
    title: "Mountpoint already in use",
    type: "error",
    text: `Another storage pool already uses the mountpoint <b>${mountpoint}</b>. Each storage pool must have a unique mountpoint.`,
    hide: false,
    opacity: 0.9,
    buttons: { closer: true, sticker: false },
    addclass: 'pnotify-center-large',
    width: '550'
  });
}

$("#modalAddStoragePool #send").off('click').on('click', function (e) {
  var form = $('#modalAdd');
  form.parsley().validate();
  if (form.parsley().isValid()) {
    data = form.serializeObject();
    // data['startable'] = 'startable' in data ? true : false;
    // data['read'] = 'read' in data ? true : false;
    // data['write'] = 'write' in data ? true : false;
    data["allowed"] = { "roles": false, "categories": false, "groups": false, "users": false }
    e.preventDefault();
    var pathsTableAdd = {};
    var isDefault = isDefaultPool(data.id);

    $('#pathsTableAdd tbody tr').each(function () {
      var type = $(this).attr("id");
      if (type) {
        var weight = parseInt($(this).find('#weight').val());
        var path = $(this).find('#path').val();
        if (!path) path = "";
        if (!pathsTableAdd[type]) {
          pathsTableAdd[type] = [];
        }
        if (isDefault) {
          path = (getTypeDefaultValue(type).path + "/" + path).replace(/\/$/, '')
        }
        if (data["default-" + type] != 'on') {
          pathsTableAdd[type].push({
            'path': path,
            'weight': weight
          });
        }
      }
    });

    for (let key in data) {
      if (key.endsWith("-weight") || key.endsWith("-path")) {
        delete data[key];
      }
    }

    data["paths"] = pathsTableAdd
    data["mountpoint"] = form.find(".path_base_mountpoint").text() + data.mountpoint

    if (mountpointInUse(data["mountpoint"], data.id)) {
      notifyMountpointInUse(data["mountpoint"]);
      return;
    }

    $.ajax({
      type: "POST",
      url: `/api/v4/storage-pool/check-category-availability`,
      data: JSON.stringify({ "categories": data.categories, "storage_pool_id": data.id }),
      contentType: "application/json",
      success: function (xhr) {
        if (xhr.available) {
          createStoragePool(data);
        } else {
          new PNotify({
            title: "Category in use",
            type: "warning",
            text: "One of the categories is in use by another pool. Proceeding will remove it from that pool. Do you want to continue?",
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
            addclass: 'pnotify-center-large',
            width: '550'
          }).get().on('pnotify.confirm', function () {
            createStoragePool(data);
          });
        }
      },
      error: function (xhr) {
        new PNotify({
          title: 'ERROR checking category availability',
          text: xhr.responseJSON ? xhr.responseJSON.description : "Something went wrong",
          type: 'error',
          hide: true,
          icon: 'fa fa-warning',
          delay: 2000,
          opacity: 1
        });
      }
    });
  }
});

$("#modalEditStoragePool #send").off('click').on('click', function (e) {
  var form = $('#modalEdit');
  form.parsley().validate();
  if (form.parsley().isValid()) {
    data = form.serializeObject();
    data['startable'] = 'startable' in data ? true : false;
    data['read'] = 'read' in data ? true : false;
    data['write'] = 'write' in data ? true : false;

    e.preventDefault();
    var pathsTableEdit = {};
    isDefault = isDefaultPool(data.id)
    $('#pathsTableEdit tbody tr').each(function () {
      if ($(this).attr("id") != undefined) {
        var type = $(this).attr("id");
        var weight = parseInt($(this).find('#weight').val());
        var path = $(this).find('#path').val();
        if (!path) path = "";
        if (!pathsTableEdit[type]) {
          pathsTableEdit[type] = [];
        }
        if (isDefault) {
          path = (getTypeDefaultValue(type).path + "/" + path).replace(/\/$/, '')
        }

        if (data["default-" + type] != 'on') {
          pathsTableEdit[type].push({
            'path': path,
            'weight': weight
          });
        }
      }
    });

    for (let key in data) {
      if (key.endsWith("-weight") || key.endsWith("-path")) {
        delete data[key];
      }
    }

    data["paths"] = pathsTableEdit
    data["mountpoint"] = form.find(".path_base_mountpoint").text() + data.mountpoint;
    data["categories"] = data["categories"] || [];

    if (mountpointInUse(data["mountpoint"], data.id)) {
      notifyMountpointInUse(data["mountpoint"]);
      return;
    }

    $.ajax({
      type: "POST",
      url: `/api/v4/storage-pool/check-category-availability`,
      data: JSON.stringify({ "categories": data.categories, "storage_pool_id": data.id }),
      contentType: "application/json",
      success: function (xhr) {
        if (xhr.available) {
          if (isDefault) {
            new PNotify({
              title: "WARNING. You're about to edit the default pool",
              type: "warning",
              text: "Editing the default pool settings may impact system operations. Are you sure you want to update?",
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
              addclass: 'pnotify-center-large',
              width: '550'
            }).get().on('pnotify.confirm', function () {
              updateStoragePool(data);
            });
          } else {
            updateStoragePool(data);
          }
        } else {
          new PNotify({
            title: "Category in use",
            type: "warning",
            text: "One of the categories is in use by another pool. Proceeding will remove it from that pool. Do you want to continue?",
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
            addclass: 'pnotify-center-large',
            width: '550'
          }).get().on('pnotify.confirm', function () {
            updateStoragePool(data);
          });
        }
      },
      error: function (xhr) {
        new PNotify({
          title: 'ERROR checking category availability',
          text: xhr.responseJSON ? xhr.responseJSON.description : "Something went wrong",
          type: 'error',
          hide: true,
          icon: 'fa fa-warning',
          delay: 2000,
          opacity: 1
        });
      }
    });
  }
});


$("#modalQoSStoragePool #send").off('click').on('click', function (e) {
  var form = $('#modalQoSStoragePool #modalQoS');
  data = form.serializeObject();
  data["id"] = form.find("#id").val();
  updateStoragePool(data);
});

function populateQosDisk(modal, qos_disk_id) {
  $(modal + " #qos_disk_id").empty();
  $(modal + ' #qos_disk_id').append(
    `<option value=null>Ignore</option>`
  );
  $.ajax({
    type: "GET",
    url: "/api/v4/admin/items/table/qos_disk",
    cache: false,
    success: function (qos_disk) {
      $.each(qos_disk, function (key, value) {
        $(modal + ' #qos_disk_id').append(
          `<option value="${value.id}">${value.name}</option>`
        );
      });
      if (qos_disk_id) {
        $(modal + " #qos_disk_id").val(qos_disk_id).trigger("change");
      }
    }
  });
}

function populateCategory(modal, category_id) {
  $(modal + " #category").empty();
  $.ajax({
    type: "GET",
    url: "/api/v4/admin/items/categories",
    cache: false,
    success: function (category) {
      $.each(category, function (key, value) {
        $(modal + ' #category').append(
          `<option value="${value.id}">${value.name}</option>`
        );
        $(modal + " #category").val(category_id).trigger("change");
      });
    }
  });
}

function updateStoragePool(data) {
  var notice = new PNotify({
    text: 'Updating pool...',
    hide: false,
    opacity: 1,
    icon: 'fa fa-spinner fa-pulse'
  })
  $.ajax({
    url: "/api/v4/storage-pool/" + data["id"],
    type: "PUT",
    data: JSON.stringify(data),
    contentType: "application/json",
    success: function (data) {
      notice.update({
        title: 'Updated',
        text: 'Pool updated successfully',
        hide: true,
        delay: 1000,
        icon: 'fa fa-' + data?.icon,
        opacity: 1,
        type: 'success'
      })
      $('form').each(function () { this.reset() });
      $('.modal').modal('hide');
      storage_pools_table.ajax.reload();
    },
    error: function (xhr) {
      notice.update({
        title: 'ERROR updating pool',
        text: xhr.responseJSON ? xhr.responseJSON.description : "Something went wrong",
        type: 'error',
        hide: true,
        icon: 'fa fa-warning',
        delay: 2000,
        opacity: 1
      })
    }
  });
}

function createStoragePool(data) {
  var notice = new PNotify({
    text: "Creating pool...",
    hide: false,
    opacity: 1,
    icon: "fa fa-spinner fa-pulse",
  });
  $.ajax({
    url: "/api/v4/storage-pool",
    type: "POST",
    data: JSON.stringify(data),
    contentType: "application/json",
    success: function (data) {
      notice.update({
        title: "Created",
        text: "Pool created successfully",
        hide: true,
        delay: 1000,
        icon: "fa fa-" + data?.icon,
        opacity: 1,
        type: "success",
      });
      $("form").each(function () {
        this.reset();
      });
      $(".modal").modal("hide");
      showPoolWarnings(data);
      storage_pools_table.ajax.reload();
    },
    error: function (xhr) {
      notice.update({
        title: "ERROR creating pool",
        text: xhr.responseJSON ? xhr.responseJSON.description : "Something went wrong",
        type: "error",
        hide: true,
        icon: "fa fa-warning",
        delay: 2000,
        opacity: 1,
      });
    },
  });
}

function showPoolWarnings(resp) {
  // Surface the non-blocking advisories a storage-pool create/update returns
  // (e.g. on disable: residing disks + queued tasks that keep draining; on
  // create/category-assign: no node serves the pool yet). Sticky so the admin
  // reads the pending/coverage note.
  ((resp && resp.warnings) || []).forEach(function (w) {
    new PNotify({
      title: "Storage pool notice",
      text: w.message,
      hide: false,
      icon: "fa fa-info-circle",
      opacity: 1,
      type: "warning",
      addclass: "pnotify-center-large",
      width: "550",
    });
  });
}

function checkStorageLaneHealth() {
  // Orphan-lane detector: warn if a storage queue holds jobs with no worker
  // consuming them, so its tasks stall until a node serving that pool starts.
  $.ajax({
    type: "GET",
    url: "/api/v4/admin/items/queues/lane-health",
    success: function (data) {
      if (data && data.healthy === false && (data.orphan_pools || []).length) {
        new PNotify({
          title: "<b>Storage lanes stalled</b>",
          text:
            "Queued storage tasks have no consumer for pool(s): <b>" +
            data.orphan_pools.join(", ") +
            "</b>. They will stall until a storage/hypervisor node with these " +
            "pools in its CAPABILITIES_STORAGE_POOLS is running.",
          hide: false,
          icon: "fa fa-warning",
          opacity: 1,
          type: "error",
          addclass: "pnotify-center-large",
          width: "550",
        });
      }
    },
  });
}

function addPath(path, mountpoint) {
  $(path).empty();
  $.each($(path), function () {
    $(this).text(`/isard/storage_pools/${mountpoint ? mountpoint : ""}`);
  });
}

function addDefaultCheckboxListeners(modal, checkbox) {
  $(checkbox).parent().show();
  $(checkbox).iCheck({
    checkboxClass: 'icheckbox_flat-green',
  });
  $(checkbox).attr("disabled", false);
  checkbox.on('ifChecked', function () {
    $(modal + ` .table-wrapper tr#${$(this).data("type")} input`).attr("disabled", true)
    $($(this)).attr("disabled", false);
  })
  checkbox.on('ifUnchecked', function () {
    $(modal + ` .table-wrapper tr#${$(this).data("type")} input`).attr("disabled", false);
  })
}

function getTypeDefaultValue(type) {
  const valueMap = {
    "desktop": {
      "path": "desktops",
      "icon": "fa-desktop",
      "title": "Desktop"
    },
    "media": {
      "path": "media",
      "icon": "fa-circle-o",
      "title": "Media"
    },
    "template": {
      "path": "templates",
      "icon": "fa-cubes",
      "title": "Template"
    },
    "volatile": {
      "path": "volatile",
      "icon": "fa-clock-o",
      "title": "Volatile"
    }
  };
  return valueMap[type];
}

function renderNewRow(type, defaultPool) {
  const typeData = getTypeDefaultValue(type);
  return `<tr id="${type}">
    <td>
          <div class="icheckbox_flat-green" style="position:relative;display:none;">
            <input type="checkbox" name="default-${type}" data-type="${type}" class="flat default-cb" style="position: absolute; opacity: 0;">
          </div>
        </label>
      </div>
    </td>
    <td id="type"><i class="fa ${typeData.icon} fa-1x"></i><b> ${typeData.title}</b></td>
    <td>
      <span class="path_base">${defaultPool ? typeData.path + "/" : ""}</span><input id="path" name="${type}-path" value="${typeData.path}" class="roundbox" required pattern="^(\\{category\\}|[\\-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇa-zA-Z0-9]+)(/(\\{category\\}|[\\-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇa-zA-Z0-9]+))*$" data-parsley-trigger="change" type="text">
    </td>
    <td><input id="weight" name="${type}-weight" type="number" value="100"></td>
    <td>
      <input id="modalAdd-addrow-${type}" type="button" value="+" onclick="addRow('${type}', 'modalAdd', ${defaultPool})"/>
      <input class="modalAdd-delrow-${type}" type="button" value="-" onclick="delRow('${type}', 'modalAdd')"/>
    </td>
  </tr>`
}

function isDefaultPool(poolId) {
  return poolId == DEFAULT_STORAGE_POOL_ID;
}