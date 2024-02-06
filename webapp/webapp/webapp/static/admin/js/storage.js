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
      "rowId": function ( row ) {
        return row.id.replaceAll("/", "_");
      },
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
          "targets": 9,
          "render": function ( data, type, full, meta ) {
            if( 'domains' in full){
              return full['domains'].length
            } else {
              return 0
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

    // storage_ready.columns().every( function () {
    //   var that = this;
    //   $( 'input', this.footer() ).on( 'keyup change', function () {
    //     if ( that.search() !== this.value ) {
    //       that.search( this.value ).draw();
    //     }
    //   } );
    // } );

    $('#storage tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest("tr");
        var row = storage_ready.row(tr);
        var rowData = row.data();

        if (row.child.isShown()) {
          // This row is already open - close it
          row.child.hide();
          tr.removeClass("shown");

          // Destroy the Child Datatable
          $('#cl' + tr.attr("id"))
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

            childTable = $('#cl' + tr.attr("id")).DataTable({
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
      "rowId": function ( row ) {
        return row.id.replaceAll("/", "_");
      },
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

    // TODO: Check why it breaks the global search
    // storage_other.columns().every( function () {
    //   var that = this;
    //   $( 'input', this.footer() ).on( 'keyup change', function () {
    //     if ( that.search() !== this.value ) {
    //       that.search( this.value ).draw();
    //     }
    //   } );
    // } );

    $('#storage_other tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest("tr");
        var row = storage_other.row(tr);
        var rowData = row.data();

        if (row.child.isShown()) {
          // This row is already open - close it
          row.child.hide();
          tr.removeClass("shown");

          // Destroy the Child Datatable
          $('#cl' + tr.attr("id"))
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

            childTable = $('#cl' + tr.attr("id")).DataTable({
              dom: "t",
              ajax: {
                url: "/api/v3/storage/" + id + "/parents",
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

  $('.mactionsStorage').on('change', function () {
    let action = $(this).val();
    let actionText = $(this).find('option:selected').text();
    let status = $(this).attr('status')
    let tableId = '#' + $(this).attr('selectedTableId')
    let appliedFilter = $(tableId).DataTable().search();

    if (appliedFilter) {
      let ids = []
      $(tableId).DataTable().rows({ filter: 'applied' }).every(function () {
        ids.push(this.data().id);
      })
      new PNotify({
        title: "Confirmation Needed",
        text: "The action '" + actionText + "' will be performed in " + ids.length + " storages. Are you sure?",
        hide: false,
        opacity: 0.9,
        type: "error",
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
        document.body.classList.add('loading-cursor')
        $.ajax({
          type: "PUT",
          url: '/api/v3/storages/status',
          data: JSON.stringify({
            ids: ids
          }),
          contentType: "application/json",
          success: function (data) {
            document.body.classList.remove('loading-cursor')
            $('.mactionsStorage option[value="none"]').prop("selected", true);
            $('thead #select-all').prop("checked", false);
            new PNotify({
              title: 'Success',
              text: ' Storages ' + action + ' performed successfully',
              hide: true,
              delay: 2000,
              icon: 'fa fa-' + data.icon,
              opacity: 1,
              type: 'success'
            });
          },
          error: function (xhr) {
            document.body.classList.remove('loading-cursor')
            $('.mactionsStorage option[value="none"]').prop("selected", true);
            new PNotify({
              title: 'Error',
              text: 'Couldn\'t perform the action \'' + actionText + '\' correctly',
              type: 'error',
              hide: true,
              icon: 'fa fa-warning',
              delay: 5000,
              opacity: 1
            })
          }
        })
      }).on('pnotify.cancel', function () {
        $('.mactionsStorage option[value="none"]').prop("selected", true);
      })
      // No rows selected will perform the action over all table data
    } else {
      new PNotify({
        title: 'Warning!',
        text: "You are about to perform the action '" + actionText + "' in all the storages in the table!\nPlease write <b>\"I'm aware\"</b> in order to confirm the action",
        hide: false,
        opacity: 0.9,
        type: 'error',
        confirm: {
          confirm: true,
          prompt: true,
          prompt_multi_line: false,
          buttons: [
            {
              text: "Ok",
              addClass: "",
              promptTrigger: true,
              click: function (notice, value) {
                if (value == "I'm aware") {
                  notice.remove();
                  document.body.classList.add('loading-cursor')
                  $.ajax({
                    type: "PUT",
                    url: '/api/v3/storages/status/' + status,
                    contentType: "application/json",
                    success: function (data) {
                      document.body.classList.remove('loading-cursor')
                      $('.mactionsStorage option[value="none"]').prop("selected", true);
                      $('thead #select-all').prop("checked", false);
                      new PNotify({
                        title: 'Success',
                        text: ' Storages ' + action + ' performed successfully',
                        hide: true,
                        delay: 2000,
                        icon: 'fa fa-' + data.icon,
                        opacity: 1,
                        type: 'success'
                      });
                    },
                    error: function (xhr) {
                      document.body.classList.remove('loading-cursor')
                      $('.mactionsStorage option[value="none"]').prop("selected", true);
                      new PNotify({
                        title: 'Error',
                        text: 'Couldn\'t perform the action \'' + actionText + '\' correctly',
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 5000,
                        opacity: 1
                      })
                    }
                  })
                }
              }
            },
            {
              text: "Cancel",
              addClass: "",
              click: function (notice) {
                notice.remove();
                $('.mactionsStorage option[value="none"]').prop("selected", true);
              }
            }]
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
      })
    }
  });

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
      "rowId": function ( row ) {
        return row.id.replaceAll("/", "_");
      },
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

    // storage_deleted.columns().every( function () {
    //   var that = this;
    //   $( 'input', this.footer() ).on( 'keyup change', function () {
    //     if ( that.search() !== this.value ) {
    //       that.search( this.value ).draw();
    //     }
    //   } );
    // } );

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
    if( typeof(storage_ready.row('#'+data.id.replaceAll("/", "_")).id())!='undefined' ){
      actual_data=storage_ready.row("#"+data.id.replaceAll("/", "_")).data()
      if( "status" in data && data.status != 'ready' ){
        storage_ready.row('#'+data.id.replaceAll("/", "_")).remove().draw();
        add_to_status_table(data.status, {...actual_data,...data})
      }else{
        storage_ready.row('#'+data.id.replaceAll("/", "_")).data({...actual_data,...data}).invalidate();
      }
    }else if( typeof(storage_deleted.row('#'+data.id.replaceAll("/", "_")).id())!='undefined' ){
      actual_data=storage_deleted.row("#"+data.id.replaceAll("/", "_")).data()
      if( "status" in data && data.status != 'deleted' ){
        storage_deleted.row('#'+data.id.replaceAll("/", "_")).remove().draw();
        add_to_status_table(data.status, {...actual_data,...data})
      }else{
        storage_deleted.row('#'+data.id.replaceAll("/", "_")).data({...actual_data,...data}).invalidate();
      }
    }else if( typeof(storage_other.row('#'+data.id.replaceAll("/", "_")).id())!='undefined' ){
      actual_data=storage_other.row("#"+data.id.replaceAll("/", "_")).data()
      if( "status" in data && data.status != 'ready' ){
        storage_other.row('#'+data.id.replaceAll("/", "_")).remove().draw();
        add_to_status_table(data.status, {...actual_data,...data})
      }else{
        storage_other.row('#'+data.id.replaceAll("/", "_")).data({...actual_data,...data}).invalidate();
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
      rowData.id.replaceAll("/", "_") +
      '" class="display compact nowrap w-100" width="100%">' +
      "</table>";
    return $(childTable).toArray();
}