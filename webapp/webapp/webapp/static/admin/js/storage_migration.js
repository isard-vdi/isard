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

// status -> {bootstrap label class, font-awesome icon, human tooltip}
const MIG_STATUS = {
  planned:   { cls: "default", icon: "fa-clock-o",        tip: "Planned — not started yet." },
  pending:   { cls: "default", icon: "fa-clock-o",        tip: "Waiting to start." },
  running:   { cls: "primary", icon: "fa-refresh fa-spin", tip: "Copying disks now." },
  waiting:   { cls: "info",    icon: "fa-hourglass-half", tip: "Idle until the schedule window opens." },
  paused:    { cls: "warning", icon: "fa-pause",          tip: "Paused — resume with Start." },
  draining:  { cls: "info",    icon: "fa-tint",           tip: "Finishing in-flight disks before stopping." },
  quarantined: { cls: "warning", icon: "fa-exclamation-triangle", tip: "Some disks were set aside after repeated failures." },
  completed: { cls: "success", icon: "fa-check",          tip: "All disks moved and verified." },
  failed:    { cls: "danger",  icon: "fa-times",          tip: "Migration stopped on a failure." },
  canceled:  { cls: "default", icon: "fa-ban",            tip: "Canceled by an admin." }
};

// friendly labels for the enum <select>s (values stay the raw enum)
const MIG_CADENCE_LABELS = {
  edge_on_drain: "Edge + on-drain", edge: "Edge only", continuous: "Continuous"
};
const MIG_FAILURE_LABELS = {
  retry_quarantine: "Retry, then quarantine", pause: "Pause for attention", retry_forever: "Retry forever"
};

function migStatusBadge (status) {
  const s = MIG_STATUS[status] || { cls: "default", icon: "fa-question", tip: status };
  return `<span class="label label-${s.cls}" title="${migEscape(s.tip)}" data-toggle="tooltip">` +
    `<i class="fa ${s.icon}"></i> ${migEscape(status)}</span>`;
}

// Long UUIDs are noise in the table — show a short head, full id on hover + copy title.
function migShortId (id) {
  const full = String(id == null ? "" : id);
  const head = full.length > 12 ? full.slice(0, 8) + "…" : full;
  return `<span class="mig-id" title="${migEscape(full)}" data-toggle="tooltip">${migEscape(head)}</span>`;
}

// (Re)initialise Bootstrap tooltips for freshly-rendered content; no-op if the
// plugin isn't loaded (native title= still shows).
function migInitTooltips ($scope) {
  try { ($scope || $(document)).find('[data-toggle="tooltip"]').tooltip({ container: "body" }); } catch (e) { /* native title fallback */ }
}

// migrations expanded in the table (preserved across re-render)
const migExpanded = {};

// id -> {name, mountpoint} for storage pools, and id -> name for categories,
// filled from the same lists that populate the create-form <select>s. Used to
// resolve a migration's selection (pool ids) into the human origin → destination
// route shown in the table + detail. Fall back to the short id until loaded.
const migPoolInfo = {};
const migCatNames = {};
// last-seen selection per migration id, so the route cell can be re-rendered when
// the pool/category name caches arrive after the rows are already drawn.
const migSelById = {};

function migPoolName (id) {
  if (!id) return "—";
  const p = migPoolInfo[id];
  return (p && p.name) ? p.name : migShortId(id);
}

// Resolve a migration's selection into a displayable origin/destination route.
// A `pool` move goes pool→pool; a `path` move is a source pool scoped to a
// directory prefix; a `category` move takes every disk of a category → dst pool.
function migRouteParts (m) {
  const s = m.selection || {};
  const dst = migPoolName(s.dst_pool_id);
  const dstTip = (migPoolInfo[s.dst_pool_id] || {}).mountpoint || "";
  let origin = "—", originTip = "";
  if (s.kind === "category") {
    origin = "category: " + (migCatNames[s.category_id] || migShortId(s.category_id));
  } else {
    origin = migPoolName(s.src_pool_id);
    originTip = (s.kind === "path")
      ? (s.path_prefix || "")
      : ((migPoolInfo[s.src_pool_id] || {}).mountpoint || "");
  }
  return { origin: origin, originTip: originTip, dst: dst, dstTip: dstTip,
    kind: s.kind || "pool", pathPrefix: s.path_prefix, categoryId: s.category_id };
}

// Re-render the route cell + any open detail route line for every drawn row,
// used once the pool/category name caches load after the rows.
function migRefreshRoutes () {
  $("#migrations tbody tr.mig-row").each(function () {
    const id = $(this).data("mig");
    const sel = migSelById[id];
    if (!sel) return;
    $(this).find("td.mig-route").html(migRouteCell({ selection: sel }));
    const $line = $(`#migrations tbody tr.mig-detail[data-mig="${id}"] .mig-route-line`);
    if ($line.length) $line.replaceWith(migRouteLine({ selection: sel }));
  });
  migInitTooltips($("#migrations"));
}

