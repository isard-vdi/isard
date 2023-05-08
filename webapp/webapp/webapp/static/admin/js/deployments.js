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
      { "data": "username" },
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
        "targets": 8,
        "render": function ( data, type, full, meta ) {
          if ('tag_visible' in full.create_dict && full.create_dict.tag_visible) {
            return '<i class="fa fa-circle" aria-hidden="true"  style="color:green" title="' + full.create_dict.tag_visible + '"></i>'
          } else {
              return '<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>'
          }
        }
      },
      {
        "targets": 9,
        "render": function ( data, type, full, meta ) {
          if ( type === 'display' || type === 'filter' ) {
            return moment.unix(full.last_access).fromNow()
          }
          return full.last_access
        }
      },
      {
        "targets": 10,
        "render": function ( data, type, full, meta ) {
          return '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
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
              deployments.ajax.reload();
            },
            error: function(xhr){
              if (xhr.status == 428) {
                new PNotify({
                  title: 'ERROR deleting deployment',
                  text: 'The deployment '+data["name"]+' must be stopped',
                  type: 'error',
                  hide: true,
                  icon: 'fa fa-warning',
                  delay: 5000,
                  opacity: 1
                })
              } else {
                new PNotify({
                  title: 'ERROR deleting deployment',
                  text: xhr.responseJSON.description,
                  type: 'error',
                  hide: true,
                  icon: 'fa fa-warning',
                  delay: 5000,
                  opacity: 1
                })
              }
            }
          });
          deployments.ajax.reload();
        }).on('pnotify.cancel', function () {});
        break;
      }
  });

  deployments.on( 'click', 'tr[role="row"]', function (e) {
    toggleRow(this, e);
  });

  $('.btn-bulkdelete').on('click', function () {
    let deploymentsToDelete = [];
    $.each(deployments.rows('.active').data(),function(key, value){
      deploymentsToDelete.push(value);
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
      for (deployment in deploymentsToDelete) {
          $.ajax({
            type: "DELETE",
            url: "/api/v3/deployments/" + deploymentsToDelete[deployment].id,
            data: JSON.stringify(deployment),
            contentType: "application/json",
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
              deployments.ajax.reload();
            },
            error: function(xhr){
              if (xhr.status == 428) {
                new PNotify({
                    title: "ERROR deleting deployment",
                    text: 'The deployment '+deploymentsToDelete[deployment].name+' must be stopped',
                    hide: true,
                    delay: 3000,
                    icon: 'fa fa-warning',
                    opacity: 1,
                    type: 'error'
                });
              } else {
                new PNotify({
                  title: "ERROR acessing storage",
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
    }
  });
});

function renderDeploymentDetailPannel ( d ) {
  $newPanel = $deployments_detail.clone();
  $newPanel.html(function(i, oldHtml){
    return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name).replace(/d.description/g, d.description);
  });
      return $newPanel
}