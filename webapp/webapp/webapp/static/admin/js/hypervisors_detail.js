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

function renderBtnEnable(data) {
  if (data.available == false) {
    return 'Pool not in hypervisor'
  }
  if (data.enabled == false) {
    return 'Disabled storage pool'
  }
  let color = data.enabled_virt_pool ? 'green' : 'darkgray'
  let active = data.enabled_virt_pool ? 'In use' : 'Inactive'
  return '<button id="btn-enable-virt_pools" class="btn btn-xs" type="button" data-placement="top" ><i class="fa fa-power-off" style="color:' + color + '"></i></button> ' + active

}

function setVirtPoolsTable(id) {
  virt_pools_table = $("#virt_pools-table-" + id).DataTable({
    "language": {
      "loadingRecords": "Virtualization pools information still not available"
    },
    "ajax": {
      "url": "/api/v3/hypervisor/" + id + "/virt_pools",
      "contentType": "application/json",
      "type": 'GET',
    },
    "sAjaxDataProp": "",
    "rowId": "id",
    "deferRender": true,
    "columns": [
      { "data": "enabled_virt_pool" },
      { "data": "name" },
      { "data": "id" },
      { "data": "categories" },
    ],
    "columnDefs": [{
      'targets': 0,
      "render": function (data, type, full, meta) {
        return renderBtnEnable(full)
      }
    }],
    "order": [0, 'desc'],
    "rowCallback": function (row, data) {
      if (data.available == false) {
        $(row).css("background-color", "lightgray");
        $(row).css("color", "black")
        return
      }
      if (data.enabled == false) {
        $(row).css("background-color", "darkgray");
        $(row).css("color", "white")
        return
      }
      if (data.enabled_virt_pool == false) {
        $(row).css("background-color", "white");
        $(row).css("color", "black")
      } else {
        $(row).css("background-color", "lightgreen");
        $(row).css("color", "black")
      }
    }
  });

  virt_pools_table.on('click', 'button', function (e) {
    tr = $(this).closest("tr");
    data = virt_pools_table.row($(this).parents('tr')).data();
    row = virt_pools_table.row(tr)
    switch ($(this).attr('id')) {
      case 'btn-enable-virt_pools':
        let change = data.available ? "disable" : "enable";
        new PNotify({
          title: "<b>WARNING</b>",
          type: "warning",
          text: "Are you sure you want to <b>" + change + "</b> pool <b>" + row.data().name + "</b>? ",
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
            "url": "/api/v3/hypervisor/" + id + "/virt_pools",
            data: JSON.stringify({ 'id': row.data().id, 'enable_virt_pool': !row.data().enabled_virt_pool }),
            contentType: "application/json",
            success: function (data) {
              new PNotify({
                title: 'Virt pool ' + change + 'd successfully',
                text: '',
                hide: true,
                delay: 7000,
                icon: 'fa fa-' + data.icon,
                opacity: 1,
                type: change == "enable" ? 'warning' : 'success'
              });
              virt_pools_table.ajax.reload();
            },
            error: function (xhr, ajaxOptions, thrownError) {
              new PNotify({
                title: "ERROR updating virt pool",
                text: xhr.responseJSON.description,
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
    }
  });
}