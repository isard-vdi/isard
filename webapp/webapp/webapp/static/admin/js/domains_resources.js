/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

// VPN
$(document).ready(function () {
    remotevpn_table = $('#table-remotevpn').DataTable({
        "ajax": {
            "url": "/admin/table/remotevpn",
            "contentType": "application/json",
            "type": 'POST',
            "data": function (d) { return JSON.stringify({ 'order_by': 'name' }) }
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
                "defaultContent": '' //'<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
            },
            { "data": "name" },
            { "data": "description" },
            { "data": null },
            { "data": null },
            { "data": "vpn.wireguard.connected", "width": "10px", "defaultContent": 'NaN' },
            {
                "className": 'actions-control',
                "orderable": false,
                "data": null,
                "width": "290px",
                "defaultContent": '<button id="btn-alloweds" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-users" style="color:darkblue"></i></button> \
                                <button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button> \
                                <button id="btn-download" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-download" style="color:darkgreen"></i></button>'
                //<button id="btn-edit" class="btn btn-xs btn-edit-interface" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>'
            },
        ],
        "order": [[1, 'asc']],
        "columnDefs": [{
            "targets": 3,
            "render": function (data, type, full, meta) {
                if ('vpn' in data) {
                    return data['vpn']['wireguard']['Address']
                } else {
                    return '-'
                }
            }
        },
        {
            "targets": 4,
            "render": function (data, type, full, meta) {
                if ('vpn' in data) {
                    return data['vpn']['wireguard']['extra_client_nets']
                } else {
                    return '-'
                }
            }
        },
        {
            "targets": 5,
            "render": function (data, type, full, meta) {
                if ('vpn' in full && full['vpn']['wireguard']['connected']) {
                    return '<i class="fa fa-circle" aria-hidden="true"  style="color:green" title="' + full["vpn"]["wireguard"]["remote_ip"] + ':' + full["vpn"]["wireguard"]["remote_port"] + '"></i>'
                } else {
                    return '<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>'
                }
            }
        },
        ]
    });

    $('#table-remotevpn').find(' tbody').on('click', 'button', function () {
        var data = remotevpn_table.row($(this).parents('tr')).data();
        switch ($(this).attr('id')) {
            case 'btn-alloweds':
                modalAllowedsFormShow('remotevpn', data)
                break;
            case 'btn-edit':
                $("#modalRemotevpnForm")[0].reset();
                $('#modalRemotevpn').modal({
                    backdrop: 'static',
                    keyboard: false
                }).modal('show');
                $('#modalRemotevpn #modalRemotevpnForm').parsley();
                $.ajax({
                    type: "POST",
                    url: "/api/v3/admin/table/remotevpn",
                    data: JSON.stringify({ 'id': data.id }),
                    contentType: "application/json",
                    accept: "application/json",
                    success: function (remotevpn) {
                        $('#modalRemotevpnForm #name').val(remotevpn.name).attr("disabled", true);
                        $('#modalRemotevpnForm #id').val(remotevpn.id);
                        $('#modalRemotevpnForm #description').val(remotevpn.description);
                        $.each(remotevpn, function (key, value) {
                            $('#modalRemotevpnForm #' + key).val(value)
                        });
                    }
                });
                break;
            case 'btn-delete':
                new PNotify({
                    title: 'Confirmation Needed',
                    text: "Are you sure you want to delete client VPN: " + data['name'] + "?",
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
                    addclass: 'pnotify-center'
                }).get().on('pnotify.confirm', function () {
                    data['table'] = 'remotevpn'
                    $.ajax({
                        type: "DELETE",
                        url: "/admin/table/remotevpn/" + data["id"],
                        data: JSON.stringify(data),
                        contentType: "application/json",
                        success: function (data) {
                            $('form').each(function () { this.reset() });
                            $('.modal').modal('hide');
                        }
                    });
                }).on('pnotify.cancel', function () {
                });
                break;
            case 'btn-download':
                $.ajax({
                    type: "GET",
                    url: "/api/v3/remote_vpn/" + data['id'] + "/config/" + getOS(),
                    success: function (data) {
                        var el = document.createElement('a')
                        var content = data.content
                        el.setAttribute(
                            'href',
                            `data:${data.mime};charset=utf-8,${encodeURIComponent(content)}`
                        )
                        el.setAttribute('download', `${data.name}.${data.ext}`)
                        el.style.display = 'none'
                        document.body.appendChild(el)
                        el.click()
                        document.body.removeChild(el)
                    }
                })
                break;
        }
    });

    $('.add-new-remotevpn').on('click', function () {
        $('#modalRemotevpnForm #name').attr("disabled", false);
        $("#modalRemotevpnForm")[0].reset();
        $('#modalRemotevpn').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        $('#modalRemotevpn #modalRemotevpnForm').parsley();
    });

    $("#modalRemotevpn #send").on('click', function (e) {
        var form = $('#modalRemotevpnForm');
        data = form.serializeObject()
        form.parsley().validate();
        if (form.parsley().isValid()) {
            var action = ''
            if (data['id'] == "") {
                //Insert
                data['id'] = data['name'];
                data['allowed'] = { 'roles': false, 'categories': false, 'groups': false, 'users': false }
                action = 'Creating'
            } else {
                //Update
                data['name'] = $('#modalRemotevpnForm #name').val();
                action = 'Updating'
            }
            data['table'] = 'remotevpn'
            delete data['id']
            var notice = new PNotify({
                text: action + ' remote VPN...',
                hide: false,
                opacity: 1,
                icon: 'fa fa-spinner fa-pulse'
            })
            $.ajax({
                type: "POST",
                url: "/admin/table/add/remotevpn",
                data: JSON.stringify(data),
                contentType: "application/json",
                success: function (data) {
                    notice.update({
                        title: 'Created',
                        text: 'Remote VPN created successfully',
                        hide: true,
                        delay: 1000,
                        icon: 'fa fa-' + data.icon,
                        opacity: 1,
                        type: 'success'
                    })
                    $('form').each(function () { this.reset() });
                    $('.modal').modal('hide');
                },
                error: function (data) {
                    notice.update({
                        title: 'ERROR creating remote VPN',
                        text: data.responseJSON.description,
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

    // QOS NET
    qosnet_table = $('#table-qos-net').DataTable({
        "ajax": {
            "url": "/admin/table/qos_net",
            "contentType": "application/json",
            "type": 'POST',
            "data": function (d) { return JSON.stringify({ 'order_by': 'name' }) }
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
                "defaultContent": '' //'<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
            },
            { "data": "name" },
            { "data": "description" },
            {
                "className": 'actions-control',
                "orderable": false,
                "data": null,
                "defaultContent": '<button id="btn-alloweds" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-users" style="color:darkblue"></i></button> \
                                    <button id="btn-edit" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>'
                //~ <button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'

            },
        ],
        "order": [[1, 'asc']]
    });

    $('#table-qos-net').find(' tbody').on('click', 'button', function () {
        var data = qosnet_table.row($(this).parents('tr')).data();
        switch ($(this).attr('id')) {
            case 'btn-alloweds':
                modalAllowedsFormShow('qos_net', data)
                break;
            case 'btn-edit':
                $("#modalQosNetForm")[0].reset();
                $('#modalQosNet').modal({
                    backdrop: 'static',
                    keyboard: false
                }).modal('show');
                $('#modalQosNet #modalQosNetForm').parsley();
                $.ajax({
                    type: "POST",
                    url: "/api/v3/admin/table/qos_net",
                    data: JSON.stringify({ 'id': data.id }),
                    contentType: "application/json",
                    accept: "application/json",
                    success: function (qos) {
                        $('#modalQosNetForm #name').val(qos.name).attr("disabled", true);
                        $('#modalQosNetForm #id').val(qos.id);
                        $('#modalQosNetForm #description').val(qos.description);
                        qos['bandwidth']['inbound'] = removeQosAd(data.bandwidth.inbound)
                        qos['bandwidth']['outbound'] = removeQosAd(data.bandwidth.outbound)
                        $.each(qos.bandwidth.inbound, function (key, value) {
                            $('#modalQosNetForm #qos-bandwidth-inbound-' + key).val(value)
                        });
                        $.each(qos.bandwidth.outbound, function (key, value) {
                            $('#modalQosNetForm #qos-bandwidth-outbound-' + key).val(value)
                        });
                    }
                });
                break;
        }
    });

    $('.add-new-qos-net').on('click', function () {
        $('#modalQosNetForm #name').attr("disabled", false);
        $("#modalQosNetForm")[0].reset();
        $('#modalQosNet').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        $('#modalQosNet #modalQosNetForm').parsley();

    });

    $("#modalQosNet #send").on('click', function (e) {
        var form = $('#modalQosNetForm');
        data = form.serializeObject()
        form.parsley().validate();
        if (form.parsley().isValid()) {

            data = QosNetParse(data)
            if (data['id'] == "") {
                //Insert
                data['id'] = data['name'];
                data['allowed'] = { 'roles': false, 'categories': false, 'groups': false, 'users': false }
                delete data['id']
                var notice = new PNotify({
                    text: 'Creating network QoS...',
                    hide: false,
                    opacity: 1,
                    icon: 'fa fa-spinner fa-pulse'
                })
                $.ajax({
                    type: "POST",
                    url: "/admin/table/add/qos_net",
                    data: JSON.stringify(data),
                    contentType: "application/json",
                    success: function (data) {
                        notice.update({
                            title: 'Created',
                            text: 'Network Qos created successfully',
                            hide: true,
                            delay: 1000,
                            icon: 'fa fa-' + data.icon,
                            opacity: 1,
                            type: 'success'
                        })
                        $('form').each(function () { this.reset() });
                        $('.modal').modal('hide');
                    },
                    error: function (data) {
                        notice.update({
                            title: 'ERROR creating network QoS',
                            text: data.responseJSON.description,
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 2000,
                            opacity: 1
                        })
                    }
                });
            } else {
                var notice = new PNotify({
                    text: 'Updating network QoS...',
                    hide: false,
                    opacity: 1,
                    icon: 'fa fa-spinner fa-pulse'
                })
                //Update
                data['name'] = $('#modalQosNetForm #name').val();
                $.ajax({
                    type: "PUT",
                    url: "/admin/table/update/qos_net",
                    data: JSON.stringify(data),
                    contentType: "application/json",
                    success: function (data) {
                        notice.update({
                            title: 'Updated',
                            text: 'Network Qos updated successfully',
                            hide: true,
                            delay: 1000,
                            icon: 'fa fa-' + data.icon,
                            opacity: 1,
                            type: 'success'
                        })
                        $('form').each(function () { this.reset() });
                        $('.modal').modal('hide');
                    },
                    error: function (data) {
                        notice.update({
                            title: 'ERROR updating network QoS',
                            text: data.responseJSON.description,
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 2000,
                            opacity: 1
                        })
                    }
                });
            }

        }
    });


    // QOS DISK
    qosdisk_table = $('#table-qos-disk').DataTable({
        "ajax": {
            "url": "/admin/table/qos_disk",
            "contentType": "application/json",
            "type": 'POST',
            "data": function (d) { return JSON.stringify({ 'order_by': 'name' }) }
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
                "defaultContent": '' //'<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
            },
            { "data": "name" },
            { "data": "description" },
            {
                "className": 'actions-control',
                "orderable": false,
                "data": null,
                "defaultContent": '<button id="btn-alloweds" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-users" style="color:darkblue"></i></button> \
                                    <button id="btn-edit" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>'
                //~ <button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'

            },
        ],
        "order": [[1, 'asc']]
    });

    $('#table-qos-disk').find(' tbody').on('click', 'button', function () {
        var data = qosdisk_table.row($(this).parents('tr')).data();
        switch ($(this).attr('id')) {
            case 'btn-alloweds':
                modalAllowedsFormShow('qos_disk', data)
                break;
            case 'btn-edit':
                $("#modalQosDiskForm")[0].reset();
                $('#modalQosDisk').modal({
                    backdrop: 'static',
                    keyboard: false
                }).modal('show');
                $('#modalQosDisk #modalQosDiskForm').parsley();
                $.ajax({
                    type: "POST",
                    url: "/api/v3/admin/table/qos_disk",
                    data: JSON.stringify({ 'id': data.id }),
                    contentType: "application/json",
                    accept: "application/json",
                    success: function (qos) {
                        $('#modalQosDiskForm #name').val(qos.name).attr("disabled", true);
                        $('#modalQosDiskForm #id').val(qos.id);
                        $('#modalQosDiskForm #description').val(qos.description);
                        $.each(qos.iotune, function (key, value) {
                            $('#modalQosDiskForm #iotune-' + key).val(value)
                        });
                    }
                });
                break;

        }
    });

    $('.add-new-qos-disk').on('click', function () {
        $('#modalQosDiskForm #name').attr("disabled", false);
        $("#modalQosDiskForm")[0].reset();
        $('#modalQosDisk').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        $('#modalQosDisk #modalQosDiskForm').parsley();
    })


    $("#modalQosDisk #send").on('click', function (e) {
        var form = $('#modalQosDiskForm');
        data = form.serializeObject()
        form.parsley().validate();
        if (form.parsley().isValid()) {
            data['allowed'] = { 'roles': false, 'categories': false, 'groups': false, 'users': false }
            data = QosDiskParse(data)
            if (data['id'] == "") {
                //Insert
                data['id'] = data['name'];
                data['allowed'] = { 'roles': false, 'categories': false, 'groups': false, 'users': false }
                delete data['id']
                var notice = new PNotify({
                    text: 'Creating disk QoS...',
                    hide: false,
                    opacity: 1,
                    icon: 'fa fa-spinner fa-pulse'
                })
                $.ajax({
                    type: "POST",
                    url: "/admin/table/add/qos_disk",
                    data: JSON.stringify(data),
                    contentType: "application/json",
                    success: function (data) {
                        notice.update({
                            title: 'Created',
                            text: 'Disk QoS created successfully',
                            hide: true,
                            delay: 1000,
                            icon: 'fa fa-' + data.icon,
                            opacity: 1,
                            type: 'success'
                        })
                        $('form').each(function () { this.reset() });
                        $('.modal').modal('hide');
                    },
                    error: function (data) {
                        notice.update({
                            title: 'ERROR creating disk QoS',
                            text: data.responseJSON.description,
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 2000,
                            opacity: 1
                        })
                    }
                });
            } else {
                //Update
                var notice = new PNotify({
                    text: 'Updating disk QoS...',
                    hide: false,
                    opacity: 1,
                    icon: 'fa fa-spinner fa-pulse'
                })
                data['name'] = $('#modalQosDiskForm #name').val();
                $.ajax({
                    type: "PUT",
                    url: "/admin/table/update/qos_disk",
                    data: JSON.stringify(data),
                    contentType: "application/json",
                    success: function (data) {
                        notice.update({
                            title: 'Updated',
                            text: 'Disk QoS updated successfully',
                            hide: true,
                            delay: 1000,
                            icon: 'fa fa-' + data.icon,
                            opacity: 1,
                            type: 'success'
                        })
                        $('form').each(function () { this.reset() });
                        $('.modal').modal('hide');
                    },
                    error: function (data) {
                        notice.update({
                            title: 'ERROR updating disk QoS',
                            text: data.responseJSON.description,
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 2000,
                            opacity: 1
                        })
                    }
                });
            }
        }
    });


    // INTERFACES

    window.ParsleyValidator.addValidator('vlanrange', (value) => {
        values = value.split('-')
        return values.length === 2 && values[0] <= values[1] && 1 <= values[0] && values[0] <= 4094 && 1 <= values[1] && values[1] <= 4094
    })

    $('#kind').on('change', function () {
        $('#ifname').removeAttr('min').removeAttr('max').removeAttr('data-parsley-vlanrange')
        if ($('#kind').val() == 'bridge') {
            $('#ifname_label').html('Input interface name')
            $('#ifname').attr('type', 'text')
        }
        if ($('#kind').val() == 'network') {
            $('#ifname_label').html('Input network name')
            $('#ifname').attr('type', 'text')
        }
        if ($('#kind').val() == 'ovs') {
            $('#ifname_label').html('Input vlan ID number')
            if ($('#modalInterfacesForm #id').val() !== "wireguard") {
                $('#ifname').attr('type', 'number').attr('min', 1).attr('max', '4094')
            }
        }
        if ($('#kind').val() == 'personal') {
            $('#ifname_label').html('Input vlan range (i.e. 2000-3000)')
            $('#ifname').attr('type', 'text').attr('data-parsley-vlanrange', 'true')
        }
    });
    int_table = $('#table-interfaces').DataTable({
        "ajax": {
            "url": "/admin/table/interfaces",
            "contentType": "application/json",
            "type": 'POST',
            "data": function (d) { return JSON.stringify({ 'order_by': 'name' }) }
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
                "defaultContent": '' //'<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
            },
            { "data": "name" },
            { "data": "description" },
            { "data": "net" },
            {
                "className": 'actions-control',
                "orderable": false,
                "data": null,
                "width": "91px",
                "defaultContent": '<button id="btn-alloweds" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-users" style="color:darkblue"></i></button> \
                                    <button id="btn-edit" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button> \
                                    <button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
            },
        ],
        "order": [[1, 'asc']],
    });

    $('#table-interfaces').find(' tbody').on('click', 'button', function () {
        var data = int_table.row($(this).parents('tr')).data();
        switch ($(this).attr('id')) {
            case 'btn-alloweds':
                modalAllowedsFormShow('interfaces', data)
                break;
            case 'btn-edit':
                $("#modalInterfacesForm")[0].reset();
                $('#modalInterfaces').modal({
                    backdrop: 'static',
                    keyboard: false
                }).modal('show');
                $('#modalInterfaces #modalInterfacesForm').parsley();
                $.ajax({
                    type: "POST",
                    url: "/api/v3/admin/table/interfaces",
                    data: JSON.stringify({ 'id': data.id }),
                    contentType: "application/json",
                    accept: "application/json",
                    success: function (interface) {
                        if (interface.id === "wireguard") {
                            $('#kind').attr('style', 'pointer-events: none;')
                            $('#ifname').prop('readonly', true)
                        } else {
                            $('#kind').removeAttr('style')
                            $('#ifname').prop('readonly', false)
                        }
                        if ('qos_id' in data) {
                            if (data['qos_id'] == false) {
                                qos_id = 'unlimited'
                            } else {
                                qos_id = data['qos_id']
                            }
                        } else { qos_id = 'unlimited' }
                        populateDropdown('qos_net', '#qos_id', qos_id, false)
                        $('#modalInterfacesForm #id').val(interface.id);
                        $('#modalInterfacesForm #description').val(interface.description);
                        $('#modalInterfacesForm #kind').val(interface.kind)
                        $('#modalInterfacesForm #kind').trigger('change')
                        $.each(interface, function (key, value) {
                            $('#modalInterfacesForm #' + key).val(value)
                        });
                    }
                });
                break;
            case 'btn-delete':
                new PNotify({
                    title: 'Confirmation Needed',
                    text: "Are you sure you want to delete: " + data.name + "? WARNING: ALL STARTED DESKTOPS WITH THIS INTERFACE WILL BE STOPPED before the interface will be removed from all depending desktops & templates.",
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
                    addclass: 'pnotify-center'
                }).get().on('pnotify.confirm', function () {
                    $.ajax({
                        type: "DELETE",
                        url: "/admin/table/interfaces/" + data["id"],
                        contentType: "application/json",
                        success: function (data) {
                            $('form').each(function () { this.reset() });
                            $('.modal').modal('hide');
                        }
                    });
                }).on('pnotify.cancel', function () {
                });
                break;
        }
    });

    $('.add-new-interface').on('click', function () {
        $('#modalInterfacesForm #name').attr("disabled", false);
        $("#modalInterfacesForm")[0].reset();
        $('#modalInterfaces').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        populateDropdown('qos_net', '#qos_id', 'unlimited', false)
        $('#modalInterfaces #modalInterfacesForm').parsley();

        window.Parsley.addValidator('cidr', {
            validateString: function (value, id) {
                var ip = "^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])(\/([0-9]|[1-2][0-9]|3[0-2]))$";
                return value.match(ip);
            },
            messages: {
                en: 'This string is not CIDR format'
            }
        });
    });

    $("#modalInterfaces #send").on('click', function (e) {
        var form = $('#modalInterfacesForm');
        data = form.serializeObject()
        form.parsley().validate();
        if (form.parsley().isValid()) {
            data['net'] = data['ifname']
            data['table'] = 'interfaces'
            if (data['id'] == "") {
                //Insert
                data['allowed'] = { 'roles': false, 'categories': false, 'groups': false, 'users': false }
                delete data['id']
                var notice = new PNotify({
                    text: 'Creating interface...',
                    hide: false,
                    opacity: 1,
                    icon: 'fa fa-spinner fa-pulse'
                })
                $.ajax({
                    type: "POST",
                    url: "/admin/table/add/interfaces",
                    data: JSON.stringify(data),
                    contentType: "application/json",
                    success: function (data) {
                        notice.update({
                            title: 'Created',
                            text: 'Interface created successfully',
                            hide: true,
                            delay: 1000,
                            icon: 'fa fa-' + data.icon,
                            opacity: 1,
                            type: 'success'
                        })
                        $('form').each(function () { this.reset() });
                        $('.modal').modal('hide');
                    },
                    error: function (data) {
                        notice.update({
                            title: 'ERROR creating interface',
                            text: data.responseJSON.description,
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 2000,
                            opacity: 1
                        })
                    }
                });
            } else {
                //Update
                data['name'] = $('#modalInterfacesForm #name').val();
                var notice = new PNotify({
                    text: 'Updating interface...',
                    hide: false,
                    opacity: 1,
                    icon: 'fa fa-spinner fa-pulse'
                })
                $.ajax({
                    type: "PUT",
                    url: "/admin/table/update/interfaces",
                    data: JSON.stringify(data),
                    contentType: "application/json",
                    success: function (data) {
                        notice.update({
                            title: 'Updated',
                            text: 'Interface updated successfully',
                            hide: true,
                            delay: 1000,
                            icon: 'fa fa-' + data.icon,
                            opacity: 1,
                            type: 'success'
                        })
                        $('form').each(function () { this.reset() });
                        $('.modal').modal('hide');
                    },
                    error: function (data) {
                        notice.update({
                            title: 'ERROR updating interface',
                            text: data.responseJSON.description,
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 2000,
                            opacity: 1
                        })
                    }
                });
            }


        }

    });


    // VIDEOS
    videos_table = $('#videos').DataTable({
        "ajax": {
            "url": "/admin/table/videos",
            "contentType": "application/json",
            "type": 'POST',
            "data": function (d) { return JSON.stringify({ 'order_by': 'name' }) }
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
                "defaultContent": '' //'<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
            },
            { "data": "name" },
            { "data": "description" },
            {
                "className": 'actions-control',
                "orderable": false,
                "data": null,
                "defaultContent": '<button id="btn-alloweds" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-users" style="color:darkblue"></i></button>'
                //~ '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button> \
                //~ <button id="btn-edit" class="btn btn-xs btn-edit-interface" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>'
            },
        ],
        "order": [[1, 'asc']]
    });

    $('#videos').find(' tbody').on('click', 'button', function () {
        var data = videos_table.row($(this).parents('tr')).data();
        switch ($(this).attr('id')) {
            case 'btn-alloweds':
                modalAllowedsFormShow('videos', data)
                break;
        }
    });

    $('.add-new-videos').on('click', function () {
        $("#modalVideos #modalAddVideos")[0].reset();
        $('#modalVideos').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        $('#modalVideos #modalAddVideos').parsley();
        setAlloweds_add('#alloweds-videos-add');
        setRangeSliders();
    });

    $("#modalVideos #send").on('click', function (e) {
        var form = $('#modalAddVideos');
        form.parsley().validate();
        data = $('#modalAddVideos').serializeObject();
        data = replaceAlloweds_arrays('#modalAddVideos #alloweds-videos-add', data)
        data['table'] = 'videos'
        var notice = new PNotify({
            text: 'Creating video...',
            hide: false,
            opacity: 1,
            icon: 'fa fa-spinner fa-pulse'
        })
        $.ajax({
            type: "POST",
            url: "/admin/table/add/videos",
            data: JSON.stringify(data),
            contentType: "application/json",
            success: function (data) {
                notice.update({
                    title: 'Created',
                    text: 'Video created successfully',
                    hide: true,
                    delay: 1000,
                    icon: 'fa fa-' + data.icon,
                    opacity: 1,
                    type: 'success'
                })
                $('form').each(function () { this.reset() });
                $('.modal').modal('hide');
            },
            error: function (data) {
                notice.update({
                    title: 'ERROR creating video',
                    text: data.responseJSON.description,
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 2000,
                    opacity: 1
                })
            }
        });
    });

    function setRangeSliders(id) {
        $("#videos-heads").ionRangeSlider({
            type: "single",
            min: 1,
            max: 4,
            step: 1,
            grid: true,
            disable: false
        }).data("ionRangeSlider").update();
        $("#videos-ram").ionRangeSlider({
            type: "single",
            min: 8000,
            max: 128000,
            step: 8000,
            grid: true,
            disable: false
        }).data("ionRangeSlider").update();
        $("#videos-vram").ionRangeSlider({
            type: "single",
            min: 8000,
            max: 128000,
            step: 8000,
            grid: true,
            disable: false
        }).data("ionRangeSlider").update();
    }



    // BOOTS
    boots_table = $('#boots').DataTable({
        "ajax": {
            "url": "/admin/table/boots",
            "contentType": "application/json",
            "type": 'POST',
            "data": function (d) { return JSON.stringify({ 'order_by': 'name' }) }
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
                "defaultContent": '' //'<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
            },
            { "data": "name" },
            { "data": "description" },
            {
                "className": 'actions-control',
                "orderable": false,
                "data": null,
                "defaultContent": '<button id="btn-alloweds" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-users" style="color:darkblue"></i></button>'
                //~ '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button> \
                //~ <button id="btn-edit" class="btn btn-xs btn-edit-interface" type="button"  data-placement="top" ><i class="fa fa-pencil" style="color:darkblue"></i></button>'
            },
        ],
        "order": [[1, 'asc']]
    });

    $('#boots').find(' tbody').on('click', 'button', function () {
        var data = boots_table.row($(this).parents('tr')).data();
        switch ($(this).attr('id')) {
            case 'btn-alloweds':
                modalAllowedsFormShow('boots', data)
                break;

        }
    });
    $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on)
})
function socketio_on(){
    socket.on('data', function (data) {
        var dict = JSON.parse(data);
        switch (dict['table']) {
            case 'videos':
                dtUpdateInsert(videos_table, dict['data'], false);
                break;
            case 'interfaces':
                dtUpdateInsert(int_table, dict['data'], false);
                break;
            case 'boots':
                dtUpdateInsert(boots_table, dict['data'], false);
                break;
            case 'qos_net':
                dtUpdateInsert(qosnet_table, dict['data'], false);
                break;
            case 'qos_disk':
                dtUpdateInsert(qosdisk_table, dict['data'], false);
                break;
            case 'remotevpn':
                dtUpdateInsert(remotevpn_table, dict['data'], false);
                break;
        }

    });

    socket.on('vpn', function (data) {
        var data = JSON.parse(data);
        if (data['kind'] == 'url') {
            window.open(data['url'], '_blank');
        }
        if (data['kind'] == 'file') {
            var vpnFile = new Blob([data['content']], { type: data['mime'] });
            var a = document.createElement('a');
            a.download = data['name'] + '.' + data['ext'];
            a.href = window.URL.createObjectURL(vpnFile);
            var ev = document.createEvent("MouseEvents");
            ev.initMouseEvent("click", true, false, self, 0, 0, 0, 0, 0, false, false, false, false, 0, null);
            a.dispatchEvent(ev);
        }
    });

    socket.on('result', function (data) {
        var data = JSON.parse(data);
        new PNotify({
            title: data.title,
            text: data.text,
            hide: true,
            delay: 4000,
            icon: 'fa fa-' + data.icon,
            opacity: 1,
            type: data.type
        });
        //users_table.ajax.reload()
    });

    socket.on('delete', function (data) {
        //~ console.log('delete')
        var dict = JSON.parse(data);
        data = dict['data']
        //~ var row = table.row('#'+data.id).remove().draw();
        switch (dict['table']) {
            case 'videos':
                var row = videos_table.row('#' + data.id).remove().draw();
                break;
            case 'interfaces':
                var row = int_table.row('#' + data.id).remove().draw();
                break;
            case 'boots':
                var row = boots_table.row('#' + data.id).remove().draw();
                break;
            case 'qos_net':
                var row = qosnet_table.row('#' + data.id).remove().draw();
                break;
            case 'qos_disk':
                var row = qosdisk_table.row('#' + data.id).remove().draw();
                break;
            case 'remotevpn':
                var row = remotevpn_table.row('#' + data.id).remove().draw();
                break;
        }
        new PNotify({
            title: "Deleted",
            text: "Resource " + data.name + " has been deleted",
            hide: true,
            delay: 4000,
            icon: 'fa fa-success',
            opacity: 1,
            type: 'success'
        });
    });
}

function removeQosAd(data) {
    $.each(data, function (key, value) {
        if (key.includes('@')) {
            data[key.split('@')[0] + key.split('@')[1]] = value
            delete data[key]
        }
    });
    return data;
}

function QosDiskParse(data) {
    data['iotune'] = {}
    $.each(data, function (key, value) {
        if (key.startsWith('iotune-')) {
            data['iotune'][key.split('-')[1]] = parseInt(value) || 0
            delete data[key];
        }
    });
    return data;
}

function QosNetParse(data) {
    data['bandwidth'] = { 'inbound': {}, 'outbound': {} }
    $.each(data, function (key, value) {
        if (key.startsWith('qos-bandwidth-inbound')) {
            data['bandwidth']['inbound']['@' + key.split('-')[3]] = parseInt(value) || 0
            delete data[key];
        }
        if (key.startsWith('qos-bandwidth-outbound')) {
            data['bandwidth']['outbound']['@' + key.split('-')[3]] = parseInt(value) || 0
            delete data[key];
        }
    });
    return data;
}


function populateDropdown(table, dropdown_id, selected_id, custom) {
    $(dropdown_id).find('option').remove().end();
    pluck = ['id', 'name', 'description']
    $.ajax({
        type: "POST",
        url: "/api/v3/admin/table/" + table,
        data: JSON.stringify({ 'pluck': pluck }),
        contentType: "application/json",
        accept: "application/json",
        success: function (data) {
            if (!(custom == false)) {
                $(dropdown_id).append('<option value=' + custom.id + '>' + custom.name + '</option>');
            }
            data.forEach(function (item) {
                $(dropdown_id).append('<option title="' + item.description + '" value=' + item.id + '>' + item.name + '</option>');
            });
            if (selected_id != false) {
                $(dropdown_id + ' option[value="' + selected_id + '"]').prop("selected", true);
            }
        }
    });
}