// Compact origin → destination for the table row.
function migRouteCell (m) {
  const r = migRouteParts(m);
  const tip = `From ${r.origin}${r.originTip ? " (" + r.originTip + ")" : ""}` +
    ` → to ${r.dst}${r.dstTip ? " (" + r.dstTip + ")" : ""}`;
  return `<span class="mig-route-inner" title="${migEscape(tip)}" data-toggle="tooltip" style="white-space:nowrap;font-size:12px;">` +
    `${migEscape(r.origin)} <i class="fa fa-long-arrow-right" style="color:#888;"></i> ${migEscape(r.dst)}</span>`;
}

// Fuller origin → destination line for the expanded detail: pool names, their
// mountpoints, and the selection kind (+ path prefix / category scope).
function migRouteLine (m) {
  const r = migRouteParts(m);
  const scope = (r.kind === "path" && r.pathPrefix) ? `path: ${r.pathPrefix}` : r.kind;
  return `<div class="mig-route-line" style="margin-bottom:6px;font-size:13px;">
      <b>Route:</b>
      <span class="label label-default" title="${migEscape(r.originTip || "")}" data-toggle="tooltip">${migEscape(r.origin)}</span>
      ${r.originTip ? `<small class="text-muted">${migEscape(r.originTip)}</small>` : ""}
      <i class="fa fa-long-arrow-right" style="margin:0 4px;"></i>
      <span class="label label-primary" title="${migEscape(r.dstTip || "")}" data-toggle="tooltip">${migEscape(r.dst)}</span>
      ${r.dstTip ? `<small class="text-muted">${migEscape(r.dstTip)}</small>` : ""}
      <small class="text-muted" style="margin-left:6px;">(${migEscape(scope)})</small>
    </div>`;
}

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

// Operators think in GB, the API speaks bytes. One GB here is 1024^3, matching
// what migBytes() prints, so a value typed in comes back out unchanged.
const MIG_GB = 1024 * 1024 * 1024;

function migGbToBytes (v) {
  const n = parseFloat(v);
  return (!isFinite(n) || n <= 0) ? 0 : Math.round(n * MIG_GB);
}

function migBytesToGb (n) {
  n = parseInt(n, 10);
  if (!n || n <= 0) return 0;
  // trim to 3 decimals so a round GB does not render as 4.999999
  return Math.round((n / MIG_GB) * 1000) / 1000;
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
  let s = migStatusBadge(m.status);
  if (migRecurring(m)) s += ' <span class="label label-info" title="Recurring job — re-scans and runs again each window." data-toggle="tooltip"><i class="fa fa-repeat"></i></span>';
  return s;
}

// Fraction of a disk's per-disk saga completed at each state. The move is the
// bulk of the transfer; rebase → db_update → release is the commit tail, which
// (when verify is on) also runs a checksum verify per disk — so a `rebased` disk
// is NOT ~done, it still has the verify+release phase left. Weighting by stage
// keeps the bar honest across ALL phases instead of jumping 0→100 at release.
const MIG_STAGE_WEIGHT = {
  pending: 0, preflight_ok: 0.05, moving: 0.2, moved: 0.5,
  rebased: 0.7, db_updated: 0.85, released: 1.0,
  skipped: 1.0, quarantined: 1.0, failed: 0
};

function migBar (done, total, bytesDone, bytesTotal, stateCounts) {
  stateCounts = stateCounts || {};
  let weighted = 0;
  Object.keys(stateCounts).forEach(function (s) {
    weighted += (MIG_STAGE_WEIGHT[s] != null ? MIG_STAGE_WEIGHT[s] : 0) * stateCounts[s];
  });
  const released = stateCounts.released || 0;
  const copied = (stateCounts.moved || 0) + (stateCounts.rebased || 0) +
    (stateCounts.db_updated || 0) + released;
  const committing = (stateCounts.rebased || 0) + (stateCounts.db_updated || 0);
  const moving = stateCounts.moving || 0;
  const pct = total ? Math.round((weighted / total) * 100) : 0;
  const doneW = total ? (released / total) * 100 : 0;                 // solid = committed
  const progW = total ? Math.max(0, (weighted - released) / total) * 100 : 0; // striped = in-flight
  const label = `${pct}% · ${released}/${total} done`;
  let phase = "";
  if (moving) phase += `${moving} copying · `;
  if (committing) phase += `${committing} verifying/releasing · `;
  const title = `${pct}% complete · ${copied}/${total} copied to destination · ` +
    `${released} committed (source freed) · ${phase}${migBytes(bytesDone)}/${migBytes(bytesTotal)} committed`;
  return `<div class="progress" style="position:relative;margin:0;min-width:160px;height:16px;" title="${migEscape(title)}">
      <div class="progress-bar progress-bar-success" style="width:${doneW}%;line-height:16px;"></div>
      <div class="progress-bar progress-bar-success progress-bar-striped active" style="width:${progW}%;line-height:16px;"></div>
      <span style="position:absolute;left:0;right:0;top:0;text-align:center;line-height:16px;font-size:11px;color:#222;">${migEscape(label)}</span>
    </div>`;
}

