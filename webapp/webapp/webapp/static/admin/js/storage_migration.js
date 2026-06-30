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

// Admin view for the storage-disk path->path migration (I+D #1924): totals
// cards, aggregate progress + ETA, per-tree and per-disk expand, and the
// window / parallelism / bwlimit / force-stop controls. Kept live by the
// aggregate `storage:migration` SocketIO event the change-handler emits.

const MIG_API = "/api/v4/admin/storage/migrations";
const POOLS_API = "/api/v4/storage-pools";
const MIG_TERMINAL = ["completed", "failed", "canceled"];

// migrations expanded in the table (preserved across re-render)
const migExpanded = {};

function migEscape (s) {
  return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function migBytes (n) {
  n = Number(n) || 0;
  const u = ["B", "KB", "MB", "GB", "TB", "PB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (i === 0 ? n : n.toFixed(1)) + " " + u[i];
}

function migEta (secs) {
  if (secs == null) return "—";
  secs = Math.max(0, Math.round(secs));
  if (secs < 60) return secs + "s";
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  return (h ? h + "h " : "") + m + "m";
}

function migWindowLabel (m) {
  const w = m.current_window;
  if (!w || !w.has_window) return "always";
  if (!w.open) return "closed";
  return "open · " + migEta(w.remaining_seconds) + " left";
}

function migBar (done, total, bytesDone, bytesTotal) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  const bpct = bytesTotal ? Math.round((bytesDone / bytesTotal) * 100) : 0;
  return `<div class="progress" style="margin:0;min-width:140px;height:16px;" title="${migBytes(bytesDone)} / ${migBytes(bytesTotal)}">
      <div class="progress-bar progress-bar-success" style="width:${bpct}%;line-height:16px;">${done}/${total} (${pct}%)</div>
    </div>`;
}

function migActionButtons (m) {
  if (MIG_TERMINAL.indexOf(m.status) !== -1) return migEscape(m.status);
  return `
    <button class="btn btn-xs btn-success mig-action" data-mig="${migEscape(m.id)}" data-action="start">Start</button>
    <button class="btn btn-xs btn-warning mig-action" data-mig="${migEscape(m.id)}" data-action="pause">Pause</button>
    <button class="btn btn-xs btn-danger mig-action" data-mig="${migEscape(m.id)}" data-action="cancel">Cancel</button>`;
}

function migCard (label, value) {
  return `<div style="display:inline-block;min-width:110px;margin:0 14px 8px 0;">
      <div style="font-size:20px;font-weight:600;">${migEscape(value)}</div>
      <div style="color:#888;font-size:12px;">${migEscape(label)}</div>
    </div>`;
}

// Config controls (window / parallelism / bwlimit / force-stop) for one job.
function migConfigControls (m) {
  const c = m.config || {};
  const w = c.window || {};
  const dis = MIG_TERMINAL.indexOf(m.status) !== -1 ? "disabled" : "";
  return `<form class="form-inline mig-config" data-mig="${migEscape(m.id)}" style="margin:8px 0;">
      <label>Window
        <input type="text" class="form-control input-sm cfg-win-start" placeholder="HH:MM" style="width:62px;" value="${migEscape(w.start || "")}" ${dis}>
        &ndash;
        <input type="text" class="form-control input-sm cfg-win-end" placeholder="HH:MM" style="width:62px;" value="${migEscape(w.end || "")}" ${dis}>
      </label>
      <label style="margin-left:8px;">Parallel
        <input type="number" class="form-control input-sm cfg-parallel" min="1" style="width:58px;" value="${migEscape(c.parallelism != null ? c.parallelism : 1)}" ${dis}>
      </label>
      <label style="margin-left:8px;">bwlimit&nbsp;KB/s
        <input type="number" class="form-control input-sm cfg-bwlimit" min="0" style="width:84px;" value="${migEscape(c.bwlimit_kbs != null ? c.bwlimit_kbs : 0)}" ${dis}>
      </label>
      <label style="margin-left:8px;"><input type="checkbox" class="cfg-force" ${c.force_stop_desktops ? "checked" : ""} ${dis}> force-stop</label>
      <label style="margin-left:8px;"><input type="checkbox" class="cfg-verify" ${c.verify === false ? "" : "checked"} ${dis}> verify</label>
      <button type="button" class="btn btn-default btn-xs mig-config-apply" style="margin-left:8px;" ${dis}>Apply</button>
      <span class="mig-config-out" style="margin-left:8px;color:#888;"></span>
    </form>`;
}

function migTreeRows (m) {
  let html = `<table class="table table-condensed" style="margin:6px 0;background:#fafafa;">
    <thead><tr><th style="width:18px;"></th><th>Root tree</th><th>Derivative templates</th>
      <th>Desktops</th><th>Progress</th></tr></thead><tbody>`;
  (m.trees || []).forEach(function (t) {
    html += `<tr class="mig-tree" data-mig="${migEscape(m.id)}" data-tree="${migEscape(t.tree_id)}" style="cursor:pointer;">
        <td><i class="fa fa-caret-right"></i></td>
        <td>${migEscape(t.root_storage_id || t.tree_id)}</td>
        <td>${migEscape(t.derivative_templates || 0)}</td>
        <td>${migEscape(t.desktops || 0)}</td>
        <td>${migBar(t.done || 0, t.items_total || 0, t.bytes_done || 0, t.bytes_total || 0)}</td>
      </tr>`;
  });
  html += "</tbody></table>";
  return html;
}

// Detail row: totals cards + config controls + per-tree table.
function migDetail (m) {
  const t = m.totals || {};
  const cards =
    migCard("trees", t.trees || (m.trees || []).length) +
    migCard("derivative templates", t.derivative_templates || 0) +
    migCard("desktops", t.desktops || 0) +
    migCard("disks", t.items_total || 0) +
    migCard("bytes", migBytes(t.bytes_total || 0)) +
    migCard("ETA", migEta(m.eta_seconds));
  return `<tr class="mig-detail" data-mig="${migEscape(m.id)}"><td></td><td colspan="6">
      <div style="margin-bottom:6px;">${cards}</div>
      ${migConfigControls(m)}
      ${migTreeRows(m)}
    </td></tr>`;
}

function migRowHtml (m) {
  const t = m.totals || {};
  const open = migExpanded[m.id];
  let html = `<tr class="mig-row" data-mig="${migEscape(m.id)}" style="cursor:pointer;">
      <td><i class="fa fa-caret-${open ? "down" : "right"}"></i></td>
      <td>${migEscape(m.id)}</td>
      <td>${migEscape(m.status)}</td>
      <td>${migBar(t.done || 0, t.items_total || 0, t.bytes_done || 0, t.bytes_total || 0)}</td>
      <td>${migEta(m.eta_seconds)}</td>
      <td>${migEscape(migWindowLabel(m))}</td>
      <td onclick="event.stopPropagation();">${migActionButtons(m)}</td>
    </tr>`;
  if (open) html += migDetail(m);
  return html;
}

// Render/replace one migration's row(s) (the aggregate shape is shared by the
// status endpoint and the socket event).
function renderMigration (m) {
  if (!m || !m.id) return;
  const $existing = $(`#migrations tbody tr[data-mig="${m.id}"]`);
  const $html = $(migRowHtml(m));
  if ($existing.length) $existing.first().replaceWith($html.first());
  else $("#migrations tbody").append($html.first());
  // detail row (only when expanded)
  $(`#migrations tbody tr.mig-detail[data-mig="${m.id}"]`).remove();
  if (migExpanded[m.id]) $(`#migrations tbody tr.mig-row[data-mig="${m.id}"]`).after($html.filter(".mig-detail"));
}

function loadMigration (id) {
  return $.ajax({ type: "GET", url: `${MIG_API}/${id}` }).done(renderMigration);
}

function loadMigrations () {
  $.ajax({ type: "GET", url: MIG_API }).done(function (data) {
    $("#migrations tbody").empty();
    (data.migrations || []).forEach(function (mig) {
      loadMigration(mig.id).fail(function () { renderMigration(mig); });
    });
  });
}

function loadMigrationPools () {
  $.ajax({ type: "GET", url: POOLS_API }).done(function (data) {
    const rows = data.storage_pools || data.data || (Array.isArray(data) ? data : []);
    const opts = rows.map(function (p) {
      return `<option value="${migEscape(p.id)}">${migEscape(p.name || p.id)}</option>`;
    }).join("");
    $("#mig_src_pool, #mig_dst_pool").html(opts);
  });
}

function migSelection () {
  return { kind: "pool", src_pool_id: $("#mig_src_pool").val(), dst_pool_id: $("#mig_dst_pool").val() };
}

function migWindowFrom (start, end) {
  start = (start || "").trim();
  end = (end || "").trim();
  return (start && end) ? { start: start, end: end, tz: "UTC" } : null;
}

function migCreateConfig () {
  return {
    bwlimit_kbs: parseInt($("#mig_bwlimit").val(), 10) || 0,
    parallelism: parseInt($("#mig_parallel").val(), 10) || 1,
    window: migWindowFrom($("#mig_win_start").val(), $("#mig_win_end").val()),
    verify: $("#mig_verify").is(":checked"),
    force_stop_desktops: $("#mig_force_stop").is(":checked")
  };
}

function connection_done () { loadMigrations(); }
function connection_lost () { }

function socketio_on () {
  socket.on("storage:migration", function (raw) {
    let m;
    try { m = (typeof raw === "string") ? JSON.parse(raw) : raw; } catch (e) { return; }
    renderMigration(m);
  });
}

$(document).ready(function () {
  loadMigrationPools();
  loadMigrations();

  $("#mig_preview").on("click", function () {
    $("#mig_preview_out").text("Building plan…");
    $.ajax({
      type: "POST", url: `${MIG_API}/plan`, contentType: "application/json",
      data: JSON.stringify({ selection: migSelection() })
    }).done(function (plan) {
      const t = plan.totals || {};
      $("#mig_preview_out").text(
        `${(plan.trees || []).length} trees · ${t.items_total || 0} disks · ${migBytes(t.bytes_total || 0)}`);
    }).fail(function (xhr) {
      $("#mig_preview_out").text("Plan failed: " + ((xhr.responseJSON && xhr.responseJSON.description) || xhr.status));
    });
  });

  $("#mig_create").on("click", function () {
    const body = { selection: migSelection(), config: migCreateConfig() };
    $.ajax({
      type: "POST", url: MIG_API, contentType: "application/json", data: JSON.stringify(body)
    }).done(function (mig) {
      $.ajax({ type: "POST", url: `${MIG_API}/${mig.id}/start` }).always(loadMigrations);
    }).fail(function (xhr) {
      $("#mig_preview_out").text("Create failed: " + ((xhr.responseJSON && xhr.responseJSON.description) || xhr.status));
    });
  });

  // expand / collapse a migration
  $("#migrations").on("click", ".mig-row", function () {
    const id = $(this).data("mig");
    migExpanded[id] = !migExpanded[id];
    loadMigration(id);
  });

  // start / pause / cancel
  $("#migrations").on("click", ".mig-action", function (e) {
    e.stopPropagation();
    const id = $(this).data("mig");
    const action = $(this).data("action");
    $.ajax({ type: "POST", url: `${MIG_API}/${id}/${action}` }).always(function () { loadMigration(id); });
  });

  // apply per-job config
  $("#migrations").on("click", ".mig-config-apply", function (e) {
    e.stopPropagation();
    const $f = $(this).closest(".mig-config");
    const id = $f.data("mig");
    const body = {
      bwlimit_kbs: parseInt($f.find(".cfg-bwlimit").val(), 10) || 0,
      parallelism: parseInt($f.find(".cfg-parallel").val(), 10) || 1,
      window: migWindowFrom($f.find(".cfg-win-start").val(), $f.find(".cfg-win-end").val()),
      verify: $f.find(".cfg-verify").is(":checked"),
      force_stop_desktops: $f.find(".cfg-force").is(":checked")
    };
    $f.find(".mig-config-out").text("Saving…");
    $.ajax({ type: "PUT", url: `${MIG_API}/${id}/config`, contentType: "application/json", data: JSON.stringify(body) })
      .done(function () { $f.find(".mig-config-out").text("saved"); loadMigration(id); })
      .fail(function (xhr) { $f.find(".mig-config-out").text("error: " + ((xhr.responseJSON && xhr.responseJSON.description) || xhr.status)); });
  });

  // expand a tree -> show its disks (fetched lazily from the status endpoint)
  $("#migrations").on("click", ".mig-tree", function (e) {
    e.stopPropagation();
    const $row = $(this);
    const id = $row.data("mig");
    const tree = $row.data("tree");
    const $next = $row.next("tr.mig-disks");
    if ($next.length) { $next.remove(); $row.find("i").attr("class", "fa fa-caret-right"); return; }
    $row.find("i").attr("class", "fa fa-caret-down");
    $.ajax({ type: "GET", url: `${MIG_API}/${id}` }).done(function (m) {
      const disks = (m.items || []).filter(function (it) { return it.tree_id === tree; });
      let h = `<tr class="mig-disks"><td></td><td colspan="4"><table class="table table-condensed" style="margin:0;">
        <thead><tr><th>Disk</th><th>Kind</th><th>State</th><th>Size</th><th>Error</th></tr></thead><tbody>`;
      disks.forEach(function (d) {
        h += `<tr><td>${migEscape(d.storage_id)}</td><td>${migEscape(d.kind || "")}</td>
          <td>${migEscape(d.state)}</td><td>${migBytes(d.size_bytes)}</td><td>${migEscape(d.error || "")}</td></tr>`;
      });
      h += "</tbody></table></td></tr>";
      $row.after(h);
    });
  });

  // Load the shared /administrators SocketIO connector; it calls
  // connection_done() on connect and we bind our handler in socketio_on().
  $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on);
});
