/*
 * Copyright 2025 the Isard-vdi project authors:
 *      Josep Maria Viñolas Auquer
 *      Alberto Larraz Dalmases
 * License: AGPLv3
 */

$(document).ready(function () {

  operations_table = $('#operations').DataTable({
    "ajax": {
      "url": "/api/v3/operations/hypervisors",
      "contentType": "application/json",
      "type": 'GET',
      "error": function (xhr, error, thrown) {
        if (xhr.status === 500) {
          $('#operations tbody').html('<tr class="odd"><td valign="top" colspan="7" class="dataTables_empty"><i class="fa fa-exclamation-triangle" style="color:red; font-size: 1.5em;"></i> Isard operations not available or not functional, review its logs</td></tr>');
        }
      }
    },
    "sAjaxDataProp": "",
    "language": {
      "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
    },
    "rowId": "id",
    "deferRender": true,
    "columns": [
      {
        className: 'actions-control',
        orderable: false,
        data: null,
        width: '65px',
        visible: $('meta[id=user_data]').attr('data-role') === 'admin',
        render: function (data, type, row, meta) {
          if (data.state === "AVAILABLE_TO_CREATE") {
            return `<button type="button" id="btn-start" class="btn btn-xs btn-start" title="Start hypervisor">
      <i class="fa fa-play"></i>
    </button>`;
          } else if (
            data.state === "AVAILABLE_TO_DESTROY" &&
            (!data.started_desktops || data.started_desktops == 0) // No desktops started
          ) {
            return `<button type="button" id="btn-stop" class="btn btn-xs btn-stop" title="Stop hypervisor">
      <i class="fa fa-stop" style="color:darkred"></i>
    </button>`;
          }
          return ``;
        }
      },
      { "data": "id" },
      { "data": "isard_state" },
      { "data": "state" },
      { "data": "desktops_started" },
      { "data": "only_forced" },
      { "data": "destroy_time" },
    ],
    "columnDefs": [
      {
        // Status
        "targets": 2,
        "render": function (data, type, full, meta) {
          console.log(full.isard_state)
          return renderStatus(full);
        }
      },
      {
        // Destroy Time
        "targets": 6,
        "render": function (data, type, full, meta) {
          if (full.hasOwnProperty("destroy_time") && full.destroy_time != "-") {
            return formatTimestampUTC(full.destroy_time)
          } else {
            return '<p>No destroy time</p>'
          }
        }
      },
    ],
    // "rowCallback": function (row, data, dataIndex) {
    //   if (data.state != "AVAILABLE_TO_CREATE") {
    //     $(row).css({ "background-color": "#FFDDDD" })
    //   } else {
    //     $(row).css({ "background-color": "#d4edda" })
    //   }
    // },
    "order": [
      [1, 'asc']
    ]
  });


  $('#operations tbody').on('click', 'button', function (e) {
    tr = $(this).closest("tr");
    data = operations_table.row($(this).parents('tr')).data();
    row = operations_table.row(tr)
    switch ($(this).attr('id')) {
      case 'btn-start':
        new PNotify({
          title: "<b>WARNING</b>",
          type: "error",
          text: "Are you sure you want to start hypervisor " + data["id"] + "? ",
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
            url: "/api/v3/operations/hypervisor/" + data["id"],
            data: JSON.stringify({}),
            contentType: "application/json",
            success: function (data) {
              new PNotify({
                title: 'Hypervisor started',
                text: 'Hypervisor ' + data["id"] + ' started',
                hide: true,
                delay: 7000,
                icon: 'fa fa-' + data.icon,
                opacity: 1,
                type: change == "enable" ? 'warning' : 'success'
              });
              operations_table.ajax.reload();
            },
            error: function (xhr, ajaxOptions, thrownError) {
              new PNotify({
                title: "ERROR starting hypervisor",
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
      case 'btn-stop':
        new PNotify({
          title: "<b>WARNING</b>",
          type: "error",
          text: "Are you sure you want to stop hypervisor " + data["id"] + "? ",
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
            type: "DELETE",
            url: "/api/v3/operations/hypervisor/" + data["id"],
            data: JSON.stringify({}),
            contentType: "application/json",
            success: function (data) {
              new PNotify({
                title: 'Hypervisor stopped',
                text: 'Hypervisor ' + data["id"] + ' stopped',
                hide: true,
                delay: 7000,
                icon: 'fa fa-' + data.icon,
                opacity: 1,
                type: change == "enable" ? 'warning' : 'success'
              });
              operations_table.ajax.reload();
            },
            error: function (xhr, ajaxOptions, thrownError) {
              new PNotify({
                title: "ERROR stopping hypervisor",
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
    }
  });
});


function renderStatus(data) {
  icon = data.icon;
  console.log(data.isard_state)
  switch (data.isard_state) {
    case 'Online':
      icon = '<i class="fa fa-power-off fa-2x" style="color:green"></i>';
      break;
    case 'Offline':
      icon = '<i class="fa fa-power-off fa-2x" style="color:black"></i>';
      break;
    case 'Error':
      icon = '<i class="fa fa-exclamation-triangle fa-2x" style="color:lightred"></i>';
      break;
    case 'TryConnection':
      icon = '<i class="fa fa-spinner fa-pulse fa-2x" style="color:lighblue"></i>';
      break;
    case 'ReadyToStart':
      icon = '<i class="fa fa-thumbs-up fa-2x fa-fw" style="color:lightblue"></i>';
      break;
    case 'StartingThreads':
      icon = '<i class="fa fa-cogs fa-2x" style="color:lightblue"></i>';
      break;
    case 'Blocked':
      icon = '<i class="fa fa-lock fa-2x" style="color:lightred"></i>';
      break;
    case 'DestroyingDomains':
      icon = '<i class="fa fa-bomb fa-2x" style="color:lightred"></i>';
      break;
    case 'StoppingThreads':
      icon = '<i class="fa fa-hand-stop-o fa-2x" style="color:lightred"></i>';
      break;
    case 'Deleting':
      icon = '<i class="fa fa-spinner fa-pulse fa-2x" style="color:lighblue"></i>';
      break;
    case '-':
      return '-';
      break;
    default:
      icon = '<i class="fa fa-question fa-2x" style="color:lightred"></i>'
  }
  if ("orchestrator_managed" in data && data.orchestrator_managed == true) {
    icon = icon + '<i class="fa fa-magic fa-1x" style="color:rgb(166, 144, 238)"></i>';
  }
  return icon + '<br>' + data.isard_state;
}