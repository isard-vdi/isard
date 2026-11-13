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
        switch ($(this).attr('id')) {
            case 'btn-edit':
                notImplemented('Editing frontend mode rules');
                break;
            case 'btn-alloweds':
                notImplemented('Editing the allowed users of frontend mode rules');
                break;
            case 'btn-delete':
                notImplemented('Deleting frontend mode rules');
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