// Brief transient feedback. Uses the admin theme's PNotify when present, with a
// console fallback so it never throws where PNotify isn't loaded (offline preview).
function migToast (text, kind) {
  try {
    if (typeof PNotify === "function") {
      new PNotify({ text: text, type: (kind === "danger" ? "error" : (kind || "success")),
        delay: 3500, buttons: { closer: true, sticker: false } });
      return;
    }
  } catch (e) { /* fall through */ }
  if (kind === "danger") console.error(text); else console.log(text);
}

// A downloadable audit report is always available (also for terminal jobs).
// A <button> (not an <a href>): the admin auth token is injected into XHRs only,
// so a plain link navigation hits apiv4 unauthenticated ("Not authenticated").
// The click handler fetches it authenticated and saves it as a Blob.
function migLogButton (m) {
  return `<button class="btn btn-xs btn-default mig-log" data-mig="${migEscape(m.id)}" title="Download the full per-disk audit report (CSV)." data-toggle="tooltip"><i class="fa fa-download"></i> Log</button>`;
}

// Which admin actions make sense for a given status (so we don't offer Start on
// an already-running job, or Pause on a paused one).
function migActionEnabled (status, action) {
  if (MIG_TERMINAL.indexOf(status) !== -1) return false;
  // Start/resume: anything not already running (planned, paused, scheduled,
  // waiting, window_closed). Pause: only a job that is actively progressing.
  // Cancel: any non-terminal job.
  if (action === "start") return status !== "running" && status !== "finishing_tree";
  if (action === "pause") return status === "running" || status === "waiting" ||
    status === "window_closed";
  if (action === "cancel") return true;
  return false;
}

function migActionButtons (m) {
  if (MIG_TERMINAL.indexOf(m.status) !== -1) {
    return migStatusBadge(m.status) + " " + migLogButton(m);
  }
  const btn = function (action, cls, icon, text, tip) {
    const off = migActionEnabled(m.status, action) ? "" : "disabled";
    return `<button class="btn btn-xs btn-${cls} mig-action" data-mig="${migEscape(m.id)}" data-action="${action}" ${off} title="${migEscape(tip)}" data-toggle="tooltip"><i class="fa ${icon}"></i> ${text}</button>`;
  };
  return `
    ${btn("start", "success", "fa-play", "Start", "Start or resume this migration.")}
    ${btn("pause", "warning", "fa-pause", "Pause", "Pause after in-flight disks finish; resume later with no data loss.")}
    ${btn("cancel", "danger", "fa-stop", "Cancel", "Stop and abandon this migration. Already-moved disks stay in the destination.")}
    ${migLogButton(m)}`;
}

function migCard (label, value, tip) {
  const t = tip ? ` title="${migEscape(tip)}" data-toggle="tooltip"` : "";
  return `<div style="display:inline-block;min-width:110px;margin:0 14px 8px 0;"${t}>
      <div style="font-size:20px;font-weight:600;">${migEscape(value)}</div>
      <div style="color:#888;font-size:12px;">${migEscape(label)}</div>
    </div>`;
}

