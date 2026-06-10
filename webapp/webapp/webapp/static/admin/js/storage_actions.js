//   Copyright © 2017-2026 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases, Miriam Melina Gamboa Valdez
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

// Generic helpers shared by every storage action (increase, create,
// sparsify, convert, …). Kept free of DOM init so they can be loaded
// from any admin page that needs to invoke a storage operation.

// Render a byte count in human units (B / KiB / MiB / GiB) so sub-GiB
// disks (a 20 MiB load-test fixture, a 512 B empty disk) don't collapse
// to "0.00 GB" and read as "0".
function humanizeBytes(bytes) {
  if (bytes === undefined || bytes === null) return '-';
  bytes = Number(bytes);
  if (!isFinite(bytes) || bytes < 0) return '-';
  if (bytes === 0) return '0 B';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KiB';
  if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(2) + ' MiB';
  return (bytes / 1024 / 1024 / 1024).toFixed(2) + ' GiB';
}

function stopAllDesktops(storageId) {
  $.ajax({
    type: "PUT",
    url: `/api/v4/item/storage/${storageId}/stop`
  }).done(function (data) {
    new PNotify({
      title: 'Stopping desktops...',
      hide: true,
      delay: 2000,
      icon: 'fa fa-' + data?.icon,
      opacity: 1,
      type: 'success'
    });
  }).fail(function (data) {
    new PNotify({
      title: 'ERROR stopping desktops',
      text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
      type: 'error',
      hide: true,
      icon: 'fa fa-warning',
      delay: 5000,
      opacity: 1
    });
  });
}

function scheduleUntilDesktopsAreStopped(storageId, action, kwargs) {
  data = {}
  data["kwargs"] = {
    storage_id: storageId,
    action: action,
    ...kwargs
  };
  $.ajax({
    url: "/scheduler/system/interval/wait_desktops_to_do_storage_action/00/05/" + storageId + ".stg_action",
    type: "POST",
    data: JSON.stringify(data),
    contentType: "application/json",
  }).done(function () {
    new PNotify({
      title: 'Success',
      text: ' Storages ' + action + ' scheduled successfully',
      hide: true,
      delay: 2000,
      icon: 'fa fa-' + data?.icon,
      opacity: 1,
      type: 'success'
    });
    $('.modal').modal('hide');
  }).fail(function (data) {
    new PNotify({
      title: 'ERROR scheduling the action ' + action,
      text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
      type: 'error',
      hide: true,
      icon: 'fa fa-warning',
      delay: 5000,
      opacity: 1
    });
  });
}

function performStorageOperation(formData, storageId, action, url) {
  $.ajax({
    url: url,
    type: action === "create" ? 'POST' : 'PUT',
    data: JSON.stringify(formData),
    contentType: 'application/json'
  }).done(function () {
    new PNotify({
      title: 'Task created successfully',
      text: `Performing ${action} on storage...`,
      hide: true,
      delay: 2000,
      opacity: 1,
      type: 'success'
    });
    $('.modal').modal('hide');
  }).fail(function (data) {
    if (data.responseJSON && data.responseJSON.description_code === "desktops_not_stopped" && $("#user_data").data("role") == "admin") {
      new PNotify({
        title: "All desktops must be 'Stopped' for storage operations",
        text: "You can force stop now all desktops associated with the storage" + ($("#user_data").data("role") == "admin" ? " or schedule the action when desktops are stopped" : ""),
        hide: false,
        opacity: 0.9,
        type: "error",
        confirm: {
          confirm: true,
          buttons: [
            {
              text: "Force Stop desktops", click: function (notice) {
                stopAllDesktops(storageId);
                scheduleUntilDesktopsAreStopped(storageId, action, formData)
                notice.remove();
              }
            },
            {
              text: "Schedule", click: function (notice) {
                scheduleUntilDesktopsAreStopped(storageId, action, formData);
                notice.remove();
              }
            },
            { text: "Cancel", click: function (notice) { notice.remove(); } }
          ]
        },
        buttons: { closer: false, sticker: false },
        history: { history: false },
        addclass: 'pnotify-center-large',
        width: '550'
      });
    } else {
      new PNotify({
        title: `ERROR trying to ${action} storage`,
        text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
        type: 'error',
        hide: true,
        icon: 'fa fa-warning',
        delay: 5000,
        opacity: 1
      });
    }
  });
}
