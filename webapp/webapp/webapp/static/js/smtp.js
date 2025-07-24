/*
*
*    Copyright © 2025 Simó Albert i Beltran
*
*    This file is part of IsardVDI.
*
*    IsardVDI is free software: you can redistribute it and/or modify
*    it under the terms of the GNU Affero General Public License as published by
*    the Free Software Foundation, either version 3 of the License, or (at your
*    option) any later version.
*
*    IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
*    WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
*    FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
*    details.
*
*    You should have received a copy of the GNU Affero General Public License
*    along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
*
*  SPDX-License-Identifier: AGPL-3.0-or-later
*/

function fillSMTPForms() {
    $.ajax({
        url: "/api/v3/smtp",
    }).done((data) => {
        $.each(data, (key, value) => {
            element = $(`.form-smtp [name="${key}"]`)
            if (element.prop('type') == 'checkbox') {
                if(value) {
                    element.iCheck('check').iCheck('update')
                } else {
                    element.iCheck('uncheck').iCheck('update')
                }
            } else {
                element.val(value)
            }
        })
        $(".form-smtp").each((index, form) => { $(form).parsley().validate() })
    })
}

function getDataSMTPForm() {
    const form = $('#form-smtp-edit')
    return form.parsley().whenValidate().then(() => {
        data=form.serializeObject()
        data.port = parseInt(data.port)
        if (data.enabled == "on") {
          data.enabled = true
        } else {
          data.enabled = false
        }
        return JSON.stringify(data)
    })
}


$(document).ready(() => {
    fillSMTPForms()
    $("#btn-edit-smtp").on("click", () => {
        fillSMTPForms()
        $("#modal-smtp-configuration").modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show')
    })
    $("#smtp-save").on('click', () => {
        getDataSMTPForm().then((data) => {
            const notice = new PNotify({
                title: 'SMTP Configuration',
                text: 'Sending SMTP configuration...',
                icon: 'fa fa-spinner fa-pulse'
            })
            $.ajax({
                type: "PUT",
                url:"/api/v3/smtp" ,
                data: data,
                contentType: "application/json"
            }).fail((data) => {
                notice.update({
                    title: "ERROR storing SMTP configuration",
                    text: data.responseJSON.description,
                    type: 'error',
                    icon: 'fa fa-warning',
                    delay: 15000,
                })
            }).done((data) => {
                $('.modal').modal('hide');
                notice.update({
                    text: 'SMTP configured successfully',
                    icon: 'fa fa-envelope',
                    type: 'success',
                    delay: 2000
                })
                fillSMTPForms()
            })
        })
    })
})