// Config controls (window / parallelism / bwlimit / force-stop) for one job.
function migConfigControls (m) {
  const c = m.config || {};
  const w = c.window || {};
  const dis = MIG_TERMINAL.indexOf(m.status) !== -1 ? "disabled" : "";
  return `<form class="form-inline mig-config" data-mig="${migEscape(m.id)}" style="margin:8px 0;padding:8px;background:#fff;border:1px solid #eee;border-radius:3px;">
      <span class="text-muted" style="margin-right:8px;font-size:11px;text-transform:uppercase;letter-spacing:.04em;" title="Live settings for this job — edit and press Apply." data-toggle="tooltip">Settings</span>
      <label title="Daily copy window (24h UTC). Blank = always." data-toggle="tooltip">Window
        <input type="text" class="form-control input-sm cfg-win-start" placeholder="HH:MM" style="width:62px;" value="${migEscape(w.start || "")}" ${dis}>
        &ndash;
        <input type="text" class="form-control input-sm cfg-win-end" placeholder="HH:MM" style="width:62px;" value="${migEscape(w.end || "")}" ${dis}>
      </label>
      <label style="margin-left:8px;" title="Disks copied at once. Higher = faster, more I/O." data-toggle="tooltip">Parallel
        <input type="number" class="form-control input-sm cfg-parallel" min="1" style="width:58px;" value="${migEscape(c.parallelism != null ? c.parallelism : 1)}" ${dis}>
      </label>
      <label style="margin-left:8px;" title="Per-disk bandwidth cap in KB/s. 0 = unlimited." data-toggle="tooltip">bwlimit&nbsp;KB/s
        <input type="number" class="form-control input-sm cfg-bwlimit" min="0" style="width:84px;" value="${migEscape(c.bwlimit_kbs != null ? c.bwlimit_kbs : 0)}" ${dis}>
      </label>
      <label style="margin-left:8px;" title="Stop a running desktop to move its disk (restartable after)." data-toggle="tooltip"><input type="checkbox" class="cfg-force" ${c.force_stop_desktops ? "checked" : ""} ${dis}> force-stop</label>
      <label style="margin-left:8px;" title="Checksum-verify each copy before removing the source." data-toggle="tooltip"><input type="checkbox" class="cfg-verify" ${c.verify === false ? "" : "checked"} ${dis}> verify</label>
      <label style="margin-left:8px;" title="Re-scan and run again each window instead of finishing once." data-toggle="tooltip"><input type="checkbox" class="cfg-recurring" ${c.recurring ? "checked" : ""} ${dis}> recurring</label>
      <span class="cfg-days" style="margin-left:8px;" title="Weekdays the window applies to." data-toggle="tooltip">Days
        ${MIG_DAY_NAMES.map(function (n, i) {
          const on = ((w.days || []).indexOf(i) !== -1) ? "checked" : "";
          return `<label style="font-weight:normal;"><input type="checkbox" class="mig-day" value="${i}" ${on} ${dis}> ${n}</label>`;
        }).join("")}
      </span>
      <label style="margin-left:8px;" title="How often to look for newly-matching disks." data-toggle="tooltip">Re-scan
        <select class="form-control input-sm cfg-cadence" ${dis}>
          ${migOpt(["edge_on_drain", "edge", "continuous"], c.rescan_cadence || "edge_on_drain", MIG_CADENCE_LABELS)}
        </select>
      </label>
      <label style="margin-left:8px;" title="What to do when a disk fails to copy or verify." data-toggle="tooltip">On&nbsp;fail
        <select class="form-control input-sm cfg-failure" ${dis}>
          ${migOpt(["retry_quarantine", "pause", "retry_forever"], c.failure_policy || "retry_quarantine", MIG_FAILURE_LABELS)}
        </select>
      </label>
      <label style="margin-left:8px;" title="Failed attempts before a disk is quarantined." data-toggle="tooltip">after
        <input type="number" class="form-control input-sm cfg-quarantine-after" min="1" style="width:52px;" value="${migEscape(c.quarantine_after != null ? c.quarantine_after : 3)}" ${dis}>
      </label>
      <label style="margin-left:8px;" title="Move at most this much per run, then stop until the next window. Honoured at tree boundaries, so the run may overshoot by one tree. 0 = no limit." data-toggle="tooltip">Stop&nbsp;after&nbsp;GB
        <input type="number" class="form-control input-sm cfg-budget-gb" min="0" step="any" style="width:78px;" value="${migEscape(migBytesToGb(c.max_bytes_per_occurrence))}" ${dis}>
      </label>
      <label style="margin-left:8px;" title="Refuse a copy that would leave the destination below this much free. Filesystem-level: no protection on a thin-provisioned (VDO) pool — use Stop after there. 0 = off." data-toggle="tooltip">Keep&nbsp;free&nbsp;GB
        <input type="number" class="form-control input-sm cfg-minfree-gb" min="0" step="any" style="width:78px;" value="${migEscape(migBytesToGb(c.min_free_bytes))}" ${dis}>
      </label>
      <button type="button" class="btn btn-default btn-xs mig-config-apply" style="margin-left:8px;" ${dis} title="Apply these settings to the running job." data-toggle="tooltip"><i class="fa fa-check"></i> Apply</button>
      <span class="mig-config-out" style="margin-left:8px;color:#888;"></span>
    </form>`;
}

// <option> list with the current value pre-selected (values are safe enums).
// `labels` optionally maps a value to a friendlier display text.
function migOpt (values, current, labels) {
  labels = labels || {};
  return values.map(function (v) {
    return `<option value="${v}"${v === current ? " selected" : ""}>${migEscape(labels[v] || v)}</option>`;
  }).join("");
}

function migTreeRows (m) {
  let html = `<table class="table table-condensed" style="margin:6px 0;background:#fafafa;">
    <thead><tr><th style="width:18px;"></th>
      <th title="Base template at the root of the backing-chain tree." data-toggle="tooltip">Root tree</th>
      <th title="Derived templates in this tree." data-toggle="tooltip">Derivative templates</th>
      <th title="Desktops in this tree." data-toggle="tooltip">Desktops</th>
      <th>Progress</th></tr></thead><tbody>`;
  (m.trees || []).forEach(function (t) {
    html += `<tr class="mig-tree" data-mig="${migEscape(m.id)}" data-tree="${migEscape(t.tree_id)}" style="cursor:pointer;" title="Click to list the individual disks in this tree." data-toggle="tooltip">
        <td><i class="fa fa-caret-right"></i></td>
        <td>${migShortId(t.root_storage_id || t.tree_id)}</td>
        <td>${migEscape(t.derivative_templates || 0)}</td>
        <td>${migEscape(t.desktops || 0)}</td>
        <td>${migBar(t.done || 0, t.items_total || 0, t.bytes_done || 0, t.bytes_total || 0, t.state_counts)}</td>
      </tr>`;
  });
  html += "</tbody></table>";
  return html;
}

