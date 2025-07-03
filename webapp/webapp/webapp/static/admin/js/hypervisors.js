/*
 * Copyright 2017 the Isard-vdi project authors:
 *      Josep Maria Viñolas Auquer
 *      Alberto Larraz Dalmases
 * License: AGPLv3
 */

interval = 5000;
engine_status_data = ""
$hypervisor_template = $(".hyper-detail");

$(document).ready(function () {
  update_engine_status();
  $('.btn-new-hyper').on('click', function () {
    $("#checkbox_add_error").hide()
    $('#modalAddHyper').modal({
      backdrop: 'static',
      keyboard: false
    }).modal('show');
    $("#modalAddHyper #hypervisors_pools_dropdown").find('option').remove();

    $.ajax({
      url: "/admin/table/hypervisors_pools",
      type: "POST",
      data: JSON.stringify({ 'order_by': 'name' }),
      contentType: "application/json",
      success: function (pools) {
        $.each(pools, function (key, value) {
          $("#modalAddHyper #hypervisors_pools_dropdown").append('<option value=' + value.id + '>' + value.name + '</option>');
        });
      },
      error: function (jqXHR, exception) {
        processError(jqXHR, form)
      }
    });

    $('#modalAddHyper #modalAdd #hostname').val(window.location.hostname)
    $('#modalAddHyper #modalAdd #user').val('root')
    $('#modalAddHyper #modalAdd #port').val(2022)
    $('#modalAddHyper #modalAdd #capabilities-disk_operations').iCheck('check')
    $('#modalAddHyper .capabilities_hypervisor').on('ifChecked', function (event) {
      $("#checkbox_add_error").hide()
      $('#viewer_fields').show()
      $('#modalAddHyper #viewer-static').val($('#modalAddHyper #modalAdd #hostname').val());
      $('#modalAddHyper #viewer-proxy_video').val($('#modalAddHyper #modalAdd #hostname').val());
      $('#modalAddHyper #viewer-proxy_hyper_host').val('isard-hypervisor');
      $('#modalAddHyper #viewer-hyper_vpn_host').val('isard-hypervisor');
    });

    $('#modalAddHyper .capabilities_disk_operations').on('ifChecked', function (event) {
      $("#checkbox_add_error").hide()
    });

    $('#modalAddHyper .capabilities_hypervisor').on('ifUnchecked', function (event) {
      $('#modalAddHyper #viewer_fields').hide()
      $('#modalAddHyper #modalAddHyper #viewer-static').val('');
      $('#modalAddHyper #modalAddHyper #viewer-proxy_video').val('');
      $('#modalAddHyper #modalAddHyper #viewer-proxy_hyper_host').val(0);
    });
  });

  $("#modalAddHyper #send").on('click', function (e) {
    var form = new FormData()
    form.append('hyper_id', $('#modalAddHyper #modalAdd #id').val())
    form.append('description', $('#modalAddHyper #modalAdd textarea[name="description"]').val())
    form.append('hostname', $('#modalAddHyper #modalAdd #hostname').val())
    form.append('user', $('#modalAddHyper #modalAdd #user').val())
    form.append('port', $('#modalAddHyper #modalAdd #port').val())
    form.append('cap_hyper', $('#modalAddHyper #modalAdd #capabilities-hypervisor').prop('checked'))
    form.append('cap_disk', $('#modalAddHyper #modalAdd #capabilities-disk_operations').prop('checked'))
    form.append('isard_static_url', $('#modalAddHyper #modalAdd #viewer-static').val())
    form.append('isard_video_url', $('#modalAddHyper #modalAdd #viewer-proxy_video').val())
    form.append('spice_port', $('#modalAddHyper #modalAdd #viewer-spice_ext_port').val())
    form.append('browser_port', $('#modalAddHyper #modalAdd #viewer-html5_ext_port').val())
    form.append('isard_proxy_hyper_url', $('#modalAddHyper #modalAdd #viewer-proxy_hyper_host').val())
    form.append('isard_hyper_vpn_host', $('#modalAddHyper #modalAdd #viewer-hyper_vpn_host').val())
    form.append('enabled', false)

    $('#modalAddHyper #modalAdd').parsley().validate();
    if ($('#modalAddHyper #modalAdd').parsley().isValid()) {
      if (!$('#modalAddHyper #modalAdd #capabilities-hypervisor').prop('checked') && !$('#modalAddHyper #modalAdd #capabilities-disk_operations').prop('checked')) {
        $("#checkbox_add_error #checkbox_add_error_html").html("You must select at least one option");
        $("#checkbox_add_error").show();
      } else {
        $("#checkbox_edit_error").hide();
        $.ajax({
          type: "POST",
          url: "/api/v3/hypervisor",
          data: form,
          processData: false,
          contentType: false,
          success: function (data) {
            $('form').each(function () { this.reset() });
            $('.modal').modal('hide');
          },
          error: function (xhr, ajaxOptions, thrownError) {
            if (xhr.status == 404) {
              new PNotify({
                title: "ERROR creating hypervisor",
                text: xhr.responseJSON.description,
                hide: true,
                delay: 3000,
                icon: 'fa fa-warning',
                opacity: 1,
                type: 'error'
              });
            }
          }
        });
      }
    }
  });
  renderBoolean = (enabled, type) => {
    if (type === 'display') {
      if (enabled) {
        return '<i class="fa fa-circle" aria-hidden="true" style="color:green"></i>'
      } else {
        return '<i class="fa fa-circle" aria-hidden="true" style="color:darkgray"></i>'
      }
    }
    return enabled
  }

  table = $('#hypervisors').DataTable({
    "ajax": {
      "url": "/api/v3/hypervisors",
      "contentType": "application/json",
      "type": 'GET'
    },
    "sAjaxDataProp": "",
    "language": {
      "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
    },
    "rowId": "id",
    "deferRender": true,
    "columns": [{
      "className": 'details-control',
      "orderable": false,
      "data": null,
      "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
    },
    { "data": "enabled" },
    { "data": "status" },
    { "data": "cap_status.disk_operations" },
    { "data": "cap_status.hypervisor" },
    { "data": "only_forced" },
    { "data": "gpu_only", "defaultContent": 0 },
    { "data": "id", "width": "100px" },
    { "data": "hostname", "width": "100px", "className": 'group-system', "visible": false },
    { "data": "info.memory_in_MB", "width": "600px", "defaultContent": 'NaN' },
    { "data": "info.cpu_cores", "width": "600px", "defaultContent": 'NaN' },
    { "data": "status_time", "className": 'group-system', "visible": false },
    { "data": "desktops_started", "defaultContent": 0 },
    {
      "data": "gpus", "defaultContent": 0, render: function (data, type, row) {
        var physical_gpus = row.gpus.filter(function (gpu) {
          return row.physical_gpus.includes(gpu);
        });
        return data.sort().toString() == physical_gpus.sort().toString() ? data.length :
          `<i title="This hypervisor is assigned to ${data.length} GPUs but there is only ${physical_gpus.length} physical GPUs. These GPUs do not correspond:
             \n${data.filter(gpu => !physical_gpus.includes(gpu))
            .concat(physical_gpus.filter(gpu => !data.includes(gpu)))}" class="fa fa-warning" style="color:red;">
            ${physical_gpus.length + "/" + data.length}</i>`
      }
    },
    { "data": "viewer.static", "className": 'group-system', "visible": false },
    { "data": "viewer.proxy_video", "className": 'group-system', "visible": false },
    { "data": "vpn.wireguard.connected", "defaultContent": 'NaN', "className": 'group-system', "visible": false },
    { "data": "info.nested", "defaultContent": 'NaN', "className": 'group-system', "visible": false },
    { "data": "info.virtualization_capabilities", "defaultContent": 'NaN', "className": 'group-system', "visible": false },
    { "data": "info.qemu_version", "defaultContent": 'NaN', "className": 'group-system', "visible": false },
    { "data": "info.libvirt_version", "defaultContent": 'NaN', "className": 'group-system', "visible": false },
    { "data": "stats.last_action.action", "width": "100px", "className": 'group-stats', "visible": false },
    { "data": "stats.last_action.action_time", "className": 'group-stats', "visible": false },
    { "data": "stats.last_action.intervals", "className": '-group-stats', "visible": false },
    { "data": "stats.positioned_items", "className": 'group-stats', "visible": false },
    ],
    "order": [
      [7, 'asc']
    ],
    "columnDefs": [{
      // Enabled
      "targets": 1,
      "render": function (data, type, full, meta) {
        return renderEnabled(full);
      }
    },
    {
      // Status
      "targets": 2,
      "render": function (data, type, full, meta) {
        return renderStatus(full);
      }
    },
    { // Disk Operations
      "targets": 3,
      "render": function (data, type, full, meta) {
        if ("capabilities" in full && "disk_operations" in full.capabilities) {
          if (full.capabilities.disk_operations) {
            if ("cap_status" in full && "disk_operations" in full.cap_status) {
              if (full.cap_status.disk_operations) {
                return renderBoolean(true, type);
              } else {
                return type === 'display' ? '<i class="fa fa-circle" aria-hidden="true" style="color:red"></i>' : 'no disk operations'
              }
            } else {
              return '<i class="fa fa-spinner fa-lg fa-spin"></i>'
            }
          }
        }
        return renderBoolean(false, type);
      },
    },
    { // Hypervisor
      "targets": 4,
      "render": function (data, type, full, meta) {
        if ("capabilities" in full && "hypervisor" in full.capabilities) {
          if (full.capabilities.hypervisor) {
            if ("cap_status" in full && "hypervisor" in full.cap_status) {
              if (full.cap_status.hypervisor) {
                return renderBoolean(true, type);
              } else {
                return '<i class="fa fa-circle" aria-hidden="true" style="color:red"></i>'
              }
            } else {
              return '<i class="fa fa-spinner fa-lg fa-spin"></i>'
            }
          }
        }
        return renderBoolean(false, type);
      },
    },
    {
      //Only Forced
      "targets": 5,
      "render": renderBoolean
    },
    {
      //Only GPU
      "targets": 6,
      "render": function (data, type, full, meta) {
        if (!("min_free_gpu_mem_gb" in full)) { return renderBoolean(data, type) }
        if (full.min_free_gpu_mem_gb == 0) { return renderBoolean(data, type) }
        if (data) {
          return '<p title="Set to reserve ' + full.min_free_gpu_mem_gb + ' GB of ram for GPU desktops. Now allowing only GPU desktops.">Auto ' + renderBoolean(data, type) + '</p>'
        } else {
          return '<p title="Set to reserve ' + full.min_free_gpu_mem_gb + ' GB of ram for GPU desktops. Now allowing all.">Auto ' + renderBoolean(data, type) + '</p>'
        }
      }
    },
    {
      // RAM
      "targets": 9,
      "render": function (data, type, full, meta) {
        if (!("stats" in full)) { return '<i class="fa fa-spinner fa-lg fa-spin"></i>' }
        if (!("min_free_mem_gb" in full)) { full.min_free_mem_gb = 0 }
        mem_used = (full.stats.mem_stats.total - full.stats.mem_stats.available)
        perc = mem_used * 100 / full.stats.mem_stats.total
        return Math.round(mem_used / 1024 / 1024) + 'GB/' + Math.round(full.stats.mem_stats.total / 1024 / 1024) + 'GB' + renderProgress(Math.round(perc), 70, Math.round((full.stats.mem_stats.total - full.min_free_mem_gb * 1024 * 1024) * 100 / full.stats.mem_stats.total))
      }
    },
    {
      // CPU
      "targets": 10,
      "render": function (data, type, full, meta) {
        if (full.info) {
          if (!("stats" in full)) { return '<i class="fa fa-spinner fa-lg fa-spin"></i>' }
          return full.info.cpu_cores + "c/" + full.info.cpu_cores * full.info.threads_x_core + "th " + renderProgress(Math.round(full.stats.cpu_1min.used), 20, 40)
        }
      }
    },
    {
      // Last Status Change
      "targets": 11,
      "render": function (data, type, full, meta) {
        return moment.unix(full.status_time).fromNow();
      }
    },
    {
      // Desktops
      "targets": 12,
      "render": function (data, type, full, meta) {
        if (full.status != "Online") {
          return "0"
        }
        return data
      }
    },
    {
      // GPUs
      "targets": 13,
      "render": function (data, type, full, meta) {
        if (full.physical_gpus == data) {
          return data
        } else {
          return `<i title="Number of GPUs doesn't match the physical GPUs" class="fa fa-warning" style="color:red;"> ${data}</i> `
        }
      }
    },
    {
      // Static
      "targets": 14,
      "render": function (data, type, full, meta) {
        if ("viewer_status" in full) {
          if (full.viewer_status.static) {
            return '<i class="fa fa-circle" aria-hidden="true" style="color:green"> Expires in ' + full.viewer_status.static + ' days</i>  ' + data
          } else {
            return '<i class="fa fa-circle" aria-hidden="true" style="color:red"> ERROR: Expired certificate or connection error</i>  ' + data
          }
        } else {
          return '<i class="fa fa-spinner fa-lg fa-spin"></i>  ' + data
        }
      }
    },
    {
      // Proxy Video
      "targets": 15,
      "render": function (data, type, full, meta) {
        if ("viewer_status" in full) {
          title = "HTML5 cert: " + full.viewer_status.html5 + " days\nSpice cert: " + full.viewer_status.spice + " days\nStatic cert: " + full.viewer_status.static + " days"
          if (full.viewer_status.html5 && full.viewer_status.spice && full.viewer_status.static) {
            return '<i class="fa fa-circle" aria-hidden="true" style="color:green" title="' + title + '"> Expires in ' + full.viewer_status.html5 + ' days</i>  ' + full.viewer.proxy_video + ' (' + full.viewer.spice_ext_port + ',' + full.viewer.html5_ext_port + ')'
          } else {
            return '<i class="fa fa-circle" aria-hidden="true" style="color:red" title="' + title + '"> ERROR Expired certificate or connection error</i>  ' + full.viewer.proxy_video + ' (' + full.viewer.spice_ext_port + ',' + full.viewer.html5_ext_port + ')'
          }
        }
        return '<i class="fa fa-spinner fa-lg fa-spin"></i>  ' + full.viewer.proxy_video + ' (' + full.viewer.spice_ext_port + ',' + full.viewer.html5_ext_port + ')'
      }
    },

    {
      // VPN
      "targets": 16,
      "render": renderBoolean
    },
    {
      // Nested
      "targets": 17,
      "render": renderBoolean
    },
    {
      // Virt
      "targets": 18,
      "render": function (data, type, full, meta) {
        if (!data) { return renderBoolean(data, type) }
        return data
      }
    },

    {
      // Last Action
      "targets": 21,
      "render": function (data, type, full, meta) {
        if (!("stats" in full)) {
          return '<i class="fa fa-spinner fa-lg fa-spin"></i>'
        }
        if (!("last_action" in full.stats)) {
          return '-'
        }
        if (type === 'display') {
          let actionMap =  {
            "start_domain": "Start",
            "stop_domain": "Stop",
          }
          let actionName = actionMap[full.stats.last_action.action] || full.stats.last_action.action

          let timeDiff = (moment().unix() - full.stats.last_action.timestamp).toFixed(3)
          if (timeDiff < 5) {
            return '<span title="Seconds since action: ' + timeDiff + '">' + '<i class="fa fa-circle" aria-hidden="true" style="color:red"></i> ' + actionName + '</span>'
          }
          return '<span title="Seconds since action: ' + timeDiff + '">' + actionName + '</span>'
        }
        return full.stats.last_action.action
      }
    },
    {
      // Action time
      "targets": 22,
      "render": function (data, type, full, meta) {
        if (!("stats" in full)) {
          return '<i class="fa fa-spinner fa-lg fa-spin"></i>'
        }
        if (!("last_action" in full.stats)) {
          return '-'
        }
        if (type === 'display') {
          let timeMap = {
            "red": 5, // over 3 seconds
            "orange": 2, // over 2 second
          }
          for (var color in timeMap) {
            if (full.stats.last_action.action_time.toFixed(3) > timeMap[color]) {
              return '<i class="fa fa-circle" aria-hidden="true" style="color:' + color + '"></i> ' + full.stats.last_action.action_time.toFixed(3)
            }
          }
          return full.stats.last_action.action_time.toFixed(3)
        }
        return full.stats.last_action.action_time
      }
    },
    {
      // Action intervals
      "targets": 23,
      "render": function (data, type, full, meta) {
        if (!("stats" in full)) {
          return '<i class="fa fa-spinner fa-lg fa-spin"></i>'
        }
        if (!("last_action" in full.stats)) {
          return '-'
        }
        if (type === 'display') {
          let table = '<table class="table table-bordered table-condensed table-striped" style="width:100%">'
          table += '<thead><tr><th>Action</th><th>Time</th></tr></thead>'
          table += '<tbody>'
          full.stats.last_action.intervals.forEach(function (obj) {
            table += '<tr>'
            table += '<td>' + Object.keys(obj)[0] + '</td>'
            table += '<td>' + obj[Object.keys(obj)[0]].toFixed(3) + '</td>'
            table += '</tr>'
          })
          table += '</tbody>'
          table += '</table>'
          return table
        }
        return data
      }
    },
    {
      // Queued actions
      "targets": 24,
      "render": function (data, type, full, meta) {
        if (!("stats" in full)) {
          return '<i class="fa fa-spinner fa-lg fa-spin"></i>'
        }
        if (!("positioned_items" in full.stats)) {
          full.stats.positioned_items = []
        }
        var dataLen = full.stats.positioned_items.length
        var dataLenGrouped = full.stats.positioned_items.reduce(function (acc, obj) {
          if (obj.event in acc) {
            acc[obj.event]++
          } else {
            acc[obj.event] = 1
          }
          return acc
        }, {})
        dataLenGoupString = ""
        for (var key in dataLenGrouped) {
          dataLenGoupString += key + ": " + dataLenGrouped[key] + ", \n"
        }

        return '<span style="cursor: help" title="' + dataLenGoupString + '">' + dataLen + '</span>'
      }
    }
    ],
    "rowCallback": function (row, data, dataIndex) {
      if (!("stats" in data)) { return '<i class="fa fa-spinner fa-lg fa-spin"></i>' }
      if (!("min_free_mem_gb" in data)) { data.min_free_mem_gb = 0 }
      mem_used = (data.stats.mem_stats.total - data.stats.mem_stats.available)
      perc = mem_used * 100 / data.stats.mem_stats.total
      if ('stats' in data) {
        if (data.stats.mem_stats.total - mem_used - data.min_free_mem_gb * 1024 * 1024 <= 0) {
          $(row).css({ "background-color": "#FFCCCB" })
        } else {
          $(row).css({ "background-color": "white" })
        }
      } else {
        $(row).css({ "background-color": "white" })
      }
    }
  });
  showUserExportButtons(table, 'hypervisors-buttons-row');

  $('#hypervisors').find('tbody').on('click', 'td.details-control', function () {
    var tr = $(this).closest('tr');
    var row = table.row(tr);

    if (row.child.isShown()) {
      // This row is already open - close it
      row.child.hide();
      row.child.remove();
      tr.removeClass('shown');
    } else {
      // Close other rows
      // Open this row
      row.child(formatHypervisorPanel(row.data())).show();
      tr.addClass('shown');
      $('#status-detail-' + row.data().id).html(row.data().detail);
      tableHypervisorDomains(row.data().id);
      setMountpoints(row.data().id);
      setHypervisorDetailButtonsStatus(row.data().id, row.data().status)
      actionsHyperDetail();
      setVirtPoolsTable(
        row.data().id,
        row.data().virt_pools || row.data().storage_pools || []
      );
    }
  });
  $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on)
})

