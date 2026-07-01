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
const CATEGORIES_API = "/api/v4/admin/items/categories";
const MIG_TERMINAL = ["completed", "failed", "canceled"];
const MIG_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

// migrations expanded in the table (preserved across re-render)
const migExpanded = {};

function migEscape (s) {
  // Escape for use inside double-quoted HTML attributes (and text). Without the
  // quote escapes, an admin-set window value like `" autofocus onfocus=alert(1)`
  // would break out of the attribute -> attribute-injection XSS (guard-3).
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
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

// recurring / days can arrive top-level (status endpoint / socket) or only
// inside config (list fallback) — read either.
function migRecurring (m) {
  return m.recurring != null ? !!m.recurring : !!(m.config && m.config.recurring);
}

function migDays (m) {
  if (m.days) return m.days;
  return (m.config && m.config.window && m.config.window.days) || [];
}

function migDaysLabel (days) {
  if (!days || !days.length) return "every day";
  const set = days.slice().sort(function (a, b) { return a - b; });
  const key = set.join(",");
  if (key === "0,1,2,3,4,5,6") return "every day";
  if (key === "0,1,2,3,4") return "Mon–Fri";
  if (key === "5,6") return "weekend";
  return set.map(function (d) { return MIG_DAY_NAMES[d] || d; }).join(",");
}

// Schedule cell: days + window state, plus the next-run for a recurring job.
function migScheduleLabel (m) {
  let s = migDaysLabel(migDays(m)) + " · " + migWindowLabel(m);
  if (migRecurring(m) && m.next_run_seconds != null && m.next_run_seconds > 0) {
    s += " · next " + migEta(m.next_run_seconds);
  }
  return s;
}

function migStatusCell (m) {
  let s = migEscape(m.status);
  if (migRecurring(m)) s += ' <span class="label label-info" title="recurring">↻</span>';
  return s;
}

function migBar (done, total, bytesDone, bytesTotal) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  const bpct = bytesTotal ? Math.round((bytesDone / bytesTotal) * 100) : 0;
  return `<div class="progress" style="margin:0;min-width:140px;height:16px;" title="${migBytes(bytesDone)} / ${migBytes(bytesTotal)}">
      <div class="progress-bar progress-bar-success" style="width:${bpct}%;line-height:16px;">${done}/${total} (${pct}%)</div>
    </div>`;
}

// A downloadable audit report is always available (also for terminal jobs).
function migLogButton (m) {
  return `<a class="btn btn-xs btn-default mig-log" href="${MIG_API}/${encodeURIComponent(m.id)}/log?format=csv" title="Download CSV report" onclick="event.stopPropagation();">Log</a>`;
}

