/*
 *   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
 *   Copyright (C) 2026 IsardVDI
 *
 *   This program is free software: you can redistribute it and/or modify
 *   it under the terms of the GNU Affero General Public License as published by
 *   the Free Software Foundation, either version 3 of the License, or
 *   (at your option) any later version.
 *
 *   This program is distributed in the hope that it will be useful, but WITHOUT
 *   ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 *   FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License.
 *
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

// Minimal admin view for the storage-disk path->path migration (I+D #1924).
// One row per ROOT tree with %/count moved + start/pause/cancel, kept live by
// the aggregate `storage:migration` SocketIO event the change-handler emits.

const MIG_API = "/api/v4";

function migEscape (s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function migProgress (tree) {
  const total = tree.items_total || 0;
  const done = (typeof tree.done === "number") ? tree.done : 0;
  const pct = total ? Math.round((done / total) * 100) : 0;
  return `${done}/${total} (${pct}%)`;
}

function migActionButtons (m) {
  const terminal = ["completed", "failed", "canceled"].indexOf(m.status) !== -1;
  if (terminal) return migEscape(m.status);
  return `
    <button class="btn btn-xs btn-success mig-action" data-mig="${migEscape(m.id)}" data-action="start">Start</button>
    <button class="btn btn-xs btn-warning mig-action" data-mig="${migEscape(m.id)}" data-action="pause">Pause</button>
    <button class="btn btn-xs btn-danger mig-action" data-mig="${migEscape(m.id)}" data-action="cancel">Cancel</button>`;
}

// Render (or re-render) every root-tree row for one migration. `m` is the
// aggregate shape shared by the status endpoint and the socket event:
// {id, status, totals, trees:[{tree_id, derivative_templates, desktops, ...}]}
function renderMigration (m) {
  $(`#migrations tbody tr[data-mig="${m.id}"]`).remove();
  const trees = (m.trees && m.trees.length) ? m.trees : [{ tree_id: "(no trees)", items_total: 0 }];
  trees.forEach(function (tree, idx) {
    const first = idx === 0;
    const row = `<tr data-mig="${migEscape(m.id)}">
      <td>${first ? migEscape(m.id) : ""}</td>
      <td>${first ? migEscape(m.status) : ""}</td>
      <td>${migEscape(tree.root_storage_id || tree.tree_id)}</td>
      <td>${migEscape(tree.derivative_templates || 0)}</td>
      <td>${migEscape(tree.desktops || 0)}</td>
      <td>${migProgress(tree)}</td>
      <td>${first ? migActionButtons(m) : ""}</td>
    </tr>`;
    $("#migrations tbody").append(row);
  });
}

function loadMigrations () {
  $.ajax({ type: "GET", url: `${MIG_API}/storage/migrations` }).done(function (data) {
    $("#migrations tbody").empty();
    (data.migrations || []).forEach(function (mig) {
      // The list lacks per-tree rows; fetch the status (with trees) per job.
      $.ajax({ type: "GET", url: `${MIG_API}/storage/migrations/${mig.id}` })
        .done(renderMigration)
        .fail(function () { renderMigration(mig); });
    });
  });
}

function loadMigrationPools () {
  $.ajax({ type: "GET", url: `${MIG_API}/storage-pools` }).done(function (data) {
    const rows = (data && data.data) ? data.data : (Array.isArray(data) ? data : []);
    const opts = rows.map(function (p) {
      return `<option value="${migEscape(p.id)}">${migEscape(p.name || p.id)}</option>`;
    }).join("");
    $("#mig_src_pool, #mig_dst_pool").html(opts);
  });
}

function migSelection () {
  return {
    kind: "pool",
    src_pool_id: $("#mig_src_pool").val(),
    dst_pool_id: $("#mig_dst_pool").val()
  };
}

function connection_done () { loadMigrations(); }
function connection_lost () { }

function socketio_on () {
  socket.on("storage:migration", function (raw) {
    let m;
    try { m = (typeof raw === "string") ? JSON.parse(raw) : raw; } catch (e) { return; }
    if (m && m.id) renderMigration(m);
  });
}

$(document).ready(function () {
  loadMigrationPools();
  loadMigrations();

  $("#mig_preview").on("click", function () {
    $("#mig_preview_out").text("Building plan…");
    $.ajax({
      type: "POST", url: `${MIG_API}/storage/migrations/plan`,
      contentType: "application/json",
      data: JSON.stringify({ selection: migSelection() })
    }).done(function (plan) {
      const t = plan.totals || {};
      $("#mig_preview_out").text(
        `${(plan.trees || []).length} trees · ${t.items_total || 0} disks · ${t.bytes_total || 0} bytes`
      );
    }).fail(function (xhr) {
      $("#mig_preview_out").text("Plan failed: " + (xhr.responseJSON && xhr.responseJSON.description || xhr.status));
    });
  });

  $("#mig_create").on("click", function () {
    const body = {
      selection: migSelection(),
      config: { force_stop_desktops: $("#mig_force_stop").is(":checked"), verify: true }
    };
    $.ajax({
      type: "POST", url: `${MIG_API}/storage/migrations`,
      contentType: "application/json", data: JSON.stringify(body)
    }).done(function (mig) {
      $.ajax({ type: "POST", url: `${MIG_API}/storage/migrations/${mig.id}/start` })
        .always(loadMigrations);
    }).fail(function (xhr) {
      $("#mig_preview_out").text("Create failed: " + (xhr.responseJSON && xhr.responseJSON.description || xhr.status));
    });
  });

  $("#migrations").on("click", ".mig-action", function () {
    const id = $(this).data("mig");
    const action = $(this).data("action");
    $.ajax({ type: "POST", url: `${MIG_API}/storage/migrations/${id}/${action}` })
      .always(loadMigrations);
  });

  // Load the shared /administrators SocketIO connector; it calls
  // connection_done() on connect and we bind our handler in socketio_on().
  $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on);
});