// Detail row: totals cards + config controls + per-tree table.
function migDetail (m) {
  const t = m.totals || {};
  const cards =
    migCard("trees", t.trees || (m.trees || []).length, "Independent backing-chain trees (a base template with its descendants). Each tree moves atomically.") +
    migCard("derivative templates", t.derivative_templates || 0, "Templates derived from a base that also move as part of the tree.") +
    migCard("desktops", t.desktops || 0, "Desktops whose disks are moved.") +
    migCard("disks", t.items_total || 0, "Total qcow2 disks to copy.") +
    migCard("bytes", migBytes(t.bytes_total || 0), "Total data to copy across all disks.") +
    migCard("ETA", migEta(m.eta_seconds), "Estimated time remaining at the current copy rate.");
  return `<tr class="mig-detail" data-mig="${migEscape(m.id)}"><td></td><td colspan="7">
      ${migRouteLine(m)}
      <div style="margin-bottom:6px;">${cards}</div>
      ${migConfigControls(m)}
      ${migTreeRows(m)}
    </td></tr>`;
}

function migRowHtml (m) {
  const t = m.totals || {};
  const open = migExpanded[m.id];
  let html = `<tr class="mig-row" data-mig="${migEscape(m.id)}" style="cursor:pointer;" title="Click to expand: totals, live settings and per-tree progress." data-toggle="tooltip">
      <td><i class="fa fa-caret-${open ? "down" : "right"}"></i></td>
      <td>${migShortId(m.id)}</td>
      <td class="mig-route">${migRouteCell(m)}</td>
      <td>${migStatusCell(m)}</td>
      <td>${migBar(t.done || 0, t.items_total || 0, t.bytes_done || 0, t.bytes_total || 0, t.state_counts)}</td>
      <td>${migEta(m.eta_seconds)}</td>
      <td>${migEscape(migScheduleLabel(m))}</td>
      <td class="mig-actions-cell">${migActionButtons(m)}</td>
    </tr>`;
  if (open) html += migDetail(m);
  return html;
}

// Render/replace one migration's row(s) (the aggregate shape is shared by the
// status endpoint and the socket event).
function renderMigration (m) {
  if (!m || !m.id) return;
  if (m.selection) migSelById[m.id] = m.selection;  // for route re-render on cache load
  $("#migrations tbody tr.mig-empty").remove();
  const $existing = $(`#migrations tbody tr[data-mig="${m.id}"]`);
  const $html = $(migRowHtml(m));
  if ($existing.length) $existing.first().replaceWith($html.first());
  else $("#migrations tbody").append($html.first());
  // detail row (only when expanded)
  $(`#migrations tbody tr.mig-detail[data-mig="${m.id}"]`).remove();
  if (migExpanded[m.id]) $(`#migrations tbody tr.mig-row[data-mig="${m.id}"]`).after($html.filter(".mig-detail"));
  migInitTooltips($(`#migrations tbody tr[data-mig="${m.id}"]`));
}

// Friendly placeholder when the table is empty.
function migShowEmpty () {
  if ($("#migrations tbody tr").length) return;
  $("#migrations tbody").html(
    '<tr class="mig-empty"><td colspan="8"><i class="fa fa-inbox"></i> ' +
    'No disk migrations yet. Choose what to move above, click <b>Preview</b> to size the plan, then <b>Create &amp; start</b>.' +
    "</td></tr>");
}

function loadMigration (id) {
  return $.ajax({ type: "GET", url: `${MIG_API}/${id}` }).done(renderMigration);
}

function loadMigrations () {
  $.ajax({ type: "GET", url: MIG_API }).done(function (data) {
    $("#migrations tbody").empty();
    const migs = data.migrations || [];
    if (!migs.length) { migShowEmpty(); return; }
    migs.forEach(function (mig) {
      loadMigration(mig.id).fail(function () { renderMigration(mig); });
    });
  });
}

