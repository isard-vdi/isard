/*
 *   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
 *   Copyright (C) 2022 Lídia Montero Gutiérrez
 *
 *   This program is free software: you can redistribute it and/or modify
 *   it under the terms of the GNU Affero General Public License as published by
 *   the Free Software Foundation, either version 3 of the License, or
 *   (at your option) any later version.
 *
 *   This program is distributed in the hope that it will be useful,
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *   GNU Affero General Public License for more details.
 *
 *   You should have received a copy of the GNU Affero General Public License
 *   along with this program.  If not, see <https://www.gnu.org/licenses/>.
 *
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

$(document).ready(function () {
  storage_pools_table = $('#storage_pools').DataTable({
    "ajax": {
      "type": 'GET',
      "url": "/admin/storage_pools",
      "dataSrc": "",
      "contentType": "application/json",
    },
    "language": {
      "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
    },
    "columns": [
      {
        "className": 'details-control',
        "orderable": false,
        "data": null,
        "width": "10px",
        "defaultContent": '<button id="btn-details" class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
      },
      {
        "data": "enabled",
        "title": "Enabled",
        "width": '55px',
        render: function (enabled, type) {
          return renderEnabled(enabled, 'check');
        }
      },
      { "data": "id", "title": "Pool ID" },
      { "data": "name", "title": "Name" },
      { "data": "mountpoint", "title": "Mountpoint" },
      { "data": "categories_names", "title": "Categories", "render": function(data, type, full, meta) { 
        var categoryList = []
        $.each(data, function(index, category){
          categoryList.push(category["name"])
        })
        return categoryList.join(", ");
      } },
      { "data": "description", "title": "Description", 'defaultContent': '' },
      // { 
      //   "data": "startable",
      //   "title": "Startable",
      //   "render": function(data, type, full, meta) {
      //     return renderEnabled(full.startable, 'circle');
      //   }
      // },
      // { 
      //   "data": "read", 
      //   "title": "Read",
      //   "render": function(data, type, full, meta) {
      //     return renderEnabled(full.read, 'circle');
      //   }
      // },
      // { 
      //   "data": "write", 
      //   "title": "Write",
      //   "render": function(data, type, full, meta) {
      //     return renderEnabled(full.write, 'circle');
      //   }
      // },
      {
        className: "actions-control",
        orderable: false,
        width: '125px',
        data: null,
        title: "Action",
        render: function (data, type, full, meta) {
          if (data.id == "00000000-0000-0000-0000-000000000000") { return "" } else {
            return data.enabled ?
              `<!--'<button id="btn-allowed" class="btn btn-xs" type="button" data-placement="top" ><i class="fa fa-users" style="color:darkblue"></i></button>--> \
                  <button id="btn-edit" class="btn btn-xs" type="button" data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button> \
                  <button id="btn-enable" class="btn btn-xs" type="button" data-placement="top" ><i class="fa fa-power-off" style="color:darkgreen"></i></button>`
              :
              `<!--'<button id="btn-allowed" class="btn btn-xs" type="button" data-placement="top" ><i class="fa fa-users" style="color:darkblue"></i></button>--> \
                  <button id="btn-edit" class="btn btn-xs" type="button" data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button> \
                  <button id="btn-enable" class="btn btn-xs" type="button" data-placement="top" ><i class="fa fa-power-off" style="color:darkgreen"></i></button> \
                  <button id="btn-delete" class="btn btn-xs" type="button" data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>`
          }
        }
      },
    ],
  })

  $('.btn-add-new').on('click', function(){
    $("#modalAddStoragePool #modalAdd")[0].reset();
    $("#modalAddStoragePool #category").select2({
      dropdownParent: $("#modalAddStoragePool"),
    });
    populateCategory("#modalAddStoragePool", null);
    addPath("#modalAddStoragePool .path_base_mountpoint", "");
    
    $("#modalAddStoragePool").modal({
      backdrop: "static",
      keyboard: false,
    }).modal("show");
    $("#modalAddStoragePool #modalAdd").parsley();
  });

  $('#storage_pools tbody').on('click', 'button', function(e){
    tr = $(this).closest("tr");
    data = storage_pools_table.row($(this).parents('tr')).data();
    row = storage_pools_table.row(tr)
    switch ($(this).attr('id')) {
      case 'btn-details':
        storage_pools_table.rows('.shown').every(function () {
          this.child.hide();
          $(this.node()).removeClass('shown');
        });
        if (row.child.isShown()) {
          row.child.hide();
          tr.removeClass('shown');
        } else {
          tr.addClass('shown');
          row.child(renderStoragePoolsPaths(row.data())).show();
        }
        break;
      case 'btn-allowed':
        modalAllowedsFormShow("storage_pool", data);
        break;
      case 'btn-edit':
      if(data.id == "00000000-0000-0000-0000-000000000000"){
        return new PNotify({
          title: "ERROR editing pool",
          text: "Default pool can't be edited",
          hide: true,
          delay: 3000,
          icon: 'fa fa-warning',
          opacity: 1,
          type: 'error'
        });
      } else {
        $("#modalEditStoragePool #modalEdit")[0].reset();
        $('#modalEdit #pathsTableEdit tbody').html('');
        $("#modalEditStoragePool #category").select2({
          dropdownParent: $("#modalEditStoragePool"),
        });
        populateCategory("#modalEditStoragePool", data.categories);
            
        $("#modalEditStoragePool").modal({
          backdrop: "static",
          keyboard: false,
        }).modal("show");
        $("#modalEditStoragePool #modalEdit").parsley();
        $("#modalEdit #id").val(data.id);
        $("#modalEdit #name").val(data.name);
        $("#modalEdit #description").val(data.description);

        var fullMountpoint = data.mountpoint.split("/");
        var mountpointVar = fullMountpoint.pop();

        $("#modalEdit .path_base_mountpoint").text(fullMountpoint.join("/") + "/")

        $("#modalEdit #mountpoint").val(mountpointVar);
        $('#modalEdit #startable').iCheck(data.startable ? 'check' : 'uncheck').iCheck('update');
        $('#modalEdit #read').iCheck(data.read ? 'check' : 'uncheck').iCheck('update');
        $('#modalEdit #write').iCheck(data.write ? 'check' : 'uncheck').iCheck('update');
        if(data.id == "00000000-0000-0000-0000-000000000000"){
          $("#modalEdit #category").attr("disabled", true);
        } else {
          $("#modalEdit #category").attr("disabled", false);
        }

        const pathsTableEdit = $('#modalEdit #pathsTableEdit tbody')[0];
        paths = data.paths;

        for (const type in paths) {
          const pathArray = paths[type];
          for (let i = 0; i < pathArray.length; i++) {
            const pathObj = pathArray[i];
            const row = pathsTableEdit.insertRow();
            row.setAttribute('id', type);

            const typeCell = row.insertCell(0);
            typeCell.setAttribute('id', 'type');
            const pathCell = row.insertCell(1);
            const weightCell = row.insertCell(2);
            const buttonAddDelCell = row.insertCell(3);

            if (type === 'desktop') {
              typeCell.innerHTML = `<i class="fa fa-desktop fa-1x"></i><b id="${type}"> Desktops</b>`;
            } else if (type === 'template') {
              typeCell.innerHTML = `<i class="fa fa-cubes fa-1x"></i><b id="${type}"> Templates</b>`;
            } else if (type === 'media') {
              typeCell.innerHTML = `<i class="fa fa-circle-o fa-1x"></i><b id="${type}"> Media</b>`;
            } else if (type === 'volatile') {
              typeCell.innerHTML = `<i class="fa fa-clock-o fa-1x"></i><b id="${type}"> Volatile</b>`;
            } else {
              typeCell.innerHTML = `<b id="${type}">${type}</b>`;
            }
            pathObj.path = pathObj.path.split("/")[pathObj.path.split("/").length-1]

            pathCell.innerHTML = `<span class="path_base"></span><input id="path" name="${type}-patzh" class="roundbox" pattern="^[-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$" data-parsley-trigger="change" type="text" value="${pathObj.path}">`;
            weightCell.innerHTML = `<input id="weight" name="${type}-weight" type="number" value="${pathObj.weight}">`;
            buttonAddDelCell.innerHTML = `<input id='modalEdit-addrow-${type}' type='button' value='+' onclick='addRow("${type}", "modalEdit")'/> \
                                          <input id='modalEdit-delrow-${type}' type='button' value='-' onclick='delRow("${type}", "modalEdit")'/>`;

            if (i === pathArray.length - 1) {
              const additionalRow = pathsTableEdit.insertRow();
              const additionalCell = additionalRow.insertCell();
              additionalCell.setAttribute('colspan', '100%');
              additionalCell.style.borderTop = '3px solid rgb(221, 221, 221)';
            }
          }
        }
       }
       break;
      case 'btn-enable':
        let change = data["enabled"] ? "disable" : "enable";

        let prompt_msg = (change == "enable") ?
          "From now on, disks from this pool's categories will be created in the new paths defined"
          :
          "From now on, disks from this pool's categories will be created in default paths";

        let msg = (change == "enable") ?
          "This pool <b>will only become operational</b> after a system restart.Ensure that there is at least one hypervisor associated with this storage pool."
          :
          "";

        new PNotify({
          title: "<b>WARNING</b>",
          type: "error",
          text: "Are you sure you want to <b>" + change + "</b> pool " + data["name"] + "? " + prompt_msg,
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
            type: "PUT",
            url: "/admin/storage_pool/"+data["id"],
            data: JSON.stringify({'name':data["name"], 'enabled': !data.enabled}),
            contentType: "application/json",
            success: function (data) {
              new PNotify({
                title: 'Pool ' + change +'d successfully',
                text:  msg,
                hide: true,
                delay: 7000,
                icon: 'fa fa-' + data.icon,
                opacity: 1,
                type: change == "enable" ? 'warning' : 'success'
              });
              storage_pools_table.ajax.reload();
            },
            error: function (xhr, ajaxOptions, thrownError) {
              new PNotify({
                title: "ERROR updating pool",
                text: xhr.responseJSON.description,
                hide: true,
                delay: 3000,
                icon: 'fa fa-warning',
                opacity: 1,
                type: 'error'
              });
            }
          });
        }).on('pnotify.cancel', function() {});
        break;
      case 'btn-delete':
        if(data.id == "00000000-0000-0000-0000-000000000000"){
          return new PNotify({
            title: "ERROR deleting pool",
            text: "Default pool can't be removed",
            hide: true,
            delay: 3000,
            icon: 'fa fa-warning',
            opacity: 1,
            type: 'error'
          });
        }
        new PNotify({
          title: "<b>WARNING</b>",
          type: "error",
          text: "Are you sure you want to <b>delete</b> pool " + data["name"] + "?",
          hide: false,
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
          addclass: 'pnotify-center-large',
          width: '550'
        }).get().on("pnotify.confirm", function () {
          $.ajax({
            type: "DELETE",
            url: "/admin/storage_pool/"+data["id"],
            contentType: "application/json",
            success: function (data) {
              new PNotify({
                title: 'Deleted',
                text: 'Pool deleted successfully',
                hide: true,
                delay: 1000,
                icon: 'fa fa-' + data.icon,
                opacity: 1,
                type: 'success'
              })
              storage_pools_table.ajax.reload();
            },
            error: function (xhr, ajaxOptions, thrownError) {
              new PNotify({
                title: "ERROR deleting pool",
                text: xhr.responseJSON.description,
                hide: true,
                delay: 3000,
                icon: 'fa fa-warning',
                opacity: 1,
                type: 'error'
              });
            }
          });
        }).on("pnotify.cancel", function () {});
        break;
    }
  });
  $.getScript("/isard-admin/static/admin/js/socketio.js");
})

function renderEnabled(enabled, kind) {
  let icon = kind == 'check' ? 'check' : 'circle'
  let color = enabled ? 'green' : 'darkgray'
  return '<i class="fa fa-' + icon + '" style="color:' + color + '"></i>'
}

function renderStoragePoolsPaths(data) {
  var $newPanel = "";
  $.each(data["categories_names"], function (index, category) {
    $panel = $(".template-storage_pools-detail").clone();
    $panel.find(".x_title h3").text(category["name"]+" paths");
    $pathsTBody = $panel.find("tbody");
    $pathsTBody.empty();
    $.each(data.paths, function (type, paths) {
      if (type == "desktop") {
        icon = "fa fa-desktop fa-1x"
        typeName = "<b>Desktops</b>"
      } else if (type == "media") {
        icon = "fa fa-circle-o fa-1x"
        typeName = "<b>Media</b>"
      } else if (type == "template") {
        icon = "fa fa-cubes fa-1x"
        typeName = "<b>Templates</b>"
      } else if (type == "volatile") {
        icon = "fa fa-laptop fa-1x"
        typeName = "<b>Volatile</b>"
      }
      $.each(paths, function (index, path) {
        $pathsTBody.append(
          $('<tr>').append(
            $('<td>').append($('<i>').addClass(icon)).append(' ').append(typeName),
            $('<td>').text(`${data.mountpoint}/${category["id"]}/${path.path}`),
            $('<td>').text(path.weight)
          )
        );
      });
    });
    $newPanel.length ? $newPanel.find(".category-panel-container").append($panel.find(".detail-col")) : $newPanel = $panel;
  });
  // $newPanel.html(function(i, oldHtml){
  //   return oldHtml.replace(/d.id/g, data.id).replace(/d.name/g, data.name).replace(/d.description/g, data.description);
  // });
  return $newPanel;
}

function addRow(type, modal) {
  var currentRow = ""
  if (modal == "modalAdd") {
    currentRow = document.getElementById(`modalAdd-addrow-${type}`).parentNode.parentNode;
  } else if (modal == "modalEdit") {
    currentRow = document.getElementById(`modalEdit-addrow-${type}`).parentNode.parentNode;
  }
  var newRow = currentRow.cloneNode(true);
  currentRow.parentNode.insertBefore(newRow, currentRow.nextSibling);
}

function delRow(type, modal) {
  var currentRow = ""
  if (modal == "modalAdd") {
    currentRow = document.getElementById(`modalAdd-delrow-${type}`).parentNode.parentNode;
  } else if (modal == "modalEdit") {
    currentRow = document.getElementById(`modalEdit-delrow-${type}`).parentNode.parentNode;
  }
  currentRow.remove();
}

$("#modalAddStoragePool #send").off('click').on('click', function (e) {
  var form = $('#modalAdd');
  form.parsley().validate();
  if (form.parsley().isValid()) {
    data = form.serializeObject();
    // data['startable'] = 'startable' in data ? true : false;
    // data['read'] = 'read' in data ? true : false;
    // data['write'] = 'write' in data ? true : false;
    data["allowed"] = {"roles": false, "categories": false, "groups": false, "users": false}

    e.preventDefault();
    var pathsTableAdd = {};
    $('#pathsTableAdd tbody tr').each(function() {
      var type = $(this).attr("id");
      var weight = parseInt($(this).find('#weight').val());
      var path = $(this).find('#path').val();
      if (!pathsTableAdd[type]) {
        pathsTableAdd[type] = [];
      }
      pathsTableAdd[type].push({
        'path': path,
        'weight': weight
      });
    });

    for (let key in data) {
      if (key.endsWith("-weight") || key.endsWith("-path")) {
        delete data[key];
      }
    }

    data["paths"] = pathsTableAdd
    data["mountpoint"] = form.find(".path_base_mountpoint").text() + data.mountpoint

    var notice = new PNotify({
      text: 'Creating pool...',
      hide: false,
      opacity: 1,
      icon: 'fa fa-spinner fa-pulse'
    })

    $.ajax({
      url: "/admin/storage_pool",
      type: "POST",
      data: JSON.stringify(data),
      contentType: "application/json",
      success: function (data) {
        notice.update({
          title: 'Created',
          text: 'Pool created successfully',
          hide: true,
          delay: 1000,
          icon: 'fa fa-' + data.icon,
          opacity: 1,
          type: 'success'
        })
        $('form').each(function () { this.reset() });
        $('.modal').modal('hide');
        storage_pools_table.ajax.reload();
      },
      error: function (xhr) {
        notice.update({
          title: 'ERROR creating pool',
          text: xhr.responseJSON.description,
          type: 'error',
          hide: true,
          icon: 'fa fa-warning',
          delay: 2000,
          opacity: 1
        })
      }
    });
  }
});

$("#modalEditStoragePool #send").off('click').on('click', function (e) {
  var form = $('#modalEdit');
  form.parsley().validate();
  if (form.parsley().isValid()) {
    data = form.serializeObject();
    data['startable'] = 'startable' in data ? true : false;
    data['read'] = 'read' in data ? true : false;
    data['write'] = 'write' in data ? true : false;

    e.preventDefault();
    var pathsTableEdit = {};
    $('#pathsTableEdit tbody tr').each(function() {
      if($(this).attr("id") != undefined){
        var type = $(this).attr("id");
        var weight = parseInt($(this).find('#weight').val());
        var path = $(this).find('#path').val();
        if (!pathsTableEdit[type]) {
          pathsTableEdit[type] = [];
        }
        pathsTableEdit[type].push({
          'path': path,
          'weight': weight
        });
      }
    });

    for (let key in data) {
      if (key.endsWith("-weight") || key.endsWith("-path")) {
        delete data[key];
      }
    }

    data["paths"] = pathsTableEdit
    data["mountpoint"] = form.find(".path_base_mountpoint").text() + data.mountpoint;

    if (data.id == "00000000-0000-0000-0000-000000000000") {
      new PNotify({
        title: "WARNING. You're about to edit the default pool",
        type: "warning",
        text: "Editing the default pool settings may impact system operations. Are you sure you want to update?",
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
      }).get().on('pnotify.confirm', function () {
        updateStoragePool(data);
      });
    } else {
      updateStoragePool(data);
    }

  }
});

function populateCategory(modal, category_id) {
  $(modal + " #category").empty();
  $.ajax({
    type: "GET",
    url: "/api/v3/admin/categories",
    cache: false,
    success: function (category) {
      $.each(category, function (key, value) {
        $(modal + ' #category').append(
          `<option value="${value.id}">${value.name}</option>`
        );
        $(modal + " #category").val(category_id).trigger("change");
      });
    }
  });
}

function updateStoragePool(data) {
  var notice = new PNotify({
    text: 'Updating pool...',
    hide: false,
    opacity: 1,
    icon: 'fa fa-spinner fa-pulse'
  })
  $.ajax({
    url: "/admin/storage_pool/" + data["id"],
    type: "PUT",
    data: JSON.stringify(data),
    contentType: "application/json",
    success: function (data) {
      notice.update({
        title: 'Updated',
        text: 'Pool updated successfully',
        hide: true,
        delay: 1000,
        icon: 'fa fa-' + data.icon,
        opacity: 1,
        type: 'success'
      })
      $('form').each(function () { this.reset() });
      $('.modal').modal('hide');
      storage_pools_table.ajax.reload();
    },
    error: function (xhr) {
      notice.update({
        title: 'ERROR updating pool',
        text: xhr.responseJSON.description,
        type: 'error',
        hide: true,
        icon: 'fa fa-warning',
        delay: 2000,
        opacity: 1
      })
    }
  });
}

function addPath(path, mountpoint) {
  $(path).empty();
  $.each($(path), function () {
    $(this).text(`/isard/storage_pools/${mountpoint ?  mountpoint : ""}`);
  });
}