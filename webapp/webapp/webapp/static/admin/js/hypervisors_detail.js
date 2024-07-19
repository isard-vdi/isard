$(document).ready(function () {

  /////////////// DOMAINS STATUS EVENTS
  waitDefined("socket", function () {
    socket.on('domain_stats', function (data) {
      var data = JSON.parse(data);
      if ($('#domains-table-' + data.hyp_started).is(':visible')) {
        dtUpdateInsert(domains_table[data.hyp_started], data, false)
      }
    });

    socket.on('domain_stats_stopped', function (data) {
      var data = JSON.parse(data);
      if ($('#domains-table-' + data.hyp_started).is(':visible')) {
        var row = domains_table[data.hyp_started].row('#' + data.id).remove().draw();
      }
    });
  })
});

//////// DOMAINS STATUS EVENTS

domains_table = {}

function tableHypervisorDomains(hyp) {
  domains_table[hyp] = $('#domains-table-' + hyp).DataTable({
    "language": {
      "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
    },
    "ajax": {
      "url": "/api/v3/hypervisor/started_domains/" + hyp,
      "contentType": "application/json",
      "type": 'GET',
    },
    "sAjaxDataProp": "",
    "rowId": "id",
    "deferRender": true,
    "columns": [
      { "data": "name" },
      { "data": "create_dict.hardware.vcpus" },
      {
        "data": "ram", "width": "100px",
        "render": function (data, type, full, meta) {
          return (full.create_dict.hardware.memory / 1024 / 1024).toFixed(2) + "GB"
        }
      },
      { "data": "username" },
      { "data": "category_name" },
      { "data": "group_name" },
      {
        "data": "server", "width": "10px", "defaultContent": "-", "render": function (data, type, full, meta) {
          if ('server' in full) {
            if (full["server"] == true) {
              if (full["server_autostart"]) {
                return "AUTO"
              } else {
                return 'SERVER';
              }

            } else {
              return '-';
            }
          } else {
            return '-';
          }
        }
      },
      {
        "data": "persistent", "render": function (data) {
          if (data == false) {
            return '<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>'
          } else {
            return `<i class="fa fa-circle" aria-hidden="true"  style="color:green"></i>`
          }
        }
      },
      { "data": "id", "visible": false }
    ],
    "order": [0, 'asc'],
  });
  adminShowIdCol(domains_table[hyp], 'domains-table-' + hyp)
}

function setMountpoints(id) {
  mountpoint_table = $("#table-mountpoints-" + id).DataTable({
    "language": {
      "loadingRecords": "Mountpoints information still not available"
    },
    "ajax": {
      "url": "/api/v3/hypervisor/mountpoints/" + id,
      "contentType": "application/json",
      "type": 'GET',
    },
    "sAjaxDataProp": "",
    "rowId": "id",
    "deferRender": true,
    "columns": [
      { "data": "mount" },
      { "data": "usage" }
    ],
    "columnDefs": [{
      'targets': 1,
      "render": function (data, type, full, meta) {
        return data + '%'
      }
    }],
    "order": [0, 'desc'],
    "rowCallback": function (row, data) {
      if (data.usage > 90) {
        $(row).css("background-color", "rgba(217,83,79,0.85)");
        $(row).css("color", "white")
      } else if (data.usage > 90 && data.usage < 95) {
        $(row).css("background-color", "rgba(240,173,78,0.85)");
      }
    }
  });
}