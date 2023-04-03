/*
 * Copyright 2017 the Isard-vdi project authors:
 *      Josep Maria Viñolas Auquer
 *      Alberto Larraz Dalmases
 * License: AGPLv3
 */

$hypervisor_template = $(".hyper-detail");

$(document).ready(function() {
  $('.admin-status').show();
  $('.btn-new-hyper').on('click', function() {
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
      success: function(pools) {
        $.each(pools, function(key, value) {
          $("#modalAddHyper #hypervisors_pools_dropdown").append('<option value=' + value.id + '>' + value.name + '</option>');
        });
      },
      error: function(jqXHR, exception) {
        processError(jqXHR, form)
      }
    });

    $('#modalAddHyper #modalAdd #hostname').val(window.location.hostname)
    $('#modalAddHyper #modalAdd #user').val('root')
    $('#modalAddHyper #modalAdd #port').val(2022)
    $('#modalAddHyper #modalAdd #capabilities-disk_operations').iCheck('check')
    $('#modalAddHyper .capabilities_hypervisor').on('ifChecked', function(event) {
      $("#checkbox_add_error").hide()
      $('#viewer_fields').show()
      $('#modalAddHyper #viewer-static').val($('#modalAddHyper #modalAdd #hostname').val());
      $('#modalAddHyper #viewer-proxy_video').val($('#modalAddHyper #modalAdd #hostname').val());
      $('#modalAddHyper #viewer-proxy_hyper_host').val('isard-hypervisor');
      $('#modalAddHyper #viewer-hyper_vpn_host').val('isard-hypervisor');
    });

    $('#modalAddHyper .capabilities_disk_operations').on('ifChecked', function(event) {
      $("#checkbox_add_error").hide()
    });

    $('#modalAddHyper .capabilities_hypervisor').on('ifUnchecked', function(event) {
      $('#modalAddHyper #viewer_fields').hide()
      $('#modalAddHyper #modalAddHyper #viewer-static').val('');
      $('#modalAddHyper #modalAddHyper #viewer-proxy_video').val('');
      $('#modalAddHyper #modalAddHyper #viewer-proxy_hyper_host').val(0);
    });
  });

  $("#modalAddHyper #send").on('click', function(e) {
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
          success: function(data) {
            $('form').each(function() { this.reset() });
            $('.modal').modal('hide');
          },
          error: function(xhr, ajaxOptions, thrownError) {
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
  renderBoolean = (enabled) => {
    if (enabled) {
      return '<i class="fa fa-circle" aria-hidden="true" style="color:green"></i>'
    } else {
      return '<i class="fa fa-circle" aria-hidden="true" style="color:darkgray"></i>'
    }
  }

  table = $('#hypervisors').DataTable({
    "ajax": {
      "url": "/admin/table/hypervisors",
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
    "columns": [{
        "className": 'details-control',
        "orderable": false,
        "data": null,
        "width": "10px",
        "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
      },
      { "data": "enabled", "width": "10px" },
      { "data": "status", "width": "10px" },
      { "data": "only_forced", "width": "10px" },
      { "data": "gpu_only", "width": "10px", "defaultContent": 0 },
      { "data": "id", "width": "10px" },
      { "data": "hostname", "width": "100px" },
      { "data": "info.memory_in_MB", "width": "10px", "defaultContent": 'NaN' },
      { "data": "info.cpu_cores", "width": "10px", "defaultContent": 'NaN' },
      { "data": "status_time", "width": "10px" },
      { "data": "dom_started", "width": "10px", "defaultContent": 0 },
      { "data": "gpus", "width": "10px", "defaultContent": 0 },
      { "data": "vpn.wireguard.connected", "width": "10px", "defaultContent": 'NaN' },
      { "data": "info.nested", "width": "10px", "defaultContent": 'NaN' },
      { "data": "viewer.static", "width": "10px" },
      { "data": "viewer.proxy_video", "width": "10px" },
      { "data": "info.virtualization_capabilities", "width": "10px", "defaultContent": 'NaN' },
      { "data": "info.qemu_version", "width": "10px", "defaultContent": 'NaN' },
      { "data": "info.libvirt_version", "width": "10px", "defaultContent": 'NaN' },
    ],
    "order": [
      [9, 'asc']
    ],
    "columnDefs": [{
        // Enabled
        "targets": 1,
        "render": function(data, type, full, meta) {
          return renderEnabled(full);
        }
      },
      {
        // Status
        "targets": 2,
        "render": function(data, type, full, meta) {
          return renderStatus(full);
        }
      },
      {
        //Only Forced
        "targets": 3,
        "render": renderBoolean
      },
      {
        //Only GPU
        "targets": 4,
        "render": renderBoolean
      },
      {
        // RAM
        "targets": 7,
        "render": function(data, type, full, meta) {
          if (!("min_free_mem_gb" in full)) { full.min_free_mem_gb = 0 }
          memTotalGB = Math.round(data / 1024 * 10) / 10
          if (!("stats" in full)) { return "-% " + memTotalGB + 'GB' }
          memUsedGB = Math.round((full.stats.mem_stats.total - full.stats.mem_stats.available) / 1024 / 1024)
          limit = ""
          if (full.min_free_mem_gb > 0) {
            limit = " Limit:" + (memTotalGB - full.min_free_mem_gb) + "GB"
          }
          return Math.round(memUsedGB * 100 / memTotalGB) + "% " + memTotalGB + "GB" + limit
        }
      },
      {
        // CPU
        "targets": 8,
        "render": function(data, type, full, meta) {
          if (full.info) {
            if (!("stats" in full)) { return "-% " + full.info.cpu_cores * full.info.threads_x_core + "th" }
            return Math.round(full.stats.cpu_current.used) + "% " + full.info.cpu_cores * full.info.threads_x_core + "th";
          }
        }
      },
      {
        // Last Status Change
        "targets": 9,
        "render": function(data, type, full, meta) {
          return moment.unix(full.status_time).fromNow();
        }
      },
      {
        // Desktops
        "targets": 10,
        "render": function(data, type, full, meta) {
          if (full.status != "Online") {
            return "0"
          }
          return data
        }
      },
      {
        // VPN
        "targets": 12,
        "render": renderBoolean
      },
      {
        // Nested
        "targets": 13,
        "render": renderBoolean
      },
      {
        // Proxy Video
        "targets": 15,
        "render": function(data, type, full, meta) {
          return full.viewer.proxy_video + ' (' + full.viewer.spice_ext_port + ',' + full.viewer.html5_ext_port + ')';
        }
      },

      {
        // Virt
        "targets": 16,
        "render": function(data, type, full, meta) {
          if (!data) { return renderBoolean }
          return data
        }
      },
    ],
    "createdRow": function(row, data, dataIndex) {
      if (!("min_free_mem_gb" in data)) { data.min_free_mem_gb = 0 }
      memTotalGB = Math.round(data.info.memory_in_MB / 1024 * 10) / 10
      if ('stats' in data) {
        memUsedGB = Math.round((data.stats.mem_stats.total - data.stats.mem_stats.available) / 1024 / 1024)
        if (memTotalGB - memUsedGB - data.min_free_mem_gb <= 0) {
          $(row).css({ "background-color": "#FFCCCB" })
        } else {
          $(row).css({ "background-color": "white" })
        }
      }
    }
  });

  $('#hypervisors').find('tbody').on('click', 'td.details-control', function() {
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
    }
  });
  $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on)
})

