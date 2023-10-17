//   Copyright © 2017-2023 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
//
//   This file is part of IsardVDI.
//
//   IsardVDI is free software: you can redistribute it and/or modify
//   it under the terms of the GNU Affero General Public License as published by
//   the Free Software Foundation, either version 3 of the License, or (at your
//   option) any later version.
//
//   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
//   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
//   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
//   details.
//
//   You should have received a copy of the GNU Affero General Public License
//   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
//
// SPDX-License-Identifier: AGPL-3.0-or-later

function getGroupParam() {
  return window.location.href.slice(window.location.href.indexOf('?') + 1).split('searchStorageId=')[1];
}

$(document).ready(function() {
    $template = $(".template-storage-detail");

    // STORAGES READY
    storage_ready=$('#storage').DataTable({
      "initComplete": function (settings, json) {
        let searchStorageId = getGroupParam()
        if (searchStorageId) {
          this.api().column(2).search(searchStorageId).draw();
          storage_ready.column(2).footer(2).firstChild.value = searchStorageId;
        }
      },
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
          "className": 'details-control',
          "orderable": false,
          "data": null,
          "width": "10px",
          "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
        },
        { "data": "directory_path",},
        { "data": "id",},
        { "data": "type",},
        { "data": null},
        { "data": null},
        { "data": "parent", "defaultContent": ""},
        { "data": "user_name",},
        { "data": "category",},
        { "data": "domains",},
        { "data": "status_logs",},
        { "data": "task",}
      ],
      "columnDefs": [
        {
          "targets": 4,
          "render": function ( data, type, full, meta ) {
            if( 'qemu-img-info' in full){
              return Math.round(full["qemu-img-info"]["virtual-size"]/1024/1024/1024)+" GB"
            }else{
              return '-'
            }
          }
        },
        {
          "targets": 5,
          "render": function ( data, type, full, meta ) {
            if( 'qemu-img-info' in full){
              return Math.round(full["qemu-img-info"]["actual-size"]/1024/1024/1024)+' GB ('+Math.round(full["qemu-img-info"]["actual-size"]*100/full["qemu-img-info"]["virtual-size"])+'%)'
            }else{
              return '-'
            }
          }
        },
        {
          "targets": 10,
          "render": function ( data, type, full, meta ) {
            if( "status_logs" in full ){
              return moment.unix(full["status_logs"][full["status_logs"].length -1]["time"]).fromNow()
            }
            return "-"
          }
        },
        {
          "targets": 11,
          "render": function ( data, type, full, meta ) {
            if( "task" in full ){
              return '<button type="button" data-task="'+full.task+'" class="btn btn-pill-right btn-info btn-xs btn-task-info" title="Show last task info"><i class="fa fa-tasks"></i></button>';
            }else{
              return "-"
            }
          }
        },
        {
          "targets": 12,
          "render": function ( data, type, full, meta ) {
            return '<button type="button" data-id="'+full.id+'" class="btn btn-pill-right btn-success btn-xs btn-check-qemu-img-info" title="Check disk info"><i class="fa fa-refresh"></i></button>';
          }
        },
      ],
      footerCallback: function () {
        var api = this.api();
        // Current page
        pageTotal = api.column(4, {search: 'applied'}).data().reduce(function (a, b) {
          if( 'qemu-img-info' in b){
            return a + b["qemu-img-info"]["actual-size"]/1024/1024/1024
          } else {
            return a + 0
          }
        }, 0);
        // All pages
        total = api.column(4).data().reduce(function(a, b) {
          if( 'qemu-img-info' in b){
            return a + b["qemu-img-info"]["actual-size"]/1024/1024/1024
          } else {
            return a + 0
          }
        }, 0);

        $('.storage-total-size').html('Applied  filter storage size: ' + pageTotal.toFixed(1) + ' GB ( Total storage size: ' + total.toFixed(1) + ' GB )');
      }
    });

    $('#storage tfoot tr:first th').each( function () {
      var title = $(this).text();
      if ([''].indexOf(title) == -1){
        $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
      }
    } );

    storage_ready.columns().every( function () {
      var that = this;
      $( 'input', this.footer() ).on( 'keyup change', function () {
        if ( that.search() !== this.value ) {
          that.search( this.value ).draw();
        }
      } );
    } );

    $('#storage tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest("tr");
        var row = storage_ready.row(tr);
        var rowData = row.data();

        if (row.child.isShown()) {
          // This row is already open - close it
          row.child.hide();
          tr.removeClass("shown");

          // Destroy the Child Datatable
          $("#cl" + rowData.clientID)
            .DataTable()
            .destroy();
        } else {

          // Close other rows
          if (storage_ready.row('.shown').length) {
            $('.details-control', storage_ready.row('.shown').node()).click();
          }

            // Open this row
            row.child(format(rowData)).show();
            var id = rowData.id;

            childTable = $("#cl" + id).DataTable({
              dom: "t",
              ajax: {
                url: "/api/v3/storage/" + id+"/parents",
                contentType: "application/json",
                type: "GET",
              },
              sAjaxDataProp: "",
              language: {
                loadingRecords:
                  '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
              },
              columns: [
                { data: null, title: "#", render: function (data, type, full, meta) { return meta.row + 1; } },
                { data: "id", title: "storage id", render: function (data, type, full, meta) { if (meta.row == 0) { return '<b>'+data+'</b>' } else { return data } } },
                { data: "status", title: "storage status" },
                { data: "parent_id", title: "parent storage id" },
                { data: "domains", title: "domains",
                  render: function (data, type, full, meta) {
                    links = []
                    $(data).each(function (index, value) {
                      let kind = value.kind.charAt(0).toUpperCase() + value.kind.slice(1).replace(/_/g, ' ')
                      links[index] = '<a href="/isard-admin/admin/domains/render/'+kind+'s?searchDomainId='+value.id+'"><b>'+kind[0]+': </b>'+value.name+'</a>'
                    });
                    return links.join(', ')
                  }
                },
              ],
              columnDefs: [
              ],
              order: [],
              select: false,
            });

            tr.addClass("shown");
          }
    } );

    $('.btn-tree').on('click', function(){
      $('form').each(function() {
        this.reset();
      })

      $('#modalTreeDisk').modal({
        backdrop: 'static',
        keyboard: false
      }).modal('show');

      populateDiskTree();
    });

    // STORAGES IN OTHER STATUSES
    storage_other=$('#storage_other').DataTable({
      "initComplete": function (settings, json) {
        let searchStorageId = getGroupParam()
        if (searchStorageId) {
          this.api().column(3).search(searchStorageId).draw();
          storage_other.column(3).footer(3).firstChild.value = searchStorageId;
        }
      },
      "ajax": {
        "url": "/api/v3/admin/storage/other",
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
          "className": 'details-control',
          "orderable": false,
          "data": null,
          "width": "10px",
          "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
        },
        { "data": "status",},
        { "data": "directory_path",},
        { "data": "id",},
        { "data": "type",},
        { "data": null},
        { "data": null},
        { "data": "parent", "defaultContent": ""},
        { "data": "user_name",},
        { "data": "category",},
        { "data": "domains",},
        { "data": "status_logs",},
        { "data": "task",}
      ],
      "columnDefs": [
        {
          "targets": 5,
          "render": function ( data, type, full, meta ) {
            if( 'qemu-img-info' in full){
              return Math.round(full["qemu-img-info"]["virtual-size"]/1024/1024/1024)+" GB"
            }else{
              return '-'
            }
          }
        },
        {
          "targets": 6,
          "render": function ( data, type, full, meta ) {
            if( 'qemu-img-info' in full){
              return Math.round(full["qemu-img-info"]["actual-size"]/1024/1024/1024)+' GB ('+Math.round(full["qemu-img-info"]["actual-size"]*100/full["qemu-img-info"]["virtual-size"])+'%)'
            }else{
              return '-'
            }
          }
        },
        {
          "targets": 11,
          "render": function ( data, type, full, meta ) {
            if( "status_logs" in full ){
              return moment.unix(full["status_logs"][full["status_logs"].length -1]["time"]).fromNow()
            }
            return "-"
          }
        },
        {
          "targets": 12,
          "render": function ( data, type, full, meta ) {
            if( "task" in full ){
              return '<button type="button" data-task="'+full.task+'" class="btn btn-pill-right btn-info btn-xs btn-task-info" title="Show last task info"><i class="fa fa-tasks"></i></button>';
            }else{
              return "-"
            }
          }
        },
        {
          "targets": 13,
          "render": function ( data, type, full, meta ) {
            return '<button type="button" data-id="'+full.id+'" class="btn btn-pill-right btn-success btn-xs btn-check-qemu-img-info" title="Check disk info"><i class="fa fa-refresh"></i></button>';
          }
        },
      ],
      footerCallback: function () {
        var api = this.api();
        // Current page
        pageTotal = api.column(5, {search: 'applied'}).data().reduce(function (a, b) {
          if( 'qemu-img-info' in b){
            return a + b["qemu-img-info"]["actual-size"]/1024/1024/1024
          } else {
            return a + 0
          }
        }, 0);
        // All pages
        total = api.column(5).data().reduce(function(a, b) {
          if( 'qemu-img-info' in b){
            return a + b["qemu-img-info"]["actual-size"]/1024/1024/1024
          } else {
            return a + 0
          }
        }, 0);

        $('.storage-other-total-size').html('Applied  filter storage size: ' + pageTotal.toFixed(1) + ' GB ( Total storage size: ' + total.toFixed(1) + ' GB )');
      }
    });

    $('#storage_other tfoot tr:first th').each( function () {
      var title = $(this).text();
      if ([''].indexOf(title) == -1){
        $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
      }
    } );

    storage_other.columns().every( function () {
      var that = this;
      $( 'input', this.footer() ).on( 'keyup change', function () {
        if ( that.search() !== this.value ) {
          that.search( this.value ).draw();
        }
      } );
    } );

    $('#storage_other tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest("tr");
        var row = storage_other.row(tr);
        var rowData = row.data();

        if (row.child.isShown()) {
          // This row is already open - close it
          row.child.hide();
          tr.removeClass("shown");

          // Destroy the Child Datatable
          $("#cl" + rowData.clientID)
            .DataTable()
            .destroy();
        } else {

          // Close other rows
          if (storage_other.row('.shown').length) {
            $('.details-control', storage_other.row('.shown').node()).click();
          }

            // Open this row
            row.child(format(rowData)).show();
            var id = rowData.id;

            childTable = $("#cl" + id).DataTable({
              dom: "t",
              ajax: {
                url: "/api/v3/storage/" + id+"/parents",
                contentType: "application/json",
                type: "GET",
              },
              sAjaxDataProp: "",
              language: {
                loadingRecords:
                  '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
              },
              columns: [
                { data: null, title: "#", render: function (data, type, full, meta) { return meta.row + 1; } },
                { data: "id", title: "storage id", render: function (data, type, full, meta) { if (meta.row == 0) { return '<b>'+data+'</b>' } else { return data } } },
                { data: "status", title: "storage status" },
                { data: "parent_id", title: "parent storage id" },
                { data: "domains", title: "domains",
                  render: function (data, type, full, meta) {
                    links = []
                    $(data).each(function (index, value) {
                      let kind = value.kind.charAt(0).toUpperCase() + value.kind.slice(1).replace(/_/g, ' ')
                      links[index] = '<a href="/isard-admin/admin/domains/render/'+kind+'s?searchDomainId='+value.id+'"><b>'+kind[0]+': </b>'+value.name+'</a>'
                    });
                    return links.join(', ')
                  }
                },
              ],
              columnDefs: [
              ],
              order: [],
              select: false,
            });

            tr.addClass("shown");
          }
    } );

    // STORAGES DELETED
    storage_deleted=$('#storage_deleted').DataTable( {
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
          { "data": null},
          { "data": "user_id"},
          { "data": "status_logs"},
          { "data": "domains"},
          { "data": "task", "defaultContent": "-"}
        ],
      "columnDefs": [
        {
          "targets": 2,
          "render": function ( data, type, full, meta ) {
            if( 'qemu-img-info' in full){
              return Math.round(full["qemu-img-info"]["virtual-size"]/1024/1024/1024)+" GB"
            }else{
              return '-'
            }
          }
        },
        {
          "targets": 3,
          "render": function ( data, type, full, meta ) {
            if( 'qemu-img-info' in full){
              return Math.round(full["qemu-img-info"]["actual-size"]/1024/1024/1024)+' GB ('+Math.round(full["qemu-img-info"]["actual-size"]*100/full["qemu-img-info"]["virtual-size"])+'%)'
            }else{
              return '-'
            }
          }
        },
        {
          "targets": 5,
          "render": function ( data, type, full, meta ) {
            return moment.unix(full["status_logs"][full["status_logs"].length -1]["time"]).fromNow()
          }
        },
        {
          "targets": 7,
          "render": function ( data, type, full, meta ) {
            if( "task" in full ){
              return '<button type="button" data-task="'+full.task+'" class="btn btn-pill-right btn-info btn-xs btn-task-info" title="Show last task info"><i class="fa fa-tasks"></i></button>';
            }else{
              return "-"
            }
          }
        },
        {
          "targets": 8,
          "render": function ( data, type, full, meta ) {
            return '<button type="button" data-id="'+full.id+'" class="btn btn-pill-right btn-success btn-xs btn-check-qemu-img-info" title="Check disk info"><i class="fa fa-refresh"></i></button>';
          }
        },
      ],
      footerCallback: function () {
        var api = this.api();
        // Current page
        pageTotal = api.column(2, {search: 'applied'}).data().reduce(function (a, b) {
          if( 'qemu-img-info' in b){
            return a + b["qemu-img-info"]["actual-size"]/1024/1024/1024
          } else {
            return a + 0
          }
        }, 0);
        // All pages
        total = api.column(2).data().reduce(function(a, b) {
          if( 'qemu-img-info' in b){
            return a + b["qemu-img-info"]["actual-size"]/1024/1024/1024
          } else {
            return a + 0
          }
        }, 0);
    
        $('.storage_deleted-total-size').html('Applied  filter storage size: ' + pageTotal.toFixed(1) + ' GB ( Total storage size: ' + total.toFixed(1) + ' GB )');
      }
    });

    $('#storage_deleted tfoot tr:first th').each( function () {
      var title = $(this).text();
      if ([''].indexOf(title) == -1){
        $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
      }
    } );

    storage_deleted.columns().every( function () {
      var that = this;
      $( 'input', this.footer() ).on( 'keyup change', function () {
        if ( that.search() !== this.value ) {
          that.search( this.value ).draw();
        }
      } );
    } );

    // STORAGES READED FROM STORAGE POOL
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
          { "data": "path"},
          { "data": "correct-chain"},
          { "data": null},
          { "data": null},
          { "data": "hyper"},
          { "data": "domains"},
          { "data": "domains_status"},
          { "data": "storage"},
          { "data": "storage_status"},
          { "data": "haschilds"},
          { "data": "tomigrate"},
          {
            "className": 'text-center',
            "data": null,
            "orderable": false,
            "defaultContent": '<input type="checkbox" class="form-check-input"></input>'
          }
        ],
        "columnDefs": [
          {
            "targets": 3,
            "render": function ( data, type, full, meta ) {
              if( 'migrate_data' in full && 'qemu-img-info' in full["migrate_data"]){
                return Math.round(full["migrate_data"]["qemu-img-info"]["virtual-size"]/1024/1024/1024)+" GB"
              }else{
                return '-'
              }
            }
          },
          {
            "targets": 4,
            "render": function ( data, type, full, meta ) {
              if( 'migrate_data' in full && 'qemu-img-info' in full["migrate_data"]){
                return Math.round(full["migrate_data"]["qemu-img-info"]["actual-size"]/1024/1024/1024)+' GB ('+Math.round(full["migrate_data"]["qemu-img-info"]["actual-size"]*100/full["migrate_data"]["qemu-img-info"]["virtual-size"])+'%)'
              }else{
                return '-'
              }
            }
          },
          {
            "targets": 0,
            "render": function ( data, type, full, meta ) {
              return '<button type="button" id="btn-info" class="btn btn-pill-right btn-success btn-xs"><i class="fa fa-info"></i></button>';
            }
          },
        ],
        footerCallback: function () {
          var api = this.api();
          // Current page
          pageTotal = api.column(4, {search: 'applied'}).data().reduce(function (a, b) {
            if( 'migrate_data' in b && 'qemu-img-info' in b["migrate_data"]){
              return a + b["migrate_data"]["qemu-img-info"]["actual-size"]/1024/1024/1024
            } else {
              return a + 0
            }
          }, 0);
          // All pages
          total = api.column(4).data().reduce(function(a, b) {
            if( 'migrate_data' in b && 'qemu-img-info' in b["migrate_data"]){
              return a + b["migrate_data"]["qemu-img-info"]["actual-size"]/1024/1024/1024
            } else {
              return a + 0
            }
          }, 0);
      
          $('.storage_physical-total-size').html('Applied  filter storage size: ' + pageTotal.toFixed(1) + ' GB ( Total storage size: ' + total.toFixed(1) + ' GB )');
        }
      });

      $('#storage_physical tfoot tr:first th').each( function () {
        var title = $(this).text();
        if (['', 'Selected'].indexOf(title) == -1){
          $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
        }
      } );
  
      storage_physical.columns().every( function () {
        var that = this;
        $( 'input', this.footer() ).on( 'keyup change', function () {
          if ( that.search() !== this.value ) {
            that.search( this.value ).draw();
          }
        } );
      } );

      $('#storage_physical tbody').on( 'click', 'button', function () {
        var data = storage_physical.row( $(this).parents('tr') ).data();
        switch($(this).attr('id')){
          case 'btn-info':
            $.ajax({
              type: "GET",
              url:
                "/api/v3/admin/storage/physical/storage_host",
              contentType: "application/json",
              success: function (storage_host) {
                $.ajax({
                  type: "POST",
                  url: storage_host+"/storage/disk/info",
                  headers: {"Authorization": "Bearer " +localStorage.getItem("token")},
                  data: JSON.stringify({
                    'path_id': data.path
                  }),
                  contentType: "application/json",
                  success: function (disk_info) {
                    new PNotify({
                      title: "Disk info.",
                        text: JSON.stringify(disk_info),
                        hide: true,
                        delay: 10000,
                        icon: 'fa fa-info',
                        opacity: 1,
                        type: 'info'
                    });
                  },
                });
              },
              error: function (xhr, ajaxOptions, thrownError) {
                if (xhr.status == 428) {
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
            rescan_pnotify = new PNotify({
              title: "Waiting storage",
                text: "Storage is looking for files in storage. Please wait, it can take some minutes...",
                hide: false,
                icon: 'fa fa-alert-sign',
                opacity: 1,
                type: "warning",
            });
            $.ajax({
              type: "GET",
              url:
                "/api/v3/admin/storage/physical/storage_host",
              contentType: "application/json",
              success: function (storage_host) {
                $.ajax({
                  type: "PUT",
                  url: storage_host+"/storage/disks",
                  contentType: "application/json",
                  success: function (data) {
                    storage_physical.ajax.reload();
                    rescan_pnotify.update({
                      title: "Physical storage",
                      text:  "Updated "+data.templates+" templates and "+data.desktops+" desktop disks from "+storage_host,
                      hide: true,
                      delay: 5000,
                      opacity: 1,
                      type: 'success'
                  });
                  },
                });
              },
              error: function (xhr, ajaxOptions, thrownError) {
                console.log(xhr)
                if (xhr.status == 428) {
                  new PNotify({
                      title: "ERROR accessing storage",
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
          })
          .on("pnotify.cancel", function () {});
      });

      $('#mactions').on('change', function () {
        action=$(this).val();
        names=''
        ids=[]

        if(storage_physical.rows('.active').data().length){
          $.each(storage_physical.rows('.active').data(),function(key, value){
            if(value["tomigrate"] == true){
              names+=value['path']+'\n';
              ids.push(value['path']);
            }
          });
          var text = "<b>You are about to\n- Activate maintenance mode\n- Stop all desktops\n To execute "+action+" these 'To Migrate' physical disks:\n\n "+names+"</b>"
        }else{
          $.each(storage_physical.rows({filter: 'applied'}).data(),function(key, value){
            if(value["tomigrate"] == true){
              ids.push(value['path']);
            }
          });
          var text = "<b>You are about to\n- Activate maintenance mode\n- Stop all desktops\n To execute "+action+" to "+ids.length+" disks!\n (Every 'To Migrate' desktop in table)</b>"
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
          width: "550"
        }).get().on('pnotify.confirm', function() {
          var notice = new PNotify({
            title: "<b>Migrating disks...</b>",
            text: "<b>Activating maintenance mode and stopping domains. \n Please, wait until the migration is completed.\n Migrating " + ids.length + " disks...</b>",
            hide: true,
            delay: 4250,
            icon: 'fa fa-alert',
            opacity: 1,
            type: 'warning',
            addclass: 'pnotify-center-large',
            width: "550"
          });
          $.ajax({
            type: "POST",
            url:"/api/v3/admin/storage/physical/multiple_actions/"+action,
            data: JSON.stringify({'paths':ids}),
            contentType: 'application/json',
            success: function(data){
              notice.update({
                title: "<b>Disks migrated</b>",
                text: ids.length + " disks migrated successfully \n Manteinance mode disabled.",
                hide: true,
                delay: 4250,
                icon: 'fa fa-success',
                opacity: 1,
                type: 'success',
              });
              storage_physical.ajax.reload()
            },
            always: function(data){
              $('#mactions option[value="none"]').prop("selected", true);
              $('#domains tr.active').removeClass('active')
              $('#mactions option[value="none"]').prop("selected",true);
            }
          });
        });
      });
    }

    // WS
    $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on)
})

// FUNCTIONS

//// TABLE BUTTON EVENTS
$(document).on('click', '.btn-task-info', function () {
  var element = $(this);
  var task = element.data("task");
  element.html('<i class="fa fa-spinner fa-pulse"></i>')
  $.ajax({
    type: 'GET',
    url: '/api/v3/task/' + task,
    contentType: 'application/json',
    success: function (result) {
      element.html('<i class="fa fa-tasks"></i>')
      new PNotify({
        title: 'Last task info',
        text: '<pre><li><b>TASK ID</b>: '+result.id+'</li><li><b>TASK</b>: '+result.task+'</li><li><b>USER ID</b>: '+result.user_id+'</li><li><b>TASK STATUS</b>: '+result.status+'</li><li><b>RESULT</b>: '+JSON.stringify(result.result, undefined, 2)+'</li></pre>',
        hide: false,
        icon: '',
        opacity: 1,
        type: 'info',
        addclass: 'pnotify-center-large',
    })
    },
    error: function (xhr, ajaxOptions, thrownError) {
      element.html('<i class="fa fa-tasks" style="color:red" title="Task not found!"></i>')
      new PNotify({
        title: 'Error',
        text: xhr.responseJSON.description,
        hide: true,
        delay: 3000,
        icon: 'fa fa-warning',
        opacity: 1,
        type: 'error'
      });
    }
  });
})

$(document).on('click', '.btn-check-qemu-img-info', function () {
  element = $(this);
  var id = element.data("id");
  element.html('<i class="fa fa-spinner fa-pulse"></i>')
  $.ajax({
    type: 'PUT',
    url: '/api/v3/storage/' + id + '/check_backing_chain',
    contentType: 'application/json',
    success: function (result) {
      element.html('<i class="fa fa-refresh"></i>')
      new PNotify({
        title: 'Updated',
        text: 'Storage backing chain succesfully',
        hide: true,
        delay: 2000,
        icon: '',
        opacity: 1,
        type: 'success'
    })
    },
    error: function (xhr, ajaxOptions, thrownError) {
      element.html('<i class="fa fa-refresh" style="color:red" title="Error checking backing chain!"></i>')
      new PNotify({
        title: 'Error',
        text: xhr.responseJSON.description,
        hide: true,
        delay: 3000,
        icon: 'fa fa-warning',
        opacity: 1,
        type: 'error'
      });
    }
  });
})

function socketio_on(){
  socket.on('storage', function(data) {
    var data = JSON.parse(data);
    if( typeof(storage_ready.row('#'+data.id).id())!='undefined' ){
      actual_data=storage_ready.row("#"+data.id).data()
      if( "status" in data && data.status != 'ready' ){
        storage_ready.row('#'+data.id).remove().draw();
        add_to_status_table(data.status, {...actual_data,...data})
      }else{
        storage_ready.row('#'+data.id).data({...actual_data,...data}).invalidate();
      }
    }else if( typeof(storage_deleted.row('#'+data.id).id())!='undefined' ){
      actual_data=storage_deleted.row("#"+data.id).data()
      if( "status" in data && data.status != 'deleted' ){
        storage_deleted.row('#'+data.id).remove().draw();
        add_to_status_table(data.status, {...actual_data,...data})
      }else{
        storage_deleted.row('#'+data.id).data({...actual_data,...data}).invalidate();
      }
    }else if( typeof(storage_other.row('#'+data.id).id())!='undefined' ){
      actual_data=storage_other.row("#"+data.id).data()
      if( "status" in data && data.status != 'ready' ){
        storage_other.row('#'+data.id).remove().draw();
        add_to_status_table(data.status, {...actual_data,...data})
      }else{
        storage_other.row('#'+data.id).data({...actual_data,...data}).invalidate();
      }
    }
  });
}

function add_to_status_table(status, data){
  switch(status){
    case 'ready':
      new PNotify({
        title: 'Disk status changed to ready',
        text: 'Disk is now ready and moved to the ready disks table',
        hide: true,
        delay: 5000,
        icon: '',
        opacity: 1,
        type: 'warning'
      })
      storage_ready.row.add(data).draw();
      break;
    case 'deleted':
      new PNotify({
        title: 'Disk status changed to deleted',
        text: 'Disk is now deleted and moved to the deleted disks table',
        hide: true,
        delay: 5000,
        icon: '',
        opacity: 1,
        type: 'warning'
      })
      storage_deleted.row.add(data).draw();
      break;
    default:
      new PNotify({
        title: 'Disk status changed to '+status,
        text: 'Disk is now '+status+' and moved to the other status disks table',
        hide: true,
        delay: 5000,
        icon: '',
        opacity: 1,
        type: 'warning'
      })
      storage_other.row.add(data).draw();
  }
}

function format(rowData) {
    var childTable =
      '<table id="cl' +
      rowData.id +
      '" class="display compact nowrap w-100" width="100%">' +
      "</table>";
    return $(childTable).toArray();
}

function populateDiskTree(){
  $(":ui-fancytree").fancytree("destroy")
  $("#modalTreeDisk .storage_disk_tree").fancytree({
    extensions: ["table"],
    table: {
      indentation: 20,      // indent 20px per node level
      nodeColumnIdx: 1,     // render the node title into the 2nd column
    },
    source: {
      url: "/api/v3/admin/storage/tree_list",
      cache: false
    },
    lazyLoad: function(event, data){
      data.result = $.ajax({
        url: "/api/v3/admin/storage/tree_list",
        dataType: "json"
      });
    },
    renderColumns: function(event, data) {
      var node = data.node,
      $tdList = $(node.tr).find(">td");
      $tdList.eq(0).text(node.getIndexHier());
      // Fancy tree populates id column (1) as title
      $tdList.eq(2).text(node.data.user_name);
      if (node.data.directory_path == "/isard/templates") {
        $tdList.eq(3).text("Template");
      } else if (node.data.directory_path == "/isard/groups") {
        $tdList.eq(3).text("Desktop");
      }
      $tdList.eq(4).text(node.data.category_name);
    }
  });
}
