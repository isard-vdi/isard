/*
*   Copyright © 2026 Adrià Garriga Bassas
*
*   This file is part of IsardVDI.
*
*   IsardVDI is free software: you can redistribute it and/or modify
*   it under the terms of the GNU Affero General Public License as published by
*   the Free Software Foundation, either version 3 of the License, or (at your
*   option) any later version.
*
*   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
*   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
*   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
*   details.
*
*   You should have received a copy of the GNU Affero General Public License
*   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
*
* SPDX-License-Identifier: AGPL-3.0-or-later
*/

$(document).ready(function () {
    renderFrontendModeRulesDatatable();

    $('#frontend-mode-rules-table').find('tbody').on('click', 'button', function () {
        const rule = $('#frontend-mode-rules-table').DataTable().row($(this).parents('tr')).data();
        switch ($(this).attr('id')) {
            case 'btn-edit':
                notImplemented('Editing frontend mode rules');
                break;
            case 'btn-alloweds':
                notImplemented('Editing the allowed users of frontend mode rules');
                break;
            case 'btn-delete':
                confirmDeleteFrontendModeRule(rule);
                break;
        }
    });

    $('.btn-add-frontend-mode-rule').on('click', function () {
        notImplemented('Adding frontend mode rules');
    });
});

function notImplemented(action) {
    new PNotify({
        title: 'Not implemented yet',
        text: `${action} is not implemented yet`,
        type: 'info',
        hide: true,
        delay: 4000,
        opacity: 1
    });
}

function confirmDeleteFrontendModeRule(rule) {
    const name = $('<div>').text(rule.name).html();
    new PNotify({
        title: 'Confirmation Needed',
        text: `Are you sure you want to delete rule "${name}"?<br><br>` +
            'Its users will get the next rule that matches them or, if none does, the global frontend mode.',
        type: 'error',
        hide: false, opacity: 1, confirm: { confirm: true },
        buttons: { closer: false, sticker: false },
        addclass: 'pnotify-center'
    }).get().on('pnotify.confirm', function () {
        $.ajax({
            type: 'DELETE',
            url: `/api/v4/item/frontend-mode-rule/${rule.id}`,
            success: function () {
                new PNotify({
                    title: 'Deleted',
                    text: `Rule "${name}" deleted successfully`,
                    hide: true,
                    delay: 2000,
                    opacity: 1,
                    type: 'success'
                });
                $('#frontend-mode-rules-table').DataTable().ajax.reload();
            },
            error: function (xhr) {
                new PNotify({
                    title: `ERROR deleting "${name}"`,
                    text: xhr.responseJSON ? xhr.responseJSON.description : 'Something went wrong',
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 5000,
                    opacity: 1
                });
            }
        });
    }).on('pnotify.cancel', function () { });
}

function renderFrontendModeRulesDatatable() {
    $('#frontend-mode-rules-table').DataTable({
        "ajax": {
            url: '/api/v4/items/frontend-mode-rules',
            type: 'GET'
        },
        "sAjaxDataProp": "rules",
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "rowId": "id",
        "searching": true,
        "footer": true,
        "order": [[3, "desc"]],
        "deferRender": true,
        "columns": [
            { data: 'name', title: 'Name', render: $.fn.dataTable.render.text() },
            { data: 'description', title: 'Description', render: $.fn.dataTable.render.text() },
            { 
                data: 'frontend_mode', 
                title: 'Frontend Mode',
                render: function (data) {
                    const descriptions = {
                        deprecated: 'Only the old frontend is allowed',
                        actual: 'Only the new frontend is allowed',
                        all: 'Both frontends are allowed, with a switch in the UI',
                        hidden: 'Both frontends are allowed, without the UI switch'
                    };
                    return `<span class="label label-default" title="${descriptions[data] || ''}">${data}</span>`;
                }
            },
            { data: 'priority', title: 'Priority' },
            {
                data: null,
                title: 'Action',
                render: function (data) {
                    return `
                        <button title="Edit rule" class="btn btn-xs btn-info" id="btn-edit" data-id="${data.id}"><i class="fa fa-pencil"></i></button>
                        <button title="Allowed users" class="btn btn-xs btn-primary" id="btn-alloweds" data-id="${data.id}"><i class="fa fa-users"></i></button>
                        <button title="Delete rule" class="btn btn-xs btn-danger" id="btn-delete" data-id="${data.id}"><i class="fa fa-trash"></i></button>
                    `;
                }
            }
        ]
    })
}