function update_engine_status() {
  $.ajax({
    url: "/engine/status",
    type: "GET",
    accept: "application/json",
    contentType: "application/json",
    success: function (data) {
      if (engine_status_data != data) {
        engine_status_data = data
        $('#engine_status').html('<i class="fa fa-success" style="font-size:16px;color:green"> System Ready</i>')
      }
    },
    error: function (data) {
      if (engine_status_data != data.responseText) {
        engine_status_data = data.responseText
        $('#engine_status').html('<i class="fa fa-warning" style="font-size:16px;color:red"> System Error: ' + data.responseText + '</i>')
      }
    },
  });
  setTimeout(update_engine_status, interval);
}

function socketio_on() {
  socket.on('hyper_data', function (data) {
    var data = JSON.parse(data);
    data = { ...table.row("#" + data.id).data(), ...data }
    new_hyper = dtUpdateInsert(table, data, false);
    table.draw(false)
    if (new_hyper) { tablepools.draw(false); }
    setHypervisorDetailButtonsStatus(data.id, data.status)
    if ("orchestrator_managed" in data) {
      if (data.orchestrator_managed) {
        new_hyper = dtUpdateInsert(orchestrator_hypers_table, data, false);
        orchestrator_hypers_table.draw(false)
      }
    }
  });

  socket.on('hyper_deleted', function (data) {
    var data = JSON.parse(data);
    table.row('#' + data.id).remove().draw();
    orchestrator_hypers_table.ajax.reload()
    new PNotify({
      title: "Hypervisor deleted",
      text: "Hypervisor " + data.id + " has been deleted",
      hide: true,
      delay: 4000,
      icon: 'fa fa-success',
      opacity: 1,
      type: 'success'
    });
    tablepools.ajax.reload()
  });

  socket.on('add_form_result', function (data) {
    var data = JSON.parse(data);
    if (data.result) {
      $("#modalAddHyper #modalAdd")[0].reset();
      $("#modalAddHyper").modal('hide');
      $("#modalEditHyper #modalEdit")[0].reset();
      $("#modalEditHyper").modal('hide');
    }
    new PNotify({
      title: data.title,
      text: data.text,
      hide: true,
      delay: 4000,
      icon: 'fa fa-' + data.icon,
      opacity: 1,
      type: data.type
    });
    table.ajax.reload()
    orchestrator_hypers_table.ajax.reload()
    tablepools.ajax.reload()
  });

  socket.on('result', function (data) {
    var data = JSON.parse(data);
    new PNotify({
      title: data.title,
      text: data.text,
      hide: true,
      delay: 4000,
      icon: 'fa fa-' + data.icon,
      opacity: 1,
      type: data.type
    });
  });
}

