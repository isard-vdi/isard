/*
 * Copyright 2017 the Isard-vdi project authors:
 *      Josep Maria Viñolas Auquer
 *      Alberto Larraz Dalmases
 * License: AGPLv3
 */

$(document).ready(function() {
  $deployments_detail = $(".template-deployments-detail");
  deployments=$('#deployments').DataTable({
    "ajax": {
      "url": "/api/v3/admin/table/deployments",
      "contentType": "application/json",
      "type": 'GET',
      data: function (d) {
        return JSON.stringify({ order_by: "name" });
      },
    },
    "sAjaxDataProp": "",
    "language": {
      "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
    },
    "rowId": "id",
    "deferRender": true,
    "columns": [
      {
        "className": 'details-control',
        "orderable": false,
        "data": null,
        "width": "10px",
        "defaultContent": '<button class="btn btn-xs btn-info" type="button" data-placement="top" ><i class="fa fa-plus"></i></button>'
      },
      { "data": "name" },
      { "data": "desktop_name" },
      { "data": "category_name" },
      { "data": "group_name" },
      { "data": "user_name" },
      { "data": "co_owners_user_names" },
      { "data": "user_permissions" },
      { "data": "how_many_desktops" },
      { "data": "how_many_desktops_started" },
      { "data": "create_dict.tag_visible" },
      { "data": "last_access" },
      { "data": null, 'defaultContent': ''},
      { "data": "id", "visible": false},
    ],
    order: [[1, "asc"]],
    "columnDefs": [
      {
        "targets": 10,
        "render": function ( data, type, full, meta ) {
          if ('tag_visible' in full.create_dict && full.create_dict.tag_visible) {
            return '<i class="fa fa-circle" aria-hidden="true"  style="color:green" title="' + full.create_dict.tag_visible + '"></i>'
          } else {
              return '<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>'
          }
        }
      },
      {
        "targets": 11,
        "render": function ( data, type, full, meta ) {
          if ( type === 'display' || type === 'filter' ) {
            return formatTimestampUTC(full.last_access*1000)
          }
          return full.last_access
        }
      },
      {
        "targets": 12,
        "render": function ( data, type, full, meta ) {
          return `<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>`
        }
      },
    ],
  });

  adminShowIdCol(deployments)

  $('#deployments').find(' tbody').on('click', 'button', function(){
    var data = deployments.row($(this).parents('tr')).data();
    switch ($(this).attr('id')) {
      case 'btn-delete':
        new PNotify({
          title: 'Confirmation Needed',
          text: "Are you sure you want to delete deployment " + data['name'] + "?",
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
          addclass: 'pnotify-center'
        }).get().on('pnotify.confirm', function () {
          $.ajax({
            type: "DELETE",
            url: "/api/v3/deployments/" + data["id"],
            success: function(data){
              new PNotify({
                title: 'Deleted',
                text: 'Deployment deleted successfully',
                hide: true,
                delay: 2000,
                icon: 'fa fa-' + data.icon,
                opacity: 1,
                type: 'success'
              });
            },
            error: function(xhr){
                new PNotify({
                  title: 'ERROR deleting deployment',
                  text: xhr.responseJSON.description,
                  type: 'error',
                  hide: true,
                  icon: 'fa fa-warning',
                  delay: 5000,
                  opacity: 1
                });
            }
          });
        }).on('pnotify.cancel', function () {});
        break;
      }
  });

  deployments.on( 'click', 'tbody tr', function (e) {
    toggleRow(this, e);
  });

  $('.btn-bulkdelete').on('click', function () {
    let deploymentsToDelete = [];
    $.each(deployments.rows('.active').data(),function(key, value){
      deploymentsToDelete.push(value.id);
    });

    if (!(deploymentsToDelete.length == 0)) {
      new PNotify({
        title: "<b>WARNING</b>",
        type: "error",
        text: "<b>You are about to delete " + deploymentsToDelete.length + " selected deployments!<br>Are you sure?</b>",
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
          var notify = new PNotify();
          $.ajax({
            type: "DELETE",
            url: "/api/v3/deployments/",
            data: JSON.stringify({ids:deploymentsToDelete}),
            contentType: "application/json",
            success: function(data){
              notify.update({
                title: 'Processing',
                text: `Processing action: deleting ${deploymentsToDelete.length} deployment(s)`,
                hide: false,
                type: 'info',
                icon: 'fa fa-spinner fa-pulse',
                opacity: 1
            });
              deployments.ajax.reload();
            },
            error: function (xhr) {
              if (xhr.responseJSON && xhr.responseJSON.exceptions) {
                const exceptionsList = xhr.responseJSON.exceptions.map(exception => `<li>${exception}</li>`).join('');
                notify.update({
                  title: "ERROR deleting deployment(s)",
                  text: `<ul>${exceptionsList}</ul>`,
                  hide: true,
                  delay: 3000,
                  icon: 'fa fa-alert-sign',
                  opacity: 1,
                  type: 'error'
                });
              } else {
                notify.update({
                  title: "ERROR deleting deployment(s)",
                  text: xhr.responseJSON ? xhr.responseJSON.description : "Something went wrong",
                  hide: true,
                  delay: 3000,
                  icon: 'fa fa-alert-sign',
                  opacity: 1,
                  type: 'error'
                });
              }
            }
          });
      }).on('pnotify.cancel', function() {});
    } else {
      new PNotify({
        type: "warning",
        text: "<b>Select the deployments you want to delete</b>",
        hide: false,
        opacity: 0.9,
        history: {
          history: false
        },
        addclass: 'pnotify-center-large',
        width: '550'
      })
    }
  });

  $('#deployments tbody').on('click', 'td.details-control', function () {
    var tr = $(this).closest("tr");
    var row = deployments.row(tr);
    if (row.child.isShown()) {
      row.child.hide();
      tr.removeClass("shown");
    } else {
      if (deployments.row('.shown').length) {
        $('.details-control', deployments.row('.shown').node()).click();
      }
      row.child(renderDeploymentDetailPannel(row.data())).show()
      tr.addClass('shown');
      setHardwareDomainDefaultsDetails(row.data().id, 'deployment');
      setAlloweds_viewer('#alloweds-' + row.data().id, row.data().id, "deployments");
      actionsDomainDetail();
    }
  });
  $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on);
});

