/*
*   Copyright © 2026 Josep Maria Viñolas Auquer
*
*   This file is part of IsardVDI.
*
*   IsardVDI is free software: you can redistribute it and/or modify
*   it under the terms of the GNU Affero General Public License as published by
*   the Free Software Foundation, either version 3 of the License, or (at your
*   option) any later version.
*
*   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
*   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
*   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
*   details.
*
*   You should have received a copy of the GNU Affero General Public License
*   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
*
* SPDX-License-Identifier: AGPL-3.0-or-later
*/

const SWEEP_JOB_ID = "system.storage_pending_actions_sweep";
const GIB = 1024 * 1024 * 1024;

$(document).ready(function () {
    loadSweepConfig();
    $("#sweep-save").on("click", saveSweepConfig);
});

function setChecked(id, value) {
    var $el = $("#" + id).prop("checked", !!value);
    try { $el.iCheck(value ? "check" : "uncheck").iCheck("update"); } catch (e) { }
}

function loadSweepConfig() {
    $.ajax({
        type: "GET",
        url: "/api/v4/admin/storage/sweep/config",
        accept: "application/json",
    }).done(function (c) {
        setChecked("sweep-enabled", c.enabled);
        setChecked("sweep-sparsify", c.sparsify);
        setChecked("sweep-repair-leaks", c.repair_leaks);
        setChecked("sweep-check-integrity", c.check_integrity);
        $("#sweep-hour").val(c.hour);
        $("#sweep-minute").val(c.minute);
        $("#sweep-max-disks").val(c.max_disks);
        $("#sweep-max-gib").val(Math.floor((c.max_bytes || 0) / GIB));
        $("#sweep-check-age").val(c.check_max_age_days);
    });
}

function saveSweepConfig() {
    var enabled = $("#sweep-enabled").is(":checked");
    var hour = parseInt($("#sweep-hour").val()) || 0;
    var minute = parseInt($("#sweep-minute").val()) || 0;
    var data = {
        enabled: enabled,
        hour: hour,
        minute: minute,
        max_disks: parseInt($("#sweep-max-disks").val()) || 0,
        max_bytes: (parseInt($("#sweep-max-gib").val()) || 0) * GIB,
        sparsify: $("#sweep-sparsify").is(":checked"),
        repair_leaks: $("#sweep-repair-leaks").is(":checked"),
        check_integrity: $("#sweep-check-integrity").is(":checked"),
        check_max_age_days: parseInt($("#sweep-check-age").val()) || 30,
    };
    $.ajax({
        type: "PUT",
        url: "/api/v4/admin/storage/sweep/config",
        data: JSON.stringify(data),
        contentType: "application/json",
    }).done(function () {
        updateSweepSchedulerJob(enabled, hour, minute);
        new PNotify({
            title: "Saved",
            text: "Storage sweep settings saved",
            hide: true, delay: 1500, opacity: 1, type: "success",
        });
    }).fail(function (d) {
        new PNotify({
            title: "ERROR saving sweep settings",
            text: d.responseJSON ? d.responseJSON.description : "Something went wrong",
            type: "error", hide: true, icon: "fa fa-warning", delay: 5000, opacity: 1,
        });
    });
}

function updateSweepSchedulerJob(enabled, hour, minute) {
    // Reconcile the cron with the saved config: drop any existing job, then
    // re-add it at the chosen time only while the sweep is enabled.
    $.ajax({ type: "DELETE", url: "/scheduler/" + SWEEP_JOB_ID }).always(function () {
        if (!enabled) return;
        $.ajax({
            type: "POST",
            url: "/scheduler/system/cron/storage_pending_actions_sweep/" + hour + "/" + minute + "/" + SWEEP_JOB_ID,
            data: JSON.stringify({}),
            contentType: "application/json",
        });
    });
}
