/*
* Copyright 2022 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$(document).ready(function () {

  var desktopsTableCols = [
    {
      data: 'id',
      title: 'Id'
    },
    {
      data: 'name',
      title: 'Name'
    },
    {
      data: 'username',
      title: 'User'
    },
    {
      data: 'category',
      title: 'Category'
    },
    {
      data: 'group',
      title: 'Group'
    },
    {
      data: 'accessed',
      title: 'Last access',
      render: function (accessed) {
        return moment.unix(accessed).fromNow()
      }
    }
  ]

  var templatesTableCols = [
    {
      data: 'id',
      title: 'Id'
    },
    {
      data: 'name',
      title: 'Name'
    },
    {
      data: 'user',
      title: 'User'
    },
    {
      data: 'category',
      title: 'Category'
    },
    {
      data: 'group',
      title: 'Group'
    },
    {
      data: 'accessed',
      title: 'Last access',
      render: function (accessed) {
        return moment.unix(accessed).fromNow()
      }
    }
  ]

  var deploymentsTableCols = [
    {
      data: 'id',
      title: 'Id'
    },
    {
      data: 'name',
      title: 'Name'
    },
    {
      data: 'create_dict',
      title: 'Desktop name',
      render: function (create_dict) {
        return create_dict.name
      }
    },
    {
      data: 'user',
      title: 'User'
    },
    {
      data: 'category',
      title: 'Category'
    },
    {
      data: 'group',
      title: 'Group'
    }
  ]

  var storageTableCols = [
    {
      data: 'id',
      title: 'Id'
    },
    {
      data: 'directory_path',
      title: 'Path'
    },
    {
      data: 'status',
      title: 'Status'
    },
    {
      data: 'type',
      title: 'Format'
    },
    {
      data: 'qemu-img-info',
      title: 'Size',
      render: function (qemu_img_info) {
        if (qemu_img_info) {
          return Math.round(qemu_img_info["virtual-size"] / 1024 / 1024 / 1024) + " GB"
        } else {
          return '-'
        }
      }
    },
    {
      data: 'qemu-img-info',
      title: 'Used',
      render: function (qemu_img_info) {
        if (qemu_img_info) {
          return Math.round(qemu_img_info["actual-size"] / 1024 / 1024 / 1024) + " GB"
        } else {
          return '-'
        }
      }
    },
    {
      data: 'parent',
      title: 'Parent'
    },
    {
      data: 'user',
      title: 'User',
    },
    {
      data: 'category',
      title: 'Category',
    },
    {
      data: 'domains',
      title: 'Domains'
    }
  ]

  var usersTableCols = [
    {
      data: 'id',
      title: 'Id'
    },
    {
      data: 'name',
      title: 'Name'
    },
    {
      data: 'provider',
      title: 'Provider'
    },
    {
      data: 'category',
      title: 'Category'
    },
    {
      data: 'uid',
      title: 'Uid'
    },
    {
      data: 'username',
      title: 'Username'
    },
    {
      data: 'role',
      title: 'Role'
    },
    {
      data: 'group',
      title: 'Group'
    }
  ]

  var groupsTableCols = [
    {
      data: 'id',
      title: 'Id'
    },
    {
      data: 'name',
      title: 'Name'
    },
    {
      data: 'description',
      title: 'Description'
    },
    {
      data: 'linked_groups',
      title: 'Linked Groups'
    }
  ]

  var categoriesTableCols = [
    {
      data: 'id',
      title: 'Id'
    },
    {
      data: 'name',
      title: 'Name'
    },
    {
      data: 'description',
      title: 'Description'
    }
  ]

  $recycle_bin_details_template = $(".template-recycle_bin-detail");
  $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on)
  var recyclebin_domains = $('#recyclebin_domains').DataTable({
    "ajax": {
      "url": "/api/v3/recycle_bin/item_count",
      "contentType": "application/json",
      "type": 'GET',
    },
    "sAjaxDataProp": "",
    "language": {
      "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
    },
    "rowId": "id",
    "deferRender": true,
    "createdRow": (row, data, index) => {
      if (!['deleted', 'restored', 'deleting'].includes(data.status) ) {
        if ($('thead #select-all').is(':checked')) {
          $(row).find('.select-checkbox input[type="checkbox"]').prop('checked', true)
          $(row).addClass('active');
        } else {
          $(row).find('.select-checkbox input[type="checkbox"]').prop('checked', false)
          $(row).removeClass('active');
        }
      }
    },
    "columns": [
      {
        className: "details-control",
        orderable: false,
        data: null,
        defaultContent: '<button id="btn-details" class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
      },
      {
        "data": "accessed",
        "title": "Deleted",
        render: function (accessed) {
          return moment.unix(accessed).fromNow()
        }
      },
      {
        "data": "status",
        "title": "Status"
      },
      {
        "data": "agent_name",
        "title": "Agent name"
      },
      {
        "data": "agent_type",
        "title": "Agent type"
      },
      {
        "data": "owner_name",
        "title": "Owner name"
      },
      {
        "data": "item_type",
        "title": "Item type"
      },
      {
        "data": "desktops",
        "title": "Deleted desktops",
      },
      {
        "data": "templates",
        "title": "Deleted templates",
      },
      {
        "data": "deployments",
        "title": "Deleted deployments",
      },
      {
        "data": "storages",
        "title": "Deleted storages",
      },
      {
        "data": "logs",
        "title": "Last modification",
        render: function (logs) {
          try {
            return moment.unix(logs.slice(-1)[0].time).fromNow()
          } catch {
            return null
          }
        }
      },
      {
        "className": 'actions-control',
        "orderable": false,
        "data": null,
        "width": "60px",
        render: function (data, type, row, meta) {
          if (!['deleted', 'restored', 'deleting'].includes(row.status) ) {
            return '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button> \
                    <button id="btn-restore" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-undo" style="color:darkgreen"></i></button>'
          }
        }
      },
      {
        "title": '<input type="checkbox" id="select-all" class="form-check-input">',
        "data": null,
        "orderable": false,
        "data": null,
        "width": "60px",
        className: 'select-checkbox',
        render: function (data, type, row, meta) {
          if (!['deleted', 'restored', 'deleting'].includes(row.status) ) {
            return '<input type="checkbox" class="form-check-input"></input>'
          }
        },
      },
      {
        "data": "id",
        "title": "Id",
        "visible": false
      }
    ],
  });

  $('thead #select-all').on('click', function (event) {
    var rows = recyclebin_domains.rows({ filter: 'applied' }).data();
    var selectAll = $('#select-all').is(':checked')
    $.each(rows, function (index, row) {
      if (!['deleted', 'restored', 'deleting'].includes(row.status) ) {
        $("#" + row.id).find('.select-checkbox input[type="checkbox"]').prop('checked', selectAll)
        selectAll ? $("#" + row.id).addClass('active') : $("#" + row.id).removeClass('active')
      }
    })
  });

  adminShowIdCol(recyclebin_domains)
  selectAutomaticDelete();

  $("#recyclebin_domains tbody").on('click', 'button', function () {
    tr = $(this).closest("tr")
    var data = recyclebin_domains.row($(this).parents('tr')).data()
    row = recyclebin_domains.row(tr)
    switch ($(this).attr('id')) {
      case 'btn-details':
        if (row.child.isShown()) {
          // Close opened row
          row.child.hide();
          tr.removeClass("shown");
        } else {
          // Close other rows
          if (recyclebin_domains.row('.shown').length) {
            $('.details-control', recyclebin_domains.row('.shown').node()).click();
          }
          // Open this row
          row.child(renderRecycleBinDetail(row.data())).show()
          fetchRecycleBin(row.data()['id'])
          tr.addClass('shown');
        }
        break;
      case 'btn-delete':
        new PNotify({
          title: 'Delete disk',
          text: "Do you really want to permanently delete the bin " + data.id + "?",
          hide: false,
          opacity: 0.9,
          confirm: { confirm: true },
          buttons: { closer: false, sticker: false },
          history: { history: false },
          addclass: 'pnotify-center'
        }).get().on('pnotify.confirm', function () {
          $.ajax({
            type: "DELETE",
            url: '/api/v3/recycle_bin/delete/' + row.data()['id'],
            contentType: "application/json",
            error: function (xhr, ajaxOptions, thrownError) {
              new PNotify({
                title: "ERROR deleting storage",
                text: xhr.responseJSON.description,
                hide: true,
                delay: 3000,
                icon: 'fa fa-warning',
                opacity: 1,
                type: 'error'
              });
            }
          })
        })
        break;
      case 'btn-restore':
        new PNotify({
          title: `Restore <strong>${data['item_type']}</strong> and all associated storage?`,
          text: `${data.desktops} desktops \n ${data.templates} templates \n ${data.deployments} deployments \n ${data.storages} disks`,
          hide: false,
          opacity: 0.9,
          type: "info",
          icon: "fa fa-warning",
          confirm: { confirm: true },
          buttons: { closer: false, sticker: false },
          history: { history: false },
          addclass: 'pnotify-center'
        }).get().on('pnotify.confirm', function () {
          var notice = new PNotify({
            text: 'Restoring storage...',
            hide: false,
            opacity: 1,
            icon: 'fa fa-spinner fa-pulse'
          })
          $.ajax({
            url: "/api/v3/recycle_bin/restore/" + data.id,
            method: "GET",
            error: function (xhr) {
              notice.update({
                title: `ERROR restoring ${data['item_type']}`,
                text: xhr.responseJSON.description,
                type: 'error',
                hide: true,
                icon: 'fa fa-warning',
                delay: 5000,
                opacity: 1
              });
            },
            success: function () {
              notice.update({
                title: `Restored ${data['item_type']} `,
                text: '',
                hide: true,
                delay: 5000,
                icon: 'fa fa-check',
                opacity: 1,
                type: 'success'
              })
            }
          });
        });
        break;
    }

    function renderRecycleBinDetail(d) {
      $newPanel = $recycle_bin_details_template.clone();
      $newPanel.html(function (i, oldHtml) {
        return oldHtml.replace(/d.id/g, d.id);
      });
      return $newPanel
    }

    function fetchRecycleBin(recycle_bin_id) {
      $.ajax({
        url: "/api/v3/recycle_bin/" + recycle_bin_id,
        contentType: "application/json",
        type: "GET",
        success: function (result) {
          loadDatatable('#recycleBinDesktopsTable', 'desktops', result, desktopsTableCols)
          loadDatatable('#recycleBinTemplatesTable', 'templates', result, templatesTableCols)
          loadDatatable('#recycleBinStorageTable', 'storages', result, storageTableCols)
          loadDatatable('#recycleBinDeploymentsTable', 'deployments', result, deploymentsTableCols)
          loadDatatable('#recycleBinUsersTable', 'users', result, usersTableCols)
          loadDatatable('#recycleBinGroupsTable', 'groups', result, groupsTableCols)
          loadDatatable('#recycleBinCategoriesTable', 'categories', result, categoriesTableCols)
        },
        error: function (data) {
        }
      });
    }

    function loadDatatable(tableId, kind, data, columns) {
      $(`#${kind}-panel .quantity`).html(`(${data[kind].length} items)`)
      if ($.fn.dataTable.isDataTable(tableId)) {
        $(tableId).DataTable().destroy();
      }

      table = $(tableId).DataTable({
        data: data[kind],
        columns: columns
      })
    }   
  });
  
  function socketio_on(){
    socket.on('update_recycle_bin', function(data){
      dtUpdateInsert(recyclebin_domains,data,false);
    })
    socket.on('add_recycle_bin', function(data){
      dtUpdateInsert(recyclebin_domains,data,false);
    })
  }

  recyclebin_domains.on( 'click', 'tr[role="row"]', function (e) {
    toggleRow(this, e);
  });
  
  $('#mactions').on('change', function () {
    let action = $(this).val();
    let ids = []

    // Selected desktops
    recyclebin_domains.rows({ filter: 'applied' }).every(function () {
      var rowNodes = this.nodes();
      var rowData = this.data();
      if ($('#select-all').is(':checked')) {
        if (!['deleted', 'restored', 'deleting'].includes(rowData.status)) {
          ids.push(rowData.id)
        }
      } else {
        rowNodes.each(function () {
          if ($(this).hasClass('active')) {
            ids.push(rowData.id);
          }
        });
      }
    })
    if (ids.length) {
      new PNotify({
        title: "Confirmation Needed",
        text: "Are you sure you want to " + action + " " + ids.length + " recycle bin entries?",
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
        var method = (action == "delete") ? "DELETE" : (action == "restore") ? "GET" : "";
        ids.forEach(function(id) {
          $.ajax({
            type: method,
            url: '/api/v3/recycle_bin/' + action + '/' + id,
            success: function(data){
              $('#mactions option[value="none"]').prop("selected", true);
              $('#recyclebin_domains tr.active .form-check-input').prop("checked", false);
              $('#recyclebin_domains tr.active').removeClass('active')
              $('thead #select-all').prop("checked", false);
              new PNotify({
                title: 'Success',
                text: 'Recycle bin entries ' + action + ' performed successfully',
                hide: true,
                delay: 2000,
                icon: 'fa fa-' + data.icon,
                opacity: 1,
                type: 'success'
              });
            },
            error: function(xhr){
              new PNotify({
                title: 'Error',
                text: 'Couldn\'t ' + action + ' recycle bin entries ',
                type: 'error',
                hide: true,
                icon: 'fa fa-warning',
                delay: 5000,
                opacity: 1
              })
            }
          })
        });
      }).on('pnotify.cancel', function () {
        $('#mactions option[value="none"]').prop("selected", true);
      })
    // No rows selected
    } else {
      $('#mactions option[value="none"]').prop("selected", true);
      return new PNotify({
        type: "warning",
        title: "<b>Please select items to delete<b>",
        hide: true,
        opacity: 0.9,
        history: {
          history: false
        },
        addclass: 'pnotify-center-large',
        width: '550',
        delay: 5000,
      })
    }
  });
});

$("#maxtime").on("change", function () {
  var max_delete_period = $(this).val();
  new PNotify({
    title: "Confirm Change",
    text: ($('meta[id=user_data]').attr('data-role') == 'admin') ?
      "Changing the maximum delete period will affect all categories' custom time. Proceed?" :
      "Recycled storage older than the selected time will be permanently deleted. Proceed?",
    hide: false,
    type: 'info',
    icon: 'fa fa-warning',
    opacity: 0.9,
    confirm: {
      confirm: true,
    },
    buttons: {
      closer: false,
      sticker: false,
    },
    history: {
      history: false,
    },
    addclass: "pnotify-center",
  })
    .get()
    .on("pnotify.confirm", function () {
      $.ajax({
        url: "/scheduler/recycle_bin/" + max_delete_period,
        method: "PUT",
      }).done(function (data) {
        new PNotify({
          title: "Maximum delete period set successfully",
          text: ``,
          hide: true,
          type: 'success',
          opacity: 0.9,
          addclass: "pnotify-center",
        })
      });
    })
    .on("pnotify.cancel", function () {
      selectAutomaticDelete();
    });
});

function selectAutomaticDelete() {
  $.ajax({
    type: "GET",
    url: "/scheduler/recycle_bin_delete/max_time",
    success: function (data) {
      $('#maxtime').val(data)
      if (data !== "null" && $('meta[id=user_data]').attr('data-role') != 'admin') {
        var maxTime = parseInt(data);
        $('#maxtime option').each(function () {
            if (($(this).val() > maxTime || $(this).val() == "null")) {
                $(this).remove();
            }
        });
      }
    }
  });
}