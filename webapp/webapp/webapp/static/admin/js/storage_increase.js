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

// Handlers for the #modalIncreaseStorage modal. Depends on the helpers
// from storage_actions.js — load that file first.

// Bootstrap 3 can't stack modals (second one renders behind the first
// backdrop). When opened from inside another modal — e.g. the Desktop
// Storage list — close the parent first and wait for the transition.
function showIncreaseModalOnTop() {
  var $other = $('.modal.in').not('#modalIncreaseStorage');
  var show = function () {
    $('#modalIncreaseStorage').modal({ backdrop: 'static', keyboard: false }).modal('show');
  };
  if ($other.length) {
    $other.one('hidden.bs.modal', show).modal('hide');
  } else {
    show();
  }
}

$(document).on('click', '.btn-increase', function () {
  element = $(this);
  var storageId = element.data("id");
  modal = "#modalIncreaseStorage";
  $(modal + " input").empty();
  $(modal + " #id").val(storageId);
  $(modal + " select#priority").empty();

  if ($("#user_data").data("role") == "admin") {
    $(modal + " select#priority").append(`
      <option selected value="low">Low</option>
      <option value="default">Default</option>
      <option value="high">High</option>
    `);
  } else {
    $(modal + " select#priority").append(`
    <option selected disabled value="low">Low</option>
    `);
    $(modal + " .different_pool").hide();
  }

  $.ajax({
    url: `/api/v4/admin/item/storage/info/${storageId}`,
    type: 'GET',
    contentType: "application/json",
  }).done(function (storage) {
    $.ajax({
      url: `/api/v4/item/storage/${storageId}/has-derivatives`,
    }).done(function (data) {
      if (data.derivatives <= 1) {
        var virtual_size = storage.virtual_size / 1024 / 1024 / 1024
        $(modal + " #current-size").text(virtual_size.toFixed(0) + " GB");
        $(modal + " #current_size").val(virtual_size);
        $(modal + " #new-size").val(virtual_size.toFixed(0)).prop("min", (virtual_size + 1).toFixed(0));

        $.ajax({
          url: "/api/v4/admin/item/user/appliedquota/" + storage["user_id"],
          type: 'GET',
        }).done(function (quota) {
          if (quota.quota) {
            $(modal + " #max-quota-div").show();
            $(modal + " #max-quota").text(quota.quota.desktops_disk_size);
            $(modal + " #new-size").prop("max", quota.quota.desktops_disk_size);
          } else {
            $(modal + " #max-quota-div").hide();
            $(modal + " #new-size").removeAttr("max");
          }


          showIncreaseModalOnTop();
        }).fail(function (data) {
          new PNotify({
            title: `ERROR trying to fetch storage size`,
            text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
            type: 'error',
            hide: true,
            icon: 'fa fa-warning',
            delay: 5000,
            opacity: 1
          });
        });
      } else {
        new PNotify({
          title: `ERROR`,
          text: 'Size of disks with derivatives cannot be modified',
          type: 'error',
          hide: true,
          icon: 'fa fa-warning',
          delay: 5000,
          opacity: 1
        });
      }
    }).fail(function (data) {
      new PNotify({
        title: `ERROR`,
        text: 'Something went wrong',
        type: 'error',
        hide: true,
        icon: 'fa fa-warning',
        delay: 5000,
        opacity: 1
      });
    });

  }).fail(function (data) {
    new PNotify({
      title: `ERROR`,
      text: 'Something went wrong',
      type: 'error',
      hide: true,
      icon: 'fa fa-warning',
      delay: 5000,
      opacity: 1
    });
  });
});

$(document).on("click", "#modalIncreaseStorage #send", function () {
  var form = $('#modalIncreaseStorageForm');
  form.parsley().validate();
  if (form.parsley().isValid()) {
    formData = form.serializeObject();
    var priority = formData.priority ? formData.priority : "low";
    formData.increment = (formData.new_size - formData.current_size).toFixed(0);
    delete formData.new_size;
    var url = `/api/v4/item/storage/${formData.storage_id}/priority/${priority}/increase/${formData.increment}`;
    performStorageOperation(formData, formData.storage_id, "increase", url);
  }
});
