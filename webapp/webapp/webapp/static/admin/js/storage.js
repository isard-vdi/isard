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
            {
              "className": 'text-center',
              "data": null,
              "orderable": false,
              "defaultContent": '<input type="checkbox" class="form-check-input"></input>'
            }
        ],
        "columnDefs": [],
      });

      storage_physical.on( 'click', 'tr[role="row"]', function (e) {
        toggleRow(this, e);
      });

      $(".btn-phy-update").on("click", function () {
        new PNotify({
          title: "Rescan physical disks on storage",
          text: "Do you really want to rescan all them?",
          hide: false,
          opacity: 0.9,
          confirm: { confirm: true },
          buttons: { closer: false, sticker: false },
          history: { history: false },
          addclass: "pnotify-center",
        })
          .get()
          .on("pnotify.confirm", function () {
            $.ajax({
              type: "GET",
              url:
                "/api/v3/admin/storage/physical/toolbox_host",
              contentType: "application/json",
              success: function (toolbox_host) {
                $.ajax({
                  type: "PUT",
                  url: toolbox_host+"/storage/disks",
                  contentType: "application/json",
                  success: function (data) {
                    storage_physical.ajax.reload();
                    new PNotify({
                      title: "Physical storage",
                      text:  "Updated "+data.templates+" templates and "+data.desktops+" desktop disksfrom "+toolbox_host,
                      hide: true,
                      delay: 5000,
                      opacity: 1,
                      type: 'success'
                  });
                  },
                });
              },
            });
          })
          .on("pnotify.cancel", function () {});
      });

      $('#mactions').on('change', function () {
        action=$(this).val();
        names=''
        ids=[]

        if(storage_physical.rows('.active').data().length){
            $.each(storage_physical.rows('.active').data(),function(key, value){
                names+=value['path']+'\n';
                ids.push(value['id']);
            });
            var text = "You are about to "+action+" these physical disks:\n\n "+names
        }else{ 
            $.each(storage_physical.rows({filter: 'applied'}).data(),function(key, value){
              ids.push(value['id']);
            });
            var text = "You are about to "+action+" "+storage_physical.rows({filter: 'applied'}).data().length+" disks!\n All the disks in list!"
        }

        $.ajax({
          type: "POST",
          url:"/toolbox/api/storage/disk/info",
          headers: {"Authorization": "Bearer " +localStorage.getItem("token")},
          data: JSON.stringify({
              'path_id': ids[0]
          }),
          contentType: 'application/json',
          success: function(data)
          {
            console.log(data)
          }
        });

				new PNotify({
						title: 'Warning!',
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
							addclass: 'pnotify-center'
						}).get().on('pnotify.confirm', function() {
                api.ajax('/api/v3/admin/storage/multiple_actions', 'POST', {'ids':ids, 'action':action}).done(function(data) {
                    notify(data)
                }).fail(function(jqXHR) {
                    notify(jqXHR.responseJSON)
                }).always(function() {
                    $('#mactions option[value="none"]').prop("selected", true);
                    $('#domains tr.active').removeClass('active')
                })
                    }).on('pnotify.cancel', function() {
                        $('#mactions option[value="none"]').prop("selected",true);
				});
    } );
    } // if storage physical is present (admin)
})

function format(rowData) {
    var childTable =
      '<table id="cl' +
      rowData.id +
      '" class="display compact nowrap w-100" width="100%">' +
      "</table>";
    return $(childTable).toArray();
  }