function migActionButtons (m) {
  if (MIG_TERMINAL.indexOf(m.status) !== -1) {
    return migEscape(m.status) + " " + migLogButton(m);
  }
  return `
    <button class="btn btn-xs btn-success mig-action" data-mig="${migEscape(m.id)}" data-action="start">Start</button>
    <button class="btn btn-xs btn-warning mig-action" data-mig="${migEscape(m.id)}" data-action="pause">Pause</button>
    <button class="btn btn-xs btn-danger mig-action" data-mig="${migEscape(m.id)}" data-action="cancel">Cancel</button>
    ${migLogButton(m)}`;
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
      <label style="margin-left:8px;"><input type="checkbox" class="cfg-recurring" ${c.recurring ? "checked" : ""} ${dis}> recurring</label>
      <span class="cfg-days" style="margin-left:8px;">Days
        ${MIG_DAY_NAMES.map(function (n, i) {
          const on = ((w.days || []).indexOf(i) !== -1) ? "checked" : "";
          return `<label style="font-weight:normal;"><input type="checkbox" class="mig-day" value="${i}" ${on} ${dis}> ${n}</label>`;
        }).join("")}
      </span>
      <label style="margin-left:8px;">Re-scan
        <select class="form-control input-sm cfg-cadence" ${dis}>
          ${migOpt(["edge_on_drain", "edge", "continuous"], c.rescan_cadence || "edge_on_drain")}
        </select>
      </label>
      <label style="margin-left:8px;">On&nbsp;fail
        <select class="form-control input-sm cfg-failure" ${dis}>
          ${migOpt(["retry_quarantine", "pause", "retry_forever"], c.failure_policy || "retry_quarantine")}
        </select>
      </label>
      <label style="margin-left:8px;">after
        <input type="number" class="form-control input-sm cfg-quarantine-after" min="1" style="width:52px;" value="${migEscape(c.quarantine_after != null ? c.quarantine_after : 3)}" ${dis}>
      </label>
      <button type="button" class="btn btn-default btn-xs mig-config-apply" style="margin-left:8px;" ${dis}>Apply</button>
      <span class="mig-config-out" style="margin-left:8px;color:#888;"></span>
    </form>`;
}

// <option> list with the current value pre-selected (values are safe enums).
function migOpt (values, current) {
  return values.map(function (v) {
    return `<option value="${v}"${v === current ? " selected" : ""}>${v}</option>`;
  }).join("");
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
      <td>${migStatusCell(m)}</td>
      <td>${migBar(t.done || 0, t.items_total || 0, t.bytes_done || 0, t.bytes_total || 0)}</td>
      <td>${migEta(m.eta_seconds)}</td>
      <td>${migEscape(migScheduleLabel(m))}</td>
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
    loadMigrationPathPrefixes();
  });
}

function loadMigrationCategories () {
  $.ajax({ type: "GET", url: CATEGORIES_API }).done(function (data) {
    const rows = Array.isArray(data) ? data : (data.categories || data.data || []);
    $("#mig_category").html(rows.map(function (c) {
      return `<option value="${migEscape(c.id)}">${migEscape(c.name || c.id)}</option>`;
    }).join(""));
  });
}

// Real source path-prefixes for the `path` kind, scoped to the chosen source
// pool (no free text).
function loadMigrationPathPrefixes () {
  const src = $("#mig_src_pool").val();
  const url = MIG_API + "/path-prefixes" + (src ? "?src_pool_id=" + encodeURIComponent(src) : "");
  $.ajax({ type: "GET", url: url }).done(function (data) {
    const prefixes = (data && data.prefixes) || [];
    $("#mig_path_prefix").html(prefixes.map(function (p) {
      return `<option value="${migEscape(p)}">${migEscape(p)}</option>`;
    }).join(""));
  });
}

// Show only the inputs relevant to the selected kind.
function migKindApply () {
  const kind = $("#mig_kind").val();
  $(".mig-grp").hide();
  $(".mig-grp-" + kind).show();
}

// Selected weekdays (0..6, Mon=0) from `.mig-day` checkboxes within a scope.
function migDaysFrom ($scope) {
  const days = [];
  $scope.find(".mig-day:checked").each(function () { days.push(parseInt($(this).val(), 10)); });
  return days;
}

function migSetDays ($scope, days) {
  const set = {};
  (days || []).forEach(function (d) { set[d] = true; });
  $scope.find(".mig-day").each(function () { $(this).prop("checked", !!set[parseInt($(this).val(), 10)]); });
}

// The migration selection for the currently-chosen kind (every field a
// dropdown value — no free text).
function migSelection () {
  const kind = $("#mig_kind").val();
  const dst = $("#mig_dst_pool").val();
  if (kind === "path") {
    return { kind: "path", src_pool_id: $("#mig_src_pool").val(),
      path_prefix: $("#mig_path_prefix").val(), dst_pool_id: dst };
  }
  if (kind === "category") {
    return { kind: "category", category_id: $("#mig_category").val(), dst_pool_id: dst };
  }
  return { kind: "pool", src_pool_id: $("#mig_src_pool").val(), dst_pool_id: dst };
}

// A window may be time-only, days-only, or both; null when neither is set.
function migWindowFrom (start, end, days) {
  start = (start || "").trim();
  end = (end || "").trim();
  days = days || [];
  const w = { tz: "UTC" };
  let has = false;
  if (start && end) { w.start = start; w.end = end; has = true; }
  if (days.length) { w.days = days; has = true; }
  return has ? w : null;
}

function migCreateConfig () {
  return {
    bwlimit_kbs: parseInt($("#mig_bwlimit").val(), 10) || 0,
    parallelism: parseInt($("#mig_parallel").val(), 10) || 1,
    window: migWindowFrom($("#mig_win_start").val(), $("#mig_win_end").val(), migDaysFrom($("#mig_days"))),
    verify: $("#mig_verify").is(":checked"),
    force_stop_desktops: $("#mig_force_stop").is(":checked"),
    recurring: $("#mig_recurring").is(":checked"),
    rescan_cadence: $("#mig_rescan_cadence").val(),
    failure_policy: $("#mig_failure_policy").val(),
    quarantine_after: parseInt($("#mig_quarantine_after").val(), 10) || 3
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
  loadMigrationCategories();
  loadMigrations();
  migKindApply();

  // kind dropdown -> show the matching inputs
  $("#mig_kind").on("change", migKindApply);

  // source pool changes -> re-scope the path-prefix dropdown
  $("#mig_src_pool").on("change", loadMigrationPathPrefixes);

  // days-of-week presets on the create form
  $("#migration_new").on("click", ".mig-days-preset", function () {
    const preset = $(this).data("preset");
    const map = { all: [0, 1, 2, 3, 4, 5, 6], weekdays: [0, 1, 2, 3, 4], weekend: [5, 6], none: [] };
    migSetDays($("#mig_days"), map[preset] || []);
  });

  // quarantine budget only applies to the retry_quarantine policy
  function migToggleQuarantine () {
    $(".mig-quarantine-after").toggle($("#mig_failure_policy").val() === "retry_quarantine");
  }
  $("#mig_failure_policy").on("change", migToggleQuarantine);
  migToggleQuarantine();

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
      window: migWindowFrom($f.find(".cfg-win-start").val(), $f.find(".cfg-win-end").val(), migDaysFrom($f)),
      verify: $f.find(".cfg-verify").is(":checked"),
      force_stop_desktops: $f.find(".cfg-force").is(":checked"),
      recurring: $f.find(".cfg-recurring").is(":checked"),
      rescan_cadence: $f.find(".cfg-cadence").val(),
      failure_policy: $f.find(".cfg-failure").val(),
      quarantine_after: parseInt($f.find(".cfg-quarantine-after").val(), 10) || 3
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