function renderName(data) {
  return '<div class="block_content" > \
          <h4 class="title" style="height: 4px; margin-top: 0px;"> \
          <a>' + data.hostname + '</a> \
          </h4> \
          <p class="excerpt" >' + data.description + '</p> \
          </div>';
}


function formatHypervisorData(data) {
  return data;
}

function formatHypervisorPanel(d) {
  $newPanel = $hypervisor_template.clone();
  $newPanel.html(function (i, oldHtml) {
    return oldHtml.replace(/d.id/g, d.id);
  });
  return $newPanel
}

function setHypervisorDetailButtonsStatus(id, status) {
  if (status == 'Online') {
    $('#actions-domains-' + id + ' *[class^="btn"]').prop('disabled', false);
  } else {
    $('#actions-domains-' + id + ' *[class^="btn"]').prop('disabled', true);
  }

  if (status == 'Offline' || status == 'Error') {
    $('#actions-delete-' + id + ' .btn-delete').prop('disabled', false);
    $('#actions-delete-' + id + ' .btn-edit').prop('disabled', false);
  } else {
    $('#actions-delete-' + id + ' .btn-delete').prop('disabled', true);
    $('#actions-delete-' + id + ' .btn-edit').prop('disabled', true);
  }

  if (status == 'Deleting') {
    $('#actions-enable-' + id + ' *[class^="btn"]').prop('disabled', true);
    $('#delete_btn_text').html('Force delete')
    $('#actions-delete-' + id + ' .btn-delete').prop('disabled', false);
  } else {
    $('#actions-enable-' + id + ' *[class^="btn"]').prop('disabled', false);
  }
}

