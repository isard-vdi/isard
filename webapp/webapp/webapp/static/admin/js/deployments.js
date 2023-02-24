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
      ],
    });

    adminShowIdCol(deployments)

    $('#deployments').find(' tbody').on('click', 'button', function(){
      var data = deployments.row($(this).parents('tr')).data();
        switch ($(this).attr('id')) {
          case 'btn-alloweds':
            modalAllowedsFormShow('deployments', data)
            break;
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
        setHardwareDomainDefaults_viewer('#hardware-'+row.data().id,row.data());
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