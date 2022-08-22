/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$(document).ready(function() {
    $template = $(".template-storage-detail");
    var storage_ready=$('#storage').DataTable( {
        "ajax": {
				"url": "/api/v3/admin/storage/ready",
                "contentType": "application/json",
                "type": 'GET',
        },
        "sAjaxDataProp": "",
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
			},
			"rowId": "id",
			"deferRender": true,
        "columns": [
            {
                "className":      'details-control',
                "orderable":      false,
                "data":           null,
                "width": "10px",
                "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
            },
            { "data": "directory_path",},
            { "data": "id",},
            { "data": "type",},
            { "data": null},
            { "data": null},
            { "data": "parent",},
            { "data": "user_name",},
            { "data": "category",},
            { "data": "domains",},
        ],
        "columnDefs": [ 
            {
                "targets": 4,
                "render": function ( data, type, full, meta ) {
                    if( full['status'] == 'ready' && 'qemu-img-info' in full){
                        return full["qemu-img-info"]["virtual-size"]
                    }else{
                        return '-'
                    }
                }},
                {
                "targets": 5,
                "render": function ( data, type, full, meta ) {
                    if( full['status'] == 'ready' && 'qemu-img-info' in full){
                        return full["qemu-img-info"]["actual-size"] +' ('+full["qemu-img-info"]["actual-size"]*100/full["qemu-img-info"]["virtual-size"]+'%)'
                    }else{
                        return '-'
                    }
                }
            }],
    });

    $('#storage tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest("tr");
        var row = storage_ready.row(tr);
        var rowData = row.data();
    
        if (row.child.isShown()) {
          // This row is already open - close it
          row.child.hide();
          tr.removeClass("shown");
        //   storage_ready.ajax.reload();
    
          // Destroy the Child Datatable
          $("#cl" + rowData.clientID)
            .DataTable()
            .destroy();
        } else {
            // Open this row
            row.child(format(rowData)).show();
            var id = rowData.id;
      
            childTable = $("#cl" + id).DataTable({
              dom: "t",
              ajax: {
                url: "/admin/storage/domains/" + id,
                contentType: "application/json",
                type: "GET",
              },
              sAjaxDataProp: "",
              language: {
                loadingRecords:
                  '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
              },
              columns: [
                { data: "kind" },
                { data: "name" },
              ],
              columnDefs: [
              ],
              select: false,
            });
      
            tr.addClass("shown");
          }
    } );

    var storage_deleted=$('#storage_deleted').DataTable( {
        "ajax": {
				"url": "/api/v3/admin/storage/deleted",
                "contentType": "application/json",
                "type": 'GET',
        },
        "sAjaxDataProp": "",
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
			},
			"rowId": "id",
			"deferRender": true,
        "columns": [
            { "data": "id",},
            { "data": "type",},
            { "data": null},
            { "data": "user_name",},
            { "data": "category",},
        ],
        "columnDefs": [
          {
          "targets": 2,
          "render": function ( data, type, full, meta ) {
              if( 'qemu-img-info' in full ){
                  return full["qemu-img-info"]["virtual-size"]
              }else{
                  return '-'
              }
          }},],
    });

    if( $("#storage_physical").length != 0){
      var storage_physical=$('#storage_physical').DataTable( {
        "ajax": {
        "url": "/api/v3/admin/storage/physical/domains",
                "contentType": "application/json",
                "type": 'GET',
        },
        "sAjaxDataProp": "",
        "language": {
          "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "rowId": "id",
        "deferRender": true,
          "columns": [
              { "data": "path",},
              { "data": "kind",},
              { "data": "size"},
              { "data": "hyper"},
              { "data": "domains"},
        ],
        "columnDefs": [],
      });
    }
})

function format(rowData) {
    var childTable =
      '<table id="cl' +
      rowData.id +
      '" class="display compact nowrap w-100" width="100%">' +
      "</table>";
    return $(childTable).toArray();
  }