function loadMigrationPools () {
  $.ajax({ type: "GET", url: POOLS_API }).done(function (data) {
    const rows = data.storage_pools || data.data || (Array.isArray(data) ? data : []);
    const opts = rows.map(function (p) {
      migPoolInfo[p.id] = { name: p.name || p.id, mountpoint: p.mountpoint || "" };
      return `<option value="${migEscape(p.id)}">${migEscape(p.name || p.id)}</option>`;
    }).join("");
    // pool names just resolved -> re-render any already-drawn rows so their route
    // shows names instead of the short-id fallback.
    migRefreshRoutes();
    // lead with a blank placeholder so nothing is preselected on open — the plan
    // summary only appears once the admin has actively chosen source + destination.
    const placeholder = '<option value="" selected>— select —</option>';
    $("#mig_src_pool, #mig_dst_pool").html(placeholder + opts);
    loadMigrationPathPrefixes();
  });
}

function loadMigrationCategories () {
  $.ajax({ type: "GET", url: CATEGORIES_API }).done(function (data) {
    const rows = Array.isArray(data) ? data : (data.categories || data.data || []);
    $("#mig_category").html('<option value="" selected>— select —</option>' + rows.map(function (c) {
      migCatNames[c.id] = c.name || c.id;
      return `<option value="${migEscape(c.id)}">${migEscape(c.name || c.id)}</option>`;
    }).join(""));
    migRefreshRoutes();
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
  // The admin theme skins checkboxes with iCheck, which hides the real <input>
  // and shows its own control — a plain .prop("checked") updates the input but
  // NOT the visible skin, so presets appear to do nothing. Drive it through
  // iCheck when the plugin is present (falling back to .prop for previews/tests).
  const hasICheck = !!($.fn && $.fn.iCheck);
  $scope.find(".mig-day").each(function () {
    const on = !!set[parseInt($(this).val(), 10)];
    if (hasICheck) $(this).iCheck(on ? "check" : "uncheck");
    else $(this).prop("checked", on);
  });
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

// True only when the selection has every field the plan query needs — a real
// destination, plus the source/path/category for the chosen kind, and (for a
// pool move) a source that differs from the destination. Until this holds we
// show no summary and fire no query.
function migSelectionComplete () {
  const s = migSelection();
  if (!s.dst_pool_id) return false;
  if (s.kind === "path") return !!(s.src_pool_id && s.path_prefix && s.src_pool_id !== s.dst_pool_id);
  if (s.kind === "category") return !!s.category_id;
  return !!(s.src_pool_id && s.src_pool_id !== s.dst_pool_id);
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
    quarantine_after: parseInt($("#mig_quarantine_after").val(), 10) || 3,
    max_bytes_per_occurrence: migGbToBytes($("#mig_budget_gb").val()),
    min_free_bytes: migGbToBytes($("#mig_min_free_gb").val())
  };
}

// ── Live plan summary (dry-run counts/sizes) + ETA ──────────────────────────
// bytes_total / items_total from the last successful plan (drive the ETA recompute)
let migLastPlanBytes = null;
let migLastPlanItems = 0;
// per-disk throughput assumed for the ETA when no bwlimit cap is set (~100 MB/s)
const MIG_DEFAULT_KBPS = 102400;
// The background reconciler advances each disk through the saga one tick-gated
// step at a time (move, [verify], rebase), at most `parallel` disks in flight —
// so for many small disks this scheduling cadence dominates, not raw transfer.
const MIG_TICK_S = 60;   // scheduler reconciler interval (system.storage_migration_tick)
let migSummaryTimer = null;
// client-side cache of plan totals keyed by the selection, so toggling options
// back and forth re-shows a previous estimate instantly without re-querying.
const migPlanCache = {};

function migSelectionKey () { return JSON.stringify(migSelection()); }

function migSetSummaryState (txt, color) {
  $("#mig_sum_state").text(txt || "").css("color", color || "#aaa");
}

// Hide the whole summary box (no source/destination chosen yet).
function migHideSummary () {
  $("#mig_summary").hide();
  $("#mig_sum_loading, #mig_sum_content").hide();
}

// Show the summary box with the spinner while the plan query is in flight.
function migShowSummaryLoading () {
  $("#mig_summary").show();
  $("#mig_sum_content").hide();
  $("#mig_sum_loading").show();
}

// Fill the summary form from a plan `totals` (templates = base + derivative).
function migRenderSummary (totals) {
  totals = totals || {};
  const bbk = totals.bytes_by_kind || {};
  const ibk = totals.items_by_kind || {};
  const deriv = totals.derivative_templates || 0;
  // Templates = every template-kind disk (base + derivative). NOTE: use the
  // per-kind count, NOT `trees` — a standalone desktop is its own tree root but
  // is a desktop, so `trees` over-counts and the cells wouldn't sum to the total.
  const tpl = (ibk.template != null) ? ibk.template : (totals.trees || 0) + deriv;
  const base = tpl - deriv;
  $("#mig_sum_tpl").html(tpl +
    (deriv ? ` <small>(${base} base + ${deriv} derived)</small>` : ""));
  $("#mig_sum_tpl_sz").text(migBytes(bbk.template || 0));
  $("#mig_sum_desk").text((ibk.desktop != null) ? ibk.desktop : (totals.desktops || 0));
  $("#mig_sum_desk_sz").text(migBytes(bbk.desktop || 0));
  $("#mig_sum_media").text((ibk.media != null) ? ibk.media : (totals.media || 0));
  $("#mig_sum_media_sz").text(migBytes(bbk.media || 0));
  $("#mig_sum_total").text(totals.items_total || 0);
  $("#mig_sum_total_sz").text(migBytes(totals.bytes_total || 0));
  migLastPlanBytes = totals.bytes_total || 0;
  migLastPlanItems = totals.items_total || 0;
  $("#mig_summary").show();
  $("#mig_sum_loading").hide();
  $("#mig_sum_content").show();
  migRecalcEta();
}

// Recompute the ETA from the cached plan size/count + the current parallel /
// bwlimit. Two additive terms:
//   transfer      = bytes / (parallel × rate)                 — raw copy time
//   orchestration = ⌈items/parallel⌉ × steps × tick           — reconciler cadence
// The orchestration term is what the old (transfer-only) estimate ignored, which
// made it wildly optimistic for many small disks (30s predicted vs 15min real).
function migRecalcEta () {
  const bytes = migLastPlanBytes;
  if (bytes == null) return;
  if (!bytes) { $("#mig_sum_eta").text("—"); $("#mig_sum_eta_note").text("nothing to move"); return; }
  const par = Math.max(1, parseInt($("#mig_parallel").val(), 10) || 1);
  const bw = Math.max(0, parseInt($("#mig_bwlimit").val(), 10) || 0);
  const kbps = bw > 0 ? bw : MIG_DEFAULT_KBPS;
  const transfer = bytes / (par * kbps * 1024);
  // tick-gated saga steps per disk: move + rebase (+ verify when enabled)
  const steps = 2 + ($("#mig_verify").is(":checked") ? 1 : 0);
  const orchestration = Math.ceil((migLastPlanItems || 0) / par) * steps * MIG_TICK_S;
  $("#mig_sum_eta").text(migEta(transfer + orchestration));
  const rate = bw > 0 ? `${par}×${bw} KB/s` : "~100 MB/s/disk";
  $("#mig_sum_eta_note").text(`≈ ${rate} transfer + background reconciler (~${MIG_TICK_S}s/step, ${par} in parallel)`);
}

// Debounced dry-run plan fetch that fills the summary form. Reuses a cached
// result for a repeated selection (unless `immediate`, which forces a refresh).
function migLoadSummary (immediate) {
  clearTimeout(migSummaryTimer);
  // Nothing chosen yet (or an incomplete/no-op selection) -> no box, no query.
  if (!migSelectionComplete()) {
    migHideSummary();
    return;
  }
  const key = migSelectionKey();
  if (!immediate && Object.prototype.hasOwnProperty.call(migPlanCache, key)) {
    migSetSummaryState("cached", "#7f8c8d");
    migRenderSummary(migPlanCache[key]);
    return;
  }
  const run = function () {
    // guard again — the selection may have changed during the debounce
    if (!migSelectionComplete()) { migHideSummary(); return; }
    migShowSummaryLoading();
    migSetSummaryState("estimating…");
    $.ajax({
      type: "POST", url: `${MIG_API}/plan`, contentType: "application/json",
      data: JSON.stringify({ selection: migSelection() })
    }).done(function (plan) {
      const totals = plan.totals || {};
      migPlanCache[key] = totals;   // retain for re-show without re-querying
      migSetSummaryState("dry-run · nothing moved", "#27ae60");
      migRenderSummary(totals);
      migInitTooltips($("#mig_summary"));
    }).fail(function (xhr) {
      $("#mig_sum_loading").hide();
      $("#mig_sum_content").show();
      migSetSummaryState("estimate failed", "#c0392b");
      migLastPlanBytes = null;
      $("#mig_sum_eta").text("–");
      $("#mig_sum_eta_note").text((xhr.responseJSON && xhr.responseJSON.description) || ("HTTP " + xhr.status));
    });
  };
  if (immediate) run(); else migSummaryTimer = setTimeout(run, 350);
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
  migInitTooltips($("#migration_new"));

  // kind dropdown -> show the matching inputs + re-estimate
  $("#mig_kind").on("change", function () { migKindApply(); migLoadSummary(); });

  // source pool changes -> re-scope the path-prefix dropdown + re-estimate
  $("#mig_src_pool").on("change", function () { loadMigrationPathPrefixes(); migLoadSummary(); });

  // any other selection change -> re-estimate the summary (debounced)
  $("#mig_path_prefix, #mig_category, #mig_dst_pool").on("change", function () { migLoadSummary(); });

  // parallel / bwlimit -> recompute ETA only (no API call needed)
  $("#mig_parallel, #mig_bwlimit").on("input change", migRecalcEta);

  // opening the New-migration modal -> init tooltips + load the live estimate
  $("#mig_new_modal").on("shown.bs.modal", function () {
    migInitTooltips($("#mig_new_modal"));
    migLoadSummary();
  });

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

  // Preview = force an immediate re-estimate of the summary form.
  $("#mig_preview").on("click", function () { migLoadSummary(true); });

  // Create the migration; `startAfter` decides whether we also POST /start (so
  // "Create" leaves it idle for review, "Create & start" runs it immediately).
  function migCreate (startAfter) {
    const body = { selection: migSelection(), config: migCreateConfig() };
    $("#mig_create, #mig_create_only").prop("disabled", true);
    $.ajax({
      type: "POST", url: MIG_API, contentType: "application/json", data: JSON.stringify(body)
    }).done(function (mig) {
      $("#mig_preview_out").html('<span class="text-success"><i class="fa fa-check"></i> Migration created' +
        (startAfter ? " &amp; starting…" : " (idle — press Start to run)") + "</span>");
      // the matched disks start leaving their pool -> cached estimates are stale
      Object.keys(migPlanCache).forEach(function (k) { delete migPlanCache[k]; });
      $("#mig_new_modal").modal("hide");
      $("#mig_create, #mig_create_only").prop("disabled", false);
      if (startAfter) {
        $.ajax({ type: "POST", url: `${MIG_API}/${mig.id}/start` }).always(loadMigrations);
      } else {
        migToast("Migration created (idle) — press Start when ready", "success");
        loadMigrations();
      }
    }).fail(function (xhr) {
      $("#mig_create, #mig_create_only").prop("disabled", false);
      $("#mig_preview_out").html('<span class="text-danger"><i class="fa fa-exclamation-triangle"></i> Create failed: ' +
        migEscape((xhr.responseJSON && xhr.responseJSON.description) || xhr.status) + "</span>");
    });
  }
  $("#mig_create").on("click", function () { migCreate(true); });
  $("#mig_create_only").on("click", function () { migCreate(false); });

  // expand / collapse a migration
  $("#migrations").on("click", ".mig-row", function () {
    const id = $(this).data("mig");
    migExpanded[id] = !migExpanded[id];
    loadMigration(id);
  });

  // start / pause / cancel
  $("#migrations").on("click", ".mig-action", function (e) {
    e.stopPropagation();
    const $btn = $(this);
    if ($btn.prop("disabled")) return;
    const id = $btn.data("mig");
    const action = $btn.data("action");
    $btn.prop("disabled", true);
    $.ajax({ type: "POST", url: `${MIG_API}/${encodeURIComponent(id)}/${action}` })
      .done(function () {
        // pause/cancel take effect on the next reconciler tick (~60s), so give
        // immediate confirmation instead of a silently unchanged row.
        migToast(`${action} requested — applies on the next cycle`, "success");
        loadMigration(id);
      })
      .fail(function (xhr) {
        migToast(`${action} failed: ` + ((xhr.responseJSON && xhr.responseJSON.description) || ("HTTP " + xhr.status)), "danger");
        $btn.prop("disabled", false);
      });
  });

  // Log: fetch the CSV authenticated (an <a href> would hit apiv4 without the
  // admin token) and save it client-side as a Blob.
  $("#migrations").on("click", ".mig-log", function (e) {
    e.stopPropagation();
    const id = $(this).data("mig");
    $.ajax({ type: "GET", url: `${MIG_API}/${encodeURIComponent(id)}/log?format=csv`, dataType: "text" })
      .done(function (csv) {
        const blob = new Blob([csv || ""], { type: "text/csv;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = `migration-${id}.csv`;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
      })
      .fail(function (xhr) {
        migToast("Log download failed: " + ((xhr.responseJSON && xhr.responseJSON.description) || ("HTTP " + xhr.status)), "danger");
      });
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
      quarantine_after: parseInt($f.find(".cfg-quarantine-after").val(), 10) || 3,
      max_bytes_per_occurrence: migGbToBytes($f.find(".cfg-budget-gb").val()),
      min_free_bytes: migGbToBytes($f.find(".cfg-minfree-gb").val())
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
        const err = d.error
          ? `<span class="text-danger" title="${migEscape(d.error)}" data-toggle="tooltip"><i class="fa fa-exclamation-circle"></i> ${migEscape(d.error)}</span>`
          : "";
        h += `<tr><td>${migShortId(d.storage_id)}</td><td>${migEscape(d.kind || "")}</td>
          <td>${migEscape(d.state)}</td><td>${migBytes(d.size_bytes)}</td><td>${err}</td></tr>`;
      });
      h += "</tbody></table></td></tr>";
      $row.after(h);
      migInitTooltips($row.next("tr.mig-disks"));
    });
  });

  // Load the shared /administrators SocketIO connector; it calls
  // connection_done() on connect and we bind our handler in socketio_on().
  $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on);
});