function renderDeploymentDetailPannel ( d ) {
  $newPanel = $deployments_detail.clone();
  $newPanel.html(function(i, oldHtml){
    return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name).replace(/d.description/g, d.description);
  });
      return $newPanel
}

function actionsDomainDetail() {
  $('.btn-owner').on('click', function () {
    var pk = $(this).closest("[data-pk]").attr("data-pk");
    $("#modalChangeOwnerDomainForm")[0].reset();
    $('#modalChangeOwnerDomain').modal({
      backdrop: 'static',
      keyboard: false
    }).modal('show');
    $('#modalChangeOwnerDomainForm #id').val(pk);
    $("#new_owner").val("");
    if ($("#new_owner").data('select2')) {
      $("#new_owner").select2('destroy');
    }
    $('#new_owner').select2({
      placeholder: "Type at least 2 letters to search.",
      minimumInputLength: 2,
      dropdownParent: $('#modalChangeOwnerDomain'),
      ajax: {
        type: "POST",
        url: '/admin/users/search',
        dataType: 'json',
        contentType: "application/json",
        delay: 250,
        data: function (params) {
          return JSON.stringify({
            term: params.term,
            pluck: ['id', 'name']
          });
        },
        processResults: function (data) {
          return {
            results: $.map(data, function (item, i) {
              return {
                text: item.name + '[' + item['uid'] + '] ',
                id: item.id
              }
            })
          };
        }
      },
    });
  });
  $('.btn-co-owners').on('click', function () {
    var pk = $(this).closest("[data-pk]").attr("data-pk");
    $("#modalChangeCoOwnersDeploymentForm")[0].reset();
    $('#modalChangeCoOwnersDeployment').modal({
      backdrop: 'static',
      keyboard: false
    }).modal('show');
    $('#modalChangeCoOwnersDeploymentForm #id').val(pk);
    $("#co_owners").val("");
    if ($("#co_owners").data('select2')) {
      $("#co_owners").select2('destroy');
    }
    $('#co_owners').select2({
      placeholder: "Type at least 2 letters to search.",
      minimumInputLength: 2,
      multiple: true,
      dropdownParent: $('#modalChangeCoOwnersDeployment'),
      ajax: {
        type: "POST",
        url: '/admin/users/search',
        dataType: 'json',
        contentType: "application/json",
        delay: 250,
        data: function (params) {
          return JSON.stringify({
            term: params.term,
            pluck: ['id', 'name']
          });
        },
        processResults: function (data) {
          return {
            results: $.map(data, function (item, i) {
              return {
                text: item.name + '[' + item['uid'] + '] ',
                id: item.id
              }
            })
          };
        }
      },
    });
    $.ajax({
      type: "GET",
      url: `/api/v3/deployment/co-owners/${pk}`,
      contentType: 'application/json',
      success: function (data) {
        $("#co_owners").empty().trigger('change');
        $.each(data.co_owners, function (i, value) {
          var newOption = new Option(value.name + '[' + value.uid + ']', value.id, true, true);
          $('#co_owners').append(newOption).trigger('change');
        });
      },
      error: function ({ responseJSON: { description } = {} }) {
        const msg = description ? description : 'Something went wrong';
        new PNotify({
          title: "ERROR",
          text: msg,
          type: 'error',
          icon: 'fa fa-warning',
          hide: true,
          delay: 15000,
          opacity: 1
        });
      }
    });
  });

  $("#modalChangeOwnerDomain #send").off('click').on('click', function (e) {
    var form = $('#modalChangeOwnerDomainForm');
    form.parsley().validate();

    if (form.parsley().isValid()) {
      data = form.serializeObject();
      let pk = $('#modalChangeOwnerDomainForm #id').val()
      $.ajax({
        type: "PUT",
        url: `/api/v3/deployment/owner/${pk}/${data['new_owner']}`,
        contentType: 'application/json',
        success: function () {
          $('form').each(function () { this.reset() });
          $('.modal').modal('hide');
          new PNotify({
            title: "Owner changed succesfully",
            text: "",
            hide: true,
            delay: 4000,
            icon: 'fa fa-success',
            opacity: 1,
            type: "success"
          });
          domains_table.ajax.reload();
        },
        error: function ({ responseJSON: { description } = {} }) {
          const msg = description ? description : 'Something went wrong';
          new PNotify({
            title: "ERROR",
            text: msg,
            type: 'error',
            icon: 'fa fa-warning',
            hide: true,
            delay: 15000,
            opacity: 1
          });
        }
      });
    };
  });

  $("#modalChangeCoOwnersDeployment #send").off('click').on('click', function (e) {
    var form = $('#modalChangeCoOwnersDeploymentForm');
    form.parsley().validate();

    if (form.parsley().isValid()) {
      let pk = $('#modalChangeCoOwnersDeploymentForm #id').val()
      coOwnersArray = $("#co_owners").val();
      $.ajax({
        type: "PUT",
        url: `/api/v3/deployment/co-owners/${pk}`,
        data: JSON.stringify({ co_owners: coOwnersArray }),
        contentType: 'application/json',
        success: function () {
          $('form').each(function () { this.reset() });
          $('.modal').modal('hide');
          new PNotify({
            title: "Co-owners changed succesfully",
            text: "",
            hide: true,
            delay: 4000,
            icon: 'fa fa-success',
            opacity: 1,
            type: "success"
          });
          domains_table.ajax.reload();
        },
        error: function ({ responseJSON: { description } = {} }) {
          const msg = description ? description : 'Something went wrong';
          new PNotify({
            title: "ERROR",
            text: msg,
            type: 'error',
            icon: 'fa fa-warning',
            hide: true,
            delay: 15000,
            opacity: 1
          });
        }
      });
    };
  });
}


function socketio_on() {
  socket.on('deployment_action', function (data) {
    PNotify.removeAll();
    var data = JSON.parse(data);
    if (data.status === 'failed') {
      new PNotify({
        title: `ERROR: ${data.action} on ${data.count} deployment(s)`,
        text: data.msg,
        hide: false,
        icon: 'fa fa-warning',
        opacity: 1,
        type: 'error'
      });
    } else if (data.status === 'completed') {
      deployments.ajax.reload();
      new PNotify({
        title: `Action Succeeded: ${data.action}`,
        text: `The action "${data.action}" completed on ${data.count} deployment(s).`,
        hide: true,
        delay: 4000,
        icon: 'fa fa-success',
        opacity: 1,
        type: 'success'
      });
    }
  });
}