function actionsHyperDetail() {
  $('.btn-enable').off('click').on('click', function () {
    var closest = $(this).closest("div");
    var pk = closest.attr("data-pk");
    var data = table.row("#" + pk).data();
    let change = data["enabled"] ? "disable" : "enable";
    text = ""
    if (data["enabled"] && data["orchestrator_managed"]) {
      text = "<b>You are about to disable " + pk + "!\nThis action will remove hypervisor from orchestrator managing\nAre you sure?</b>"
    } else {
      text = "<b>You are about to " + change + " " + pk + "!\nAre you sure?</b>"
    }
    new PNotify({
      title: "<b>WARNING</b>",
      type: "error",
      text: text,
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
        url: "/admin/table/update/hypervisors",
        type: "PUT",
        accept: "application/json",
        data: JSON.stringify({ 'id': pk, 'enabled': !data.enabled }),
        contentType: "application/json",
        success: function (hyp) {
          if (data["enabled"] && data["orchestrator_managed"]) {
            $.ajax({
              url: "/api/v3/orchestrator/hypervisor/" + pk + "/manage",
              type: "DELETE",
              accept: "application/json",
              contentType: "application/json",
              success: function (data) {
                new PNotify({
                  title: 'Updated',
                  text: 'Hypervisor updated successfully',
                  hide: true,
                  delay: 2000,
                  opacity: 1,
                  type: 'success'
                })
              },
              error: function (data) {
                new PNotify({
                  title: 'ERROR updating hypervisor',
                  text: data.responseJSON.description,
                  type: 'error',
                  hide: true,
                  icon: 'fa fa-warning',
                  delay: 2000,
                  opacity: 1
                })
              },
            });
            $.ajax({
              url: "/api/v3/orchestrator/hypervisor/" + pk + "/manage",
              type: "DELETE",
              accept: "application/json",
              contentType: "application/json",
            })
          }
        },
      });
    }).on('pnotify.cancel', function () { });
  });

  $('.btn-delete').on('click', function () {
    var pk = $(this).closest("div").attr("data-pk");
    new PNotify({
      title: '<b>WARNING</b>',
      type: "error",
      text: "<b>You are about to delete " + pk + "!<br>Are you sure?</b>",
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
        url: "/api/v3/hypervisor/" + pk,
        type: "DELETE",
        accept: "application/json",
        contentType: "application/json",
        success: function (data) {
          new PNotify({
            title: 'Deleted',
            text: 'Hypervisor deleted successfully',
            hide: true,
            delay: 2000,
            opacity: 1,
            type: 'success'
          })
        },
        error: function (data) {
          new PNotify({
            title: 'ERROR deleting hypervisor',
            text: data.responseJSON.description,
            type: 'error',
            hide: true,
            icon: 'fa fa-warning',
            delay: 2000,
            opacity: 1
          })
        },
      });
    }).on('pnotify.cancel', function () { });
  });

  $('.btn-domstop').on('click', function () {
    var pk = $(this).closest("div").attr("data-pk");
    new PNotify({
      title: '<b>WARNING</b>',
      type: "error",
      text: "<b>You are about to FORCE STOP all desktops in " + pk + "!<br>Are you sure?</b>",
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
        url: "/api/v3/hypervisor/stop/" + pk,
        type: "PUT",
        accept: "application/json",
        contentType: "application/json",
        success: function (data) {
          new PNotify({
            title: 'Updated',
            text: 'Hypervisor desktops stopped successfully',
            hide: true,
            delay: 2000,
            opacity: 1,
            type: 'success'
          })
        },
        error: function (data) {
          new PNotify({
            title: 'ERROR stopping hypervisor desktops',
            text: data.responseJSON.description,
            type: 'error',
            hide: true,
            icon: 'fa fa-warning',
            delay: 2000,
            opacity: 1
          })
        },
      });
    }).on('pnotify.cancel', function () { });
  });

  $('.btn-edit').on('click', function () {
    $("#checkbox_edit_error").hide()
    var pk = $(this).closest("div").attr("data-pk");
    $("#modalEdit")[0].reset();
    $("#modalEditHyper #hypervisors_pools_dropdown").find('option').remove();

    $('#modalEditHyper').modal({
      backdrop: 'static',
      keyboard: false
    }).modal('show');

    $.ajax({
      url: "/admin/table/hypervisors",
      type: "POST",
      data: JSON.stringify({ 'order_by': 'id' }),
      contentType: "application/json",
      success: function (hyp) {
        hyp = hyp[0]
        $('#modalEditHyper #modalEdit #id').val(pk);
        $('#modalEditHyper #modalEdit #fake_id').val(pk);
        $('#modalEditHyper #modalEdit #description').val(hyp.description);
        $('#modalEditHyper #modalEdit #hostname').val(hyp.hostname);
        $('#modalEditHyper #modalEdit #user').val(hyp.user);
        $('#modalEditHyper #modalEdit #port').val(hyp.port);
        if (hyp.capabilities.disk_operations) {
          $('#modalEditHyper #modalEdit #capabilities-disk_operations').iCheck('check');
        }
        if (hyp.capabilities.hypervisor) {
          $('#modalEditHyper #modalEdit #capabilities-hypervisor').iCheck('check');
        }
        $('#modalEditHyper #modalEdit #viewer-static').val(hyp.viewer.static);
        $('#modalEditHyper #modalEdit #viewer-proxy_video').val(hyp.viewer.proxy_video);
        $('#modalEditHyper #modalEdit #viewer-spice_ext_port').val(hyp.viewer.spice_ext_port);
        $('#modalEditHyper #modalEdit #viewer-html5_ext_port').val(hyp.viewer.html5_ext_port);
        $('#modalEditHyper #modalEdit #viewer-hyper_vpn_host').val(hyp.isard_hyper_vpn_host);
        $('#modalEditHyper #modalEdit #viewer-proxy_hyper_host').val(hyp.viewer.proxy_hyper_host);
      },
      error: function (jqXHR, exception) {
        processError(jqXHR, form)
      }
    });

    $.ajax({
      url: "/admin/table/hypervisors_pools",
      type: "POST",
      data: JSON.stringify({ 'order_by': 'name' }),
      contentType: "application/json",
      success: function (pools) {
        $.each(pools, function (key, value) {
          $("#modalEditHyper #hypervisors_pools_dropdown").append('<option value=' + value.id + '>' + value.name + '</option>');
        });
      },
      error: function (jqXHR, exception) {
        processError(jqXHR, form)
      }
    });

    $('#modalEditHyper .capabilities_hypervisor').on('ifChecked', function (event) {
      $("#checkbox_edit_error").hide()
      $('#modalEditHyper #viewer_fields').show()
      if ($('#modalEditHyper #viewer-static').val() != '' && $('#modalEditHyper #viewer-proxy_video').val() == '' && $('#modalEditHyper #viewer-proxy_hyper_host').val() == '') {
        $('#modalEditHyper #viewer-static').val($('#modalEditHyper #hostname').val());
        $('#modalEditHyper #viewer-proxy_video').val($('#modalEditHyper #hostname').val());
        $('#modalEditHyper #viewer-proxy_hyper_host').val($('#modalEditHyper #hostname').val());
      }


    });

    $('#modalEditHyper .capabilities_disk_operations').on('ifChecked', function (event) {
      $("#checkbox_edit_error").hide()
    });

    $('#modalEditHyper .capabilities_hypervisor').on('ifUnchecked', function (event) {
      $('#modalEditHyper #viewer_fields').hide()
      $('#modalEditHyper #viewer-static').val('');
      $('#modalEditHyper #viewer-proxy_video').val('');
      $('#modalEditHyper #viewer-proxy_hyper_host').val('');
    });

    $('#modalEditHyper #send').off('click').on('click', function (e) {
      var form = $('#modalEditHyper #modalEdit');
      form.parsley().validate();
      if (form.parsley().isValid()) {
        data = $('#modalEditHyper #modalEdit').serializeObject();
        data['only_forced'] = $('#modalEditHyper #modalEdit #only_forced').prop('checked');
        data['hypervisors_pools'] = [$('#modalEditHyper #hypervisors_pools_dropdown').val()];

        delete data['capabilities-hypervisor']
        delete data['capabilities-disk_operations']
        data['capabilities'] = {}
        data['capabilities']['hypervisor'] = $('#modalEditHyper #modalEdit #capabilities-hypervisor').prop('checked')
        data['capabilities']['disk_operations'] = $('#modalEditHyper #modalEdit #capabilities-disk_operations').prop('checked')

        delete data['viewer-html5_ext_port']
        delete data['viewer-proxy_hyper_host']
        delete data['viewer-proxy_video']
        delete data['viewer-spice_ext_port']
        delete data['viewer-static']
        data['viewer'] = {}
        data['viewer']['html5_ext_port'] = $('#modalEditHyper #modalEdit #viewer-html5_ext_port').val()
        data['viewer']['proxy_hyper_host'] = $('#modalEditHyper #modalEdit #viewer-proxy_hyper_host').val()
        data['viewer']['proxy_video'] = $('#modalEditHyper #modalEdit #viewer-proxy_video').val()
        data['viewer']['spice_ext_port'] = $('#modalEditHyper #modalEdit #viewer-spice_ext_port').val()
        data['viewer']['static'] = $('#modalEditHyper #modalEdit #viewer-static').val()

        if (!data['capabilities']['hypervisor'] && !data['capabilities']['disk_operations']) {
          $("#checkbox_edit_error #checkbox_edit_error_html").html("You must select at least one option")
          $("#checkbox_edit_error").show()
        } else {
          $("#checkbox_edit_error").hide()

          $.ajax({
            type: "PUT",
            url: "/admin/table/update/hypervisors",
            data: JSON.stringify(data),
            contentType: "application/json",
            success: function (data) {
              $('form').each(function () { this.reset() });
              $('.modal').modal('hide');
            }
          });
        }
      }
    });
  });

  $('.btn-onlyforced').off('click').on('click', function () {

    var pk = $(this).closest("div").attr("data-pk");
    var data = table.row("#" + pk).data();
    text = ""
    if (!data["only_forced"] && data["orchestrator_managed"]) {
      text = "<b>You are about to set Only Forced to true for hyper " + pk + "!\nThis action will remove hypervisor from orchestrator managing\nAre you sure?</b>"
    } else {
      text = "<b>You are about to set Only Forced to " + !data.only_forced + " for hyper " + pk + "!\nAre you sure?</b>"
    }
    new PNotify({
      title: "<b>WARNING</b>",
      type: "error",
      text: text,
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
        url: "/admin/table/update/hypervisors",
        type: "PUT",
        data: JSON.stringify({ 'id': pk, 'only_forced': !data.only_forced }),
        contentType: "application/json",
        success: function (data) {
          new PNotify({
            title: 'Updated',
            text: 'Hypervisor updated successfully',
            hide: true,
            delay: 2000,
            opacity: 1,
            type: 'success'
          })
        },
        error: function (data) {
          new PNotify({
            title: 'ERROR updating hypervisor',
            text: data.responseJSON.description,
            type: 'error',
            hide: true,
            icon: 'fa fa-warning',
            delay: 2000,
            opacity: 1
          })
        },
      });
      if (!data["only_forced"] && data["orchestrator_managed"]) {
        $.ajax({
          url: "/api/v3/orchestrator/hypervisor/" + pk + "/manage",
          type: "DELETE",
          accept: "application/json",
          success: function (data) {
            new PNotify({
              title: 'Updated',
              text: 'Hypervisor updated successfully',
              hide: true,
              delay: 2000,
              opacity: 1,
              type: 'success'
            })
          },
          error: function (data) {
            new PNotify({
              title: 'ERROR updating hypervisor',
              text: data.responseJSON.description,
              type: 'error',
              hide: true,
              icon: 'fa fa-warning',
              delay: 2000,
              opacity: 1
            })
          },
        });
      }
    }).on('pnotify.cancel', function () { });
  });

  $('.btn-gpu_only').on('click', function () {

    var pk = $(this).closest("div").attr("data-pk");
    var gpu_only = table.row("#" + pk).data()['gpu_only'];

    new PNotify({
      title: "<b>WARNING</b>",
      type: "error",
      text: "<b>You are about to set Only GPU to " + !gpu_only + "!<br>Are you sure?</b>",
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
        url: "/admin/table/update/hypervisors",
        type: "PUT",
        data: JSON.stringify({ 'id': pk, 'gpu_only': !gpu_only }),
        contentType: "application/json",
        success: function (data) {
          table.ajax.reload()
          new PNotify({
            title: 'Updated',
            text: 'Hypervisor updated successfully',
            hide: true,
            delay: 2000,
            opacity: 1,
            type: 'success'
          })
        },
        error: function (data) {
          new PNotify({
            title: 'ERROR updating hypervisor',
            text: data.responseJSON.description,
            type: 'error',
            hide: true,
            icon: 'fa fa-warning',
            delay: 2000,
            opacity: 1
          })
        },
      });
    }).on('pnotify.cancel', function () { });
  });

  $('.btn-orchestrator').off('click').on('click', function () {
    var closest = $(this).closest("div");
    var pk = closest.attr("data-pk");
    var data = table.row("#" + pk).data();
    let change = data["orchestrator_managed"] ? "unmanaged" : "managed";
    new PNotify({
      title: "<b>WARNING</b>",
      type: "error",
      text: "<b>Do you want this hyper to be " + change + " by Orchestrator?</b>",
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
      type = ""
      type = data["orchestrator_managed"] ? "DELETE" : "POST";
      $.ajax({
        url: "/api/v3/orchestrator/hypervisor/" + pk + "/manage",
        type: type,
        contentType: "application/json",
        success: function (data) {
          new PNotify({
            title: 'Updated',
            text: 'Hypervisor updated successfully',
            hide: true,
            delay: 2000,
            opacity: 1,
            type: 'success'
          })
          orchestrator_hypers_table.ajax.reload()
          table.ajax.reload()
        },
        error: function (data) {
          new PNotify({
            title: 'ERROR updating hypervisor',
            text: data.responseJSON.description,
            type: 'error',
            hide: true,
            icon: 'fa fa-warning',
            delay: 2000,
            opacity: 1
          })
        },
      });
    }).on('pnotify.cancel', function () { });
  });
}


