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

const FRONTEND_MODE_DESCRIPTIONS = {
    deprecated: 'Only the old frontend is allowed',
    actual: 'Only the new frontend is allowed',
    all: 'Both frontends are allowed, with a switch in the UI',
    hidden: 'Both frontends are allowed, without the UI switch'
};

const FRONTEND_MODE_RULE_MODAL = '#modalFrontendModeRule';
const FRONTEND_MODE_RULE_ALLOWEDS = `${FRONTEND_MODE_RULE_MODAL} #alloweds-frontend-mode-rule`;

$(document).ready(function () {
    renderFrontendModeRulesDatatable();

    window.Parsley.addValidator('uniquePriority', {
        validateString: function (value) {
            const priority = parseInt(value, 10);
            return !$('#frontend-mode-rules-table').DataTable().rows().data().toArray()
                .some(rule => rule.priority === priority);
        },
        messages: {
            en: 'Another rule already has this priority.'
        }
    });

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
        showAddFrontendModeRuleModal();
    });

    $(`${FRONTEND_MODE_RULE_MODAL} #priority`).on('input', function () {
        $(this).parsley().removeError('duplicatedPriority');
    });

    $(`${FRONTEND_MODE_RULE_MODAL} #send`).on('click', function () {
        const form = $(`${FRONTEND_MODE_RULE_MODAL}Form`);
        form.find('#priority').parsley().removeError('duplicatedPriority');
        form.parsley().validate();
        if (!form.parsley().isValid()) {
            return;
        }

        let data = form.serializeObject();
        data = replaceAlloweds_arrays(FRONTEND_MODE_RULE_ALLOWEDS, data);
        data.priority = parseInt(data.priority, 10);

        $.ajax({
            type: 'POST',
            url: '/api/v4/item/frontend-mode-rule',
            data: JSON.stringify(data),
            contentType: 'application/json',
            success: function () {
                $(FRONTEND_MODE_RULE_MODAL).modal('hide');
                new PNotify({
                    title: 'Added',
                    text: 'Rule added successfully',
                    hide: true,
                    delay: 2000,
                    opacity: 1,
                    type: 'success'
                });
                $('#frontend-mode-rules-table').DataTable().ajax.reload();
            },
            error: function (xhr) {
                const error = xhr.responseJSON;
                if (xhr.status === 409 && error && error.description_code === 'duplicated_priority') {
                    form.find('#priority').parsley().addError('duplicatedPriority', {
                        message: 'Another rule already has this priority.'
                    });
                    return;
                }
                new PNotify({
                    title: 'ERROR adding rule',
                    text: error ? error.description : 'Something went wrong',
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 5000,
                    opacity: 1
                });
            }
        });
    });
});

function showAddFrontendModeRuleModal() {
    const form = $(`${FRONTEND_MODE_RULE_MODAL}Form`);
    form[0].reset();
    form.parsley().reset();

    form.find('#frontend_mode').empty().append(
        new Option('Choose...', ''),
        Object.entries(FRONTEND_MODE_DESCRIPTIONS).map(([mode, description]) =>
            new Option(`${mode}: ${description}`, mode))
    );

    setAlloweds_add(FRONTEND_MODE_RULE_ALLOWEDS);
    $(`${FRONTEND_MODE_RULE_ALLOWEDS} #allowed-title h4`)
        .html('Applies to <small>Users matching any of the checked fields</small>');
    $(`${FRONTEND_MODE_RULE_ALLOWEDS} #alloweds_panel`).show();

    $(FRONTEND_MODE_RULE_MODAL).modal({ backdrop: 'static', keyboard: false }).modal('show');
}

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
                    return `<span class="label label-default" title="${FRONTEND_MODE_DESCRIPTIONS[data] || ''}">${data}</span>`;
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