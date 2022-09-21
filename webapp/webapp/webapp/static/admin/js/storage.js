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
            { "data": "status_logs",}
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
                }},
                {
                  "targets": 10,
                  "render": function ( data, type, full, meta ) {
                    return moment.unix(full["status_logs"][full["status_logs"].length -1]["time"]).fromNow()
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
            { "data": "status_logs"}
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
          }},
          {
            "targets": 5,
            "render": function ( data, type, full, meta ) {
              return moment.unix(full["status_logs"][full["status_logs"].length -1]["time"]).fromNow()
          }
        }],
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
            { "data": ""},
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
        "columnDefs": [
          {
            "targets": 0,
            "render": function ( data, type, full, meta ) {
              return '<button type="button" id="btn-info" class="btn btn-pill-right btn-success btn-xs"><i class="fa fa-info"></i></button>';
            }
        }
        ],
      });

      $('#storage_physical tbody').on( 'click', 'button', function () {
        var data = storage_physical.row( $(this).parents('tr') ).data();
        switch($(this).attr('id')){
          case 'btn-info':
            $.ajax({
              type: "POST",
              url:"/toolbox/api/storage/disk/info",
              headers: {"Authorization": "Bearer " +localStorage.getItem("token")},
              data: JSON.stringify({
                  'path_id': data.path
              }),
              contentType: 'application/json',
              success: function(disk_info)
              {
                new PNotify({
                  title: "Disk info.",
                    text: JSON.stringify(disk_info),
                    hide: true,
                    delay: 10000,
                    icon: 'fa fa-info',
                    opacity: 1,
                    type: 'info'
                });
              }
            });
        break;
      }
      })

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
                ids.push(value['path']);
            });
            var text = "You are about to "+action+" these physical disks:\n\n "+names
        }else{ 
            $.each(storage_physical.rows({filter: 'applied'}).data(),function(key, value){
              ids.push(value['path']);
            });
            var text = "You are about to "+action+" "+storage_physical.rows({filter: 'applied'}).data().length+" disks!\n All the disks in list!"
        }

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
              $.ajax({
                type: "POST",
                url:"/api/v3/admin/storage/physical/multiple_actions/"+action,
                data: JSON.stringify({'paths':ids}),
                contentType: 'application/json',
                success: function(data)
                {
                  console.log(data)
                },
                always: function(data)
                {
                  $('#mactions option[value="none"]').prop("selected", true);
                  $('#domains tr.active').removeClass('active')
                  $('#mactions option[value="none"]').prop("selected",true);
                }
              });
    } )
      })
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