/*
 * Copyright 2017 the Isard-vdi project authors:
 *      Josep Maria Viñolas Auquer
 *      Alberto Larraz Dalmases
 * License: AGPLv3
 */

$(document).ready(function() {
  orchestrator_hypers_table = $('#orchestrator_hypervisors').DataTable({
    "ajax": {
      "url": "/api/v3/hypervisors/orchestrator_managed",
      "data": function(d) { return JSON.stringify({ 'order_by': 'id' }) },
      "contentType": "application/json",
      "type": 'POST'
    },
    "sAjaxDataProp": "",
    "language": {
      "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
    },
    "rowId": "id",
    "deferRender": true,
    "columns": [
      { "data": "id", "width": "10px", "defaultContent": "" },
      { "data": "destroy_time", "width": "10px" },
      { "data": "info.memory_in_MB", "width": "10px", "defaultContent": 'NaN' },
      { "data": "info.cpu_cores", "width": "10px", "defaultContent": 'NaN' },
      { "data": "desktops_started", "width": "10px", "defaultContent": 0 },
      { "data": "status_time", "width": "10px" },
    ],
    "order": [
      [0, 'asc']
    ],
    "columnDefs": [
      {
        // ID
        "targets": 0,
        "render": function(data, type, full, meta) {
          return full.id
        }
      },
      {
        // Destroy Time
        "targets": 1,
        "render": function(data, type, full, meta) {
          if (full.hasOwnProperty("destroy_time") && full.destroy_time) {
            return formatTimestampUTC(full.destroy_time)
          } else {
            return '<p>No destroy time</p>'
          }
        }
      },
      {
        // RAM
        "targets": 2,
        "render": function(data, type, full, meta) {
          if (!("stats" in full)) { return '<i class="fa fa-spinner fa-lg fa-spin"></i>' }
          if (!("min_free_mem_gb" in full)) { full.min_free_mem_gb = 0 }
          var ms = full.stats.mem_stats
          var mem_used = ms.used != null ? ms.used : (ms.total - ms.available)
          var perc = ms.total > 0 ? mem_used * 100 / ms.total : 0
          var label = Math.round(mem_used/1024/1024)+'GB/'+Math.round(ms.total/1024/1024)+'GB'
          if (ms.hugepages_total_kb > 0) {
            var hp_used = Math.round((ms.hugepages_used_kb != null ? ms.hugepages_used_kb : (ms.hugepages_total_kb - ms.hugepages_free_kb)) / 1024 / 1024)
            var hp_total = Math.round(ms.hugepages_total_kb / 1024 / 1024)
            label += ' <span style="color:#8a6d3b;" title="Hugepages: ' + hp_total + 'GB reserved, ' + hp_used + 'GB in use by VMs">(HP:' + hp_used + '/' + hp_total + 'GB)</span>'
          }
          return label + renderProgress(Math.round(perc), 70, Math.round((ms.total-full.min_free_mem_gb*1024*1024)*100/ms.total))
        }
      },
      {
        // CPU
        "targets": 3,
        "render": function(data, type, full, meta) {
          if (full.info) {
            if (!("stats" in full)) { return '<i class="fa fa-spinner fa-lg fa-spin"></i>' }
            return full.info.cpu_cores+"c/"+full.info.cpu_cores * full.info.threads_x_core+"th "+renderProgress(Math.round(full.stats.cpu_1min.used),20,40)
          }
        }
      },
      {
        // Desktops
        "targets": 4,
        "render": function(data, type, full, meta) {
          if (full.status != "Online") {
            return "0"
          }
          return data
        }
      },
      {
        // Last Status Change
        "targets": 5,
        "render": function(data, type, full, meta) {
          return moment.unix(full.status_time).fromNow()
        }
      },
    ],
  });
});