function socketio_on() {
  socket.on('hyper_data', function(data) {
    var data = JSON.parse(data);
    data = {...table.row("#" + data.id).data(), ...data }
    new_hyper = dtUpdateInsert(table, data, false);
    table.draw(false)
    if (new_hyper) { tablepools.draw(false); }
    setHypervisorDetailButtonsStatus(data.id, data.status)
  });

  socket.on('hyper_deleted', function(data) {
    var data = JSON.parse(data);
    table.row('#' + data.id).remove().draw();
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

  socket.on('add_form_result', function(data) {
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
    tablepools.ajax.reload()
  });

  socket.on('result', function(data) {
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
  $newPanel.html(function(i, oldHtml) {
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
  $('.btn-enable').off('click').on('click', function() {
    var closest = $(this).closest("div");
    var pk = closest.attr("data-pk");
    var data = table.row("#" + pk).data();
    let change = data["enabled"] ? "disable" : "enable";
    new PNotify({
      title: "<b>WARNING</b>",
      type: "error",
      text: "<b>You are about to " + change + " " + pk + "!<br>Are you sure?</b>",
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

    }).get().on('pnotify.confirm', function() {
      api.ajax('/admin/table/update/hypervisors', 'PUT', { 'id': pk, 'enabled': !data.enabled }).done(function(hyp) {});
    }).on('pnotify.cancel', function() {});
  });

  $('.btn-delete').on('click', function() {
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

    }).get().on('pnotify.confirm', function() {
      api.ajax('/api/v3/hypervisor/' + pk, 'DELETE').done(function(hyp) {});
    }).on('pnotify.cancel', function() {});
  });

  $('.btn-domstop').on('click', function() {
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

    }).get().on('pnotify.confirm', function() {
      api.ajax('/api/v3/hypervisor/stop/' + pk, 'PUT').done(function(hyp) {});
    }).on('pnotify.cancel', function() {});
  });

  $('.btn-edit').on('click', function() {
    $("#checkbox_edit_error").hide()
    var pk = $(this).closest("div").attr("data-pk");
    $("#modalEdit")[0].reset();
    $("#modalEditHyper #hypervisors_pools_dropdown").find('option').remove();

    $('#modalEditHyper').modal({
      backdrop: 'static',
      keyboard: false
    }).modal('show');

    api.ajax('/admin/table/hypervisors', 'POST', { 'id': pk }).done(function(hyp) {
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

    });

    $.ajax({
      url: "/admin/table/hypervisors_pools",
      type: "POST",
      data: JSON.stringify({ 'order_by': 'name' }),
      contentType: "application/json",
      success: function(pools) {
        $.each(pools, function(key, value) {
          $("#modalEditHyper #hypervisors_pools_dropdown").append('<option value=' + value.id + '>' + value.name + '</option>');
        });
      },
      error: function(jqXHR, exception) {
        processError(jqXHR, form)
      }
    });

    $('#modalEditHyper .capabilities_hypervisor').on('ifChecked', function(event) {
      $("#checkbox_edit_error").hide()
      $('#modalEditHyper #viewer_fields').show()
      if ($('#modalEditHyper #viewer-static').val() != '' && $('#modalEditHyper #viewer-proxy_video').val() == '' && $('#modalEditHyper #viewer-proxy_hyper_host').val() == '') {
        $('#modalEditHyper #viewer-static').val($('#modalEditHyper #hostname').val());
        $('#modalEditHyper #viewer-proxy_video').val($('#modalEditHyper #hostname').val());
        $('#modalEditHyper #viewer-proxy_hyper_host').val($('#modalEditHyper #hostname').val());
      }


    });

    $('#modalEditHyper .capabilities_disk_operations').on('ifChecked', function(event) {
      $("#checkbox_edit_error").hide()
    });

    $('#modalEditHyper .capabilities_hypervisor').on('ifUnchecked', function(event) {
      $('#modalEditHyper #viewer_fields').hide()
      $('#modalEditHyper #viewer-static').val('');
      $('#modalEditHyper #viewer-proxy_video').val('');
      $('#modalEditHyper #viewer-proxy_hyper_host').val('');
    });

    $('#modalEditHyper #send').off('click').on('click', function(e) {
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
            success: function(data) {
              $('form').each(function() { this.reset() });
              $('.modal').modal('hide');
            }
          });
        }
      }
    });
  });

  $('.btn-onlyforced').on('click', function() {

    var pk = $(this).closest("div").attr("data-pk");
    var only_forced = table.row("#" + pk).data()['only_forced'];

    new PNotify({
      title: "<b>WARNING</b>",
      type: "error",
      text: "<b>You are about to set Only Forced to " + !only_forced + "!<br>Are you sure?</b>",
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

    }).get().on('pnotify.confirm', function() {
      $.ajax({
        url: "/admin/table/update/hypervisors",
        type: "PUT",
        data: JSON.stringify({ 'id': pk, 'only_forced': !only_forced }),
        contentType: "application/json",
        success: function(data) {
          new PNotify({
            title: 'Updated',
            text: 'Hypervisor updated successfully',
            hide: true,
            delay: 2000,
            opacity: 1,
            type: 'success'
          })
        },
        error: function(data) {
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
    }).on('pnotify.cancel', function() {});
  });

  $('.btn-gpu_only').on('click', function() {

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

    }).get().on('pnotify.confirm', function() {
      $.ajax({
        url: "/admin/table/update/hypervisors",
        type: "PUT",
        data: JSON.stringify({ 'id': pk, 'gpu_only': !gpu_only }),
        contentType: "application/json",
        success: function(data) {
          new PNotify({
            title: 'Updated',
            text: 'Hypervisor updated successfully',
            hide: true,
            delay: 2000,
            opacity: 1,
            type: 'success'
          })
        },
        error: function(data) {
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
    }).on('pnotify.cancel', function() {});
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
  return icon + '<br>' + data.status;
}

function renderGraph(data) {
  return '<div class="epoch category40" id="chart-' + data.id + '" style="width: 220px; height: 50px;"></div>'
}