function renderEnabled(data) {
  if (data.enabled == true) { return '<i class="fa fa-check fa-2x" style="color:lightgreen"></i>'; }
  return '<i class="fa fa-close fa-2x" style="color:darkgray"></i>';
}

function renderStatus(data) {
  icon = data.icon;
  switch (data.status) {
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
    default:
      icon = '<i class="fa fa-question fa-2x" style="color:lightred"></i>'
  }
  if ("orchestrator_managed" in data && data.orchestrator_managed == true) {
    icon = icon + '<i class="fa fa-magic fa-1x" style="color:rgb(166, 144, 238)"></i>';
  }
  return icon + '<br>' + data.status;
}

function renderProgress(perc, green, orange) {
  if (perc < green) {
    cl = "lightgreen"
  } else if (perc < orange) {
    cl = "orange"
  } else {
    cl = "red"
  }
  return '<div class="progress" > \
        <div class="progress-bar" role="progressbar" aria-valuenow="'+ perc + '" \
        aria-valuemin="0" aria-valuemax="100" style="width:'+ perc + '%;color: black;;background: ' + cl + '"> \
          '+ perc + '%  \
        </div> \
      </<div> '
}

function renderGraph(data) {
  return '<div class="epoch category40" id="chart-' + data.id + '" style="width: 220px; height: 50px;"></div>'
}

function showUserExportButtons(table, buttonsRowClass) {
  new $.fn.dataTable.Buttons(table, {
    buttons: [
      {
        titleAttr: 'Customise visible columns',
        text: 'Custom',
        extend: 'colvis',
        columns: ':not(.details-control)'
      },
      {
        titleAttr: 'Toggle system info columns',
        text: 'System',
        extend: 'columnToggle',
        columns: '.group-system'
      },
      {
        titleAttr: 'Toggle Stats columns',
        text: 'Stats',
        extend: 'columnToggle',
        columns: '.group-stats'
      },
    ]
  }).container()
    .appendTo($('.' + buttonsRowClass));
}
