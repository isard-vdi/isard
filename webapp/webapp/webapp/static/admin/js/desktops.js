/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

var href = location.href;
url=href.match(/([^\/]*)\/*$/)[1];
$('#global_actions').css('display','block');
// Sort by Last Access in Desktops table
order=17

loading_events=[]
deleted_events=[]
opened_row=null
columns = [
    {
        "className": 'details-control',
        "orderable": false,
        "data": null,
        "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
    },
    {
        "data": "icon", "render": function (data, type, full, meta) {
            img_url = location.protocol + '//' + document.domain + ':' + location.port + full.image.url
            if (! "booking_id" in full) {
                booking_id = false
            } else {
                booking_id = full.booking_id
            }
            return renderBooking(full.create_dict.reservables, booking_id) + "<img src='" + img_url + "' width='50px'>"
        }
    },
    { "data": "name" },
    {
        "data": "status", "render": function (data, type, full, meta) {
            return renderStatus(full)
        }
    },
    {
        "data": null, "className": 'viewer',
        "width": "100px",
        "render": function (data, type, full, meta) {
            return renderAction(full) + renderDisplay(full)
        }
    },
        {
        "data": "persistent", "render": function (data, type) {
            if (type === 'filter') {
                return data ? 'true' : 'false'
            }
            if (data == false) {
                return '<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>'
            } else {
                return `<i class="fa fa-circle" aria-hidden="true"  style="color:green"></i>`
            }
        }
    },
    {
        "data": "create_dict.reservables", "render": function (data, type, full) {
            if (data) {
                return data.vgpus
            } else {
                return '-'
            }
        }
    },
    {
        "data": "ram", "width": "100px",
        "render": function (data, type, full, meta) {
            if (type == "display" || type === 'filter') {
                return (full.create_dict.hardware.memory / 1024 / 1024).toFixed(2) + "GB"
            }
            return full.create_dict.hardware.memory
        }
    },
    { "data": "create_dict.hardware.vcpus", "width": "10px" },
    { "data": "user_name" },
    { "data": "role" },
    { "data": "category_name" },
    { "data": "group_name" },
    {
        "data": "server", "width": "10px", "defaultContent": "-", "render": function (data, type, full, meta) {
            if ('server' in full) {
                if (full["server"] == true) {
                    if (full["server_autostart"]) {
                        return "AUTO"
                    } else {
                        return 'SERVER';
                    }
                   
                } else {
                    return '-';
                }
            } else {
                return '-';
            }
        }
    },
    {
        "data": "hyp_started", "width": "100px", "render": function (data, type, full, meta) {
            if ('hyp_started' in full && full.hyp_started != '') {
                return full.hyp_started;
            } else {
                return '-'
            }
        },
        "visible": $('meta[id=user_data]').attr('data-role') == 'admin'
    },
    {
        "data": "favourite_hyp", "width": "100px", "render": function (data, type, full, meta) {
            if ('favourite_hyp' in full && full.favourite_hyp != '') {
                return full.favourite_hyp.join(",");
            } else {
                return '-'
            }
        }
    },
    {
        "data": "forced_hyp", "width": "100px", "render": function (data, type, full, meta) {
            if ('forced_hyp' in full && full.forced_hyp != '') {
                return full.forced_hyp.join(",");
            } else {
                return '-'
            }
        },
        "visible": $('meta[id=user_data]').attr('data-role') == 'admin'
    },
    {
        "data": "bastion.http.enabled",
        "render": function (data, type) {
            if (type === 'display') {
                if (data === true) {
                    return `<i class="fa fa-circle" aria-hidden="true"  style="color:green"></i>`
                } else {
                    return '<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>'
                }
            }
            return data === true ? 'true' : 'false'
        }
    },
    {
        "data": "bastion.ssh.enabled",
        "render": function (data, type) {
            if (type === 'display') {
                if (data === true) {
                    return `<i class="fa fa-circle" aria-hidden="true"  style="color:green"></i>`
                } else {
                    return '<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>'
                }
            }
            return data === true ? 'true' : 'false'
        }
    },
    {
        "data": "bastion.domain",
        "render": function (data, type) {
            return data || '-'
        }
    },
    {
        "data": "accessed", 'defaultContent': '', "render": function (data, type, full, meta) {
            if (type === 'display' || type === 'filter') {
                return moment.unix(full.accessed).fromNow()
            }
            return full.accessed
        }
    },
    {
        "className": 'text-center',
        "data": null,
        "orderable": false,
        "defaultContent": '<input type="checkbox" class="form-check-input"></input>'
    },
    { "data": "id", "visible": false },
]

function getGroupParam() {
    return window.location.href.slice(window.location.href.indexOf('?') + 1).split('searchDomainId=')[1];
}

$(document).ready(function() {
    $template_domain = $(".template-detail-domain");
    $admin_template_domain = $(".admin-template-detail-domain");

    var stopping_timer=null
    modal_add_desktops = $('#modal_add_desktops').DataTable()
    initalize_modal_all_desktops_events()
    $('.btn-add-desktop').on('click', function () {
        $('#allowed-title').html('')
        $('#alloweds_panel').css('display','block');
        setAlloweds_add('#alloweds-block');
        if ($('meta[id=user_data]').attr('data-role') == 'manager'){
            $('#categories_pannel').hide();
            $('#roles_pannel').hide();
        }

        $("#modalAddDesktop #send").unbind('click');
        $("#modalAddDesktop #send").on('click', function(e){
            var form = $('#modalAdd');

            form.parsley().validate();

            if (form.parsley().isValid()){
                template_id=$('#modalAddDesktop #template').val();
                if (template_id !=''){
                    data=$('#modalAdd').serializeObject();
                    data=replaceAlloweds_arrays('#modalAddDesktop #alloweds-block',data)
                    name = data["name"]
                    description = data["description"]
                    allowed = data["allowed"]

                    var notice = new PNotify({
                        text: 'Creating desktops...',
                        hide: true,
                        opacity: 1,
                        icon: 'fa fa-spinner fa-pulse'
                    })

                    $.ajax({
                        type: "POST",
                        url:"/api/v3/persistent_desktop/bulk",
                        data: JSON.stringify({name, template_id, description, allowed}),
                        contentType: "application/json",
                        error: function(data) {
                            notice.update({
                                title: 'ERROR creating desktops',
                                text: data.responseJSON.description,
                                type: 'error',
                                hide: true,
                                icon: 'fa fa-warning',
                                delay: 5000,
                                opacity: 1
                            })
                        },
                        success: function(data) {
                            notice.update({
                                title: 'New desktops',
                                text: 'Desktops created successfully',
                                hide: true,
                                delay: 2000,
                                icon: 'fa fa-' + data.icon,
                                opacity: 1,
                                type: 'success'
                            })
                            $('form').each(function() {
                                this.reset()
                            })
                            $('.modal').modal('hide')
                        }
                    });
                }else{
                    $('#modal_add_desktops').closest('.x_panel').addClass('datatables-error');
                    $('#modalAddDesktop #datatables-error-status').html('No template selected').addClass('my-error');
                }
            }
        });

         if($('.limits-desktops-bar').attr('aria-valuenow') >=100){
            new PNotify({
                title: "Quota for creating desktops full.",
                    text: "Can't create another desktop, category quota full.",
                    hide: true,
                    delay: 3000,
                    icon: 'fa fa-alert-sign',
                    opacity: 1,
                    type: 'error'
                });
        }else{
            setHardwareOptions('#modalAddDesktop');
            $("#modalAdd")[0].reset();
            $('#modalAddDesktop').modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');
            $('#modalAddDesktop #hardware-block').hide();
            $('#modalAdd').parsley();
            modal_add_desktop_datatables();
        }
    });

    $('.btn-bulk-edit-desktops').on('click', function () {
        ids = []
        filter = domains_table.rows('.active').data().length ? '.active' : { filter: 'applied' }

        $('#modalBulkEdit #desktops-list').empty()
        $('#modalBulkEdit #desktops-number').text(domains_table.rows(filter).data().length + " desktop(s) will be updated")
        $.each(domains_table.rows(filter).data(), function (key, value) {
            ids.push(value['id']);
            $('#modalBulkEdit #desktops-list').append(
                '<p style="font-size:smaller; margin: 0px">' + value['name'] + '</p>'
            )
        });

        setHardwareOptions('#modalBulkEdit');
        disableFirstOption('#modalBulkEdit');

        $('#modalBulkEdit #edit-network-checkbox').show();
        $('#modalBulkEdit #hardware-interfaces option:first').remove();
        $('#modalBulkEdit #virtualization_nested-checkbox').remove();

        showAndHideByCheckbox($('#modalBulkEdit #edit-network'), $('#modalBulkEdit #network-row'));
        showAndHideByCheckbox($('#modalBulkEdit #edit-viewers'), $('#modalBulkEdit #viewers-row'));
        showAndHideByCheckbox($('#modalBulkEdit #edit-credentials'), $('#modalBulkEdit #credentials-row'))

        $('#modalBulkEdit #ids').val(ids.join(','));
        $("#modalBulkEditForm")[0].reset();
        $('#modalBulkEditForm :checkbox').iCheck('uncheck').iCheck('update');
        $('#modalBulkEdit').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
    });

    $('#modalBulkEdit #send').on('click', function (e) {
        var form = $('#modalBulkEditForm')
        if (form.parsley().isValid()) {
            data = form.serializeObject()
            for (let [key, value] of Object.entries(data)) {
                if (key.startsWith('guest_properties-credentials-')) {
                    if (!data['edit-viewers'] || !data['edit-credentials']) {
                        delete data[key]
                    }
                } else if (key.startsWith('viewers-')) {
                    if (!data['edit-viewers']) {
                        delete data[key]
                    }
                } else if (key === 'hardware-interfaces') {
                    if (!data['edit-network']) {
                        delete data[key]
                    }
                } else if (key === 'ids') {
                    data['ids'] = data['ids'].split(',')
                } else if (value === '--') {
                    delete data[key]
                } else if (value === 'on') {
                    data[key] = true
                }
                if (key.startsWith('hardware-')) {
                    data['edit-hardware'] = true
                }
            }
            data = parse_desktop_bulk(data)

            var notice = new PNotify({
                title: 'Updating ' + ids.length + ' desktop(s)',
                hide: true,
                opacity: 1,
                icon: 'fa fa-spinner fa-pulse'
            })

            $.ajax({
                type: 'PUT',
                url: '/api/v3/domain/bulk',
                data: JSON.stringify(data),
                contentType: 'application/json',
                success: function (data) {
                    $('form').each(function () {
                        this.reset()
                    })
                    $('.modal').modal('hide')
                    notice.update({
                        title: 'Updated',
                        text: ids.length + ' desktop(s) updated successfully',
                        hide: true,
                        icon: 'fa fa-success',
                        delay: 4000,
                        opacity: 1,
                        type: 'success'
                    })
                },
                error: function (data) {
                    notice.update({
                        title: 'ERROR updating multiple desktops',
                        text: data.responseJSON.description,
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 5000,
                        opacity: 1
                    })
                }
            });
        }
    });

    $("#modalTemplateDesktop #send").on('click', function(e){
            var form = $('#modalTemplateDesktopForm');
            form.parsley().validate();
            if (form.parsley().isValid()){
                desktop_id=$('#modalTemplateDesktopForm #id').val();
                if (desktop_id !=''){
                    data=$('#modalTemplateDesktopForm').serializeObject();
                    data=replaceAlloweds_arrays('#modalTemplateDesktopForm #alloweds-add',data)
                    data['enabled']=$('#modalTemplateDesktopForm #enabled').prop('checked')

                    name=data["name"]
                    allowed=data["allowed"]
                    description=data["description"]
                    enabled=data["enabled"]

                    var notice = new PNotify({
                        text: 'Creating template...',
                        hide: false,
                        opacity: 1,
                        icon: 'fa fa-spinner fa-pulse'
                    })

                    $.ajax({
                        type: "POST",
                        url:"/api/v3/template",
                        data: JSON.stringify({name, desktop_id, allowed, description, enabled}),
                        contentType: "application/json",
                        error: function(data) {
                            notice.update({
                                title: 'ERROR creating template',
                                text: data.responseJSON.description,
                                type: 'error',
                                hide: true,
                                icon: 'fa fa-warning',
                                delay: 5000,
                                opacity: 1
                            })
                        },
                        success: function(data) {
                            $('form').each(function() {
                                this.reset()
                            })
                            $('.modal').modal('hide');
                            notice.update({
                                title: 'New template',
                                text: 'Template created successfully',
                                hide: true,
                                delay: 2000,
                                icon: 'fa fa-' + data.icon,
                                opacity: 1,
                                type: 'success'
                            })
                        }
                    });

                }else{
                    $('#modal_add_desktops').closest('.x_panel').addClass('datatables-error');
                    $('#modalAddDesktop #datatables-error-status').html('No template selected').addClass('my-error');
                }
            }
        });

    // Setup - add a text input to each footer cell
    $('#domains tfoot th').each( function () {
        var title = $(this).text();
        if (['', 'Icon', 'Action', 'Enabled'].indexOf(title) == -1){
            $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
        }
    } );

    $template = $(".template-detail-domain");

    const filter_list = ['category', 'favourite_hyp', 'forced_hyp', 'group', 'hyp_started', 'memory', 'name', 'server', 'status', 'user', 'vcpus'];
    const options = filter_list.map(item => `<option value="${item}">${item.charAt(0).toUpperCase() + item.slice(1).replace(/_/g, ' ')}</option>`);
    $('#filter-select').append(options.join(''));
    var selectedCategories = [$('meta[id=user_data]').attr('data-categoryid')]

    let searchDomainId = getGroupParam()
    if (!searchDomainId) {
        // set the filter box category on loading the document
        initial_filters();
    }

    domains_table = $("#domains").DataTable({
      ajax: {
        url: "/admin/domains",
        type: "POST",
        contentType: 'application/json',
        dataSrc : "",
        data: function () {
            var categories = [];
            categories = $('#filter-category #category').val();
            if ($('#filter-category').length) {
                return JSON.stringify({
                    'kind': "desktop",
                    'categories': JSON.stringify(categories)
                });
            } else {
                return JSON.stringify({
                    'kind': "desktop",
                    'categories': JSON.stringify([])
                });
            }
        }
    },
      initComplete: function (settings, json) {
        $.each(deleted_events, function (index, value) {
          domains_table
            .row("#" + value.id)
            .remove()
            .draw();
        });
        deleted_events = [];
        $.each(loading_events, function (index, value) {
          data = { ...domains_table.row("#" + value.id).data(), ...value };
          dtUpdateInsert(domains_table, data, false);
        });
        loading_events = [];
      },
      language: {
        loadingRecords: "&nbsp",
        processing:
          '<p>Loading...</p><i syle="font-size: 1rem;" class="fa fa-spinner fa-pulse fa-2x fa-fw"></i>',
      },
      processing: true,
      rowId: "id",
      deferRender: true,
      paging: true,
      cache: false,
      columns: columns,
      order: [[order, "des"]],
      rowCallback: function (row, data) {
        if ("server" in data) {
          if (data["server"] == true) {
            $(row).css("background-color", "#f7eac6");
          } else {
            $(row).css("background-color", "#ffffff");
          }
        }
      },
    });

    // Apply the search
    domains_table.columns().every(function () {
        var that = this;

        $('input', this.footer()).on('keyup change', function () {
            if (that.search() !== this.value) {
                that
                    .search(this.value)
                    .draw();
            }
        });
    });

    if (searchDomainId) {
        domains_table.search(searchDomainId).draw()
    }

    var selectedCategories = ''

    $("#btn-search").on("click", function () {
        var table = $("#domains").DataTable();
        // do for each item filter box
        $("#filter-boxes .filter-item").each(function () {
            var operator = $(this).find(".operator-select").val();
            var title = $(this).find(".filter-box").attr("index");
            if ($(this)
            .find(".filter-box").val()==null) {
                var values = [""]
            } else {
                var values = $(this).find(".filter-box").val().map(value => 
                    value === "Maintenance" ? value : `^${value.trim()}$`
                );
            }
            var searchParams = values.join("|");
            if (title === "category") {
                if (JSON.stringify(selectedCategories) !== JSON.stringify(values)) {
                selectedCategories = $(".filter-item #" + title).val();
                table.ajax.reload();
            }
            } else {
            // search in the loaded table content
            table.columns().every(function () {
                header = $(this.header()).text().trim().toLowerCase();
                if (header === title) {
                    if (searchParams.length) {
                        if (operator === "is") {
                            const regex = searchParams ?
                                '(?:' + searchParams + ')' : '';
                            this.search(regex, true, false).draw();
                        } else if (operator === "is-not" && values.length) {
                            const regex = "^(?!.*?(" + searchParams + ")).*$"
                            this.search(regex, true, false).draw();
                        }
                    } else {
                        this.search("").draw()
                    }
                }
            });
        }
    });
        if (!$("#filter-category").length && selectedCategories !== null) {
            $('#category').empty();
            selectedCategories = null;
            table.ajax.reload();
        }
        
    });

    $("#btn-reload").on("click", function () {
        reloadOtherFiltersContent(domains_table);
    });

     $("#btn-clear").on("click", function () {
        $('.filter-box').each(function () {
            removeFilter($(this).attr('id'))
        })
    });

    $('#filter-boxes').on('click', '.btn-delete-filter', function () {
        var name = $(this).prop('name');
        removeFilter(name);
    });


    $('.panel_toolbox .btn-disabled').click(function () {
        domains_table.draw();
    });

    domains_table.on( 'click', 'tbody tr', function (e) {
            toggleRow(this, e);
     });

     $('#filter-select').on('change', function () {
        const item = $(this).val();
        if (item !== "null" && !$(`#filter-boxes #${item}`).length) {
          const node = newFilterBox(item);
          $('#filter-boxes').append(node);
          populateSelect(item);
          $(this).find(`option[value='${item}']`).remove();
        }
      });

    // Bulk actions
    $('#mactions').on('change', function () {
        action=$(this).val();
        ids=[]

        // Selected desktops
        if(domains_table.rows('.active').data().length){
            names = '<ul>'
            $.each(domains_table.rows('.active').data(),function(key, value){
                names+= "<li>" + value['name']+'</li>';
                ids.push(value['id']);
            });
            names += '</ul>'
            new PNotify({
                title: 'Warning!',
                text: "You are about to " + action + " these desktops:\n\n" + names,
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
            }).get().on('pnotify.confirm', function() {
                var notify = new PNotify();
               $.ajax({
                    type: "POST",
                    url:"/api/v3/admin/multiple_actions",
                    data: JSON.stringify({'ids':ids, 'action':action}),
                    contentType: "application/json",
                    accept: "application/json",
                    error: function(data) {
                        notify.update({
                            title: "ERROR " + action + " desktop(s)",
                            text: data.responseJSON ?  data.responseJSON.description : "Something went wrong",
                            hide: true,
                            delay: 3000,
                            icon: 'fa fa-alert-sign',
                            opacity: 1,
                            type: 'error'
                        })
                        $('#mactions option[value="none"]').prop("selected", true);
                    },
                    success: function() {
                        notify.update({
                            title: 'Processing',
                            text: `Processing action: ${action} on ${ids.length} desktop(s)`,
                            hide: false,
                            type: 'info',
                            icon: 'fa fa-spinner fa-pulse',
                            opacity: 1
                        });
                        $('#mactions option[value="none"]').prop("selected", true);
                    },
                });
            }).on('pnotify.cancel', function() {
                $('#mactions option[value="none"]').prop("selected",true);
            });
        // All desktops
        } else {
            $.each(domains_table.rows({filter: 'applied'}).data(),function(key, value){
                ids.push(value['id']);
            });
            new PNotify({
                title: 'Warning!',
                text: "You are about to " + action + " all the desktops in the list (" + domains_table.rows({filter: 'applied'}).data().length + " desktops)!\nPlease write <b>\"I'm aware\"</b> in order to confirm the action",
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
                            click: function(notice, value){
                                if (value == "I'm aware") {
                                    notice.remove();
                                    var notify = new PNotify()
                                    $.ajax({
                                        type: "POST",
                                        url:"/api/v3/admin/multiple_actions",
                                        data: JSON.stringify({'ids':ids, 'action':action}),
                                        contentType: "application/json",
                                        accept: "application/json",
                                        error: function(data) {
                                            notify.update({
                                                title: "ERROR " + action + " desktops",
                                                text: data.responseJSON ?  data.responseJSON.description : "Something went wrong",
                                                hide: true,
                                                delay: 3000,
                                                icon: 'fa fa-alert-sign',
                                                opacity: 1,
                                                type: 'error'
                                            })
                                            $('#mactions option[value="none"]').prop("selected", true);
                                        },
                                        success: function() {
                                            notify.update({
                                                title: 'Processing',
                                                text: `Processing action: ${action} ${ids.length} desktops`,
                                                type: 'info',
                                                hide: false,
                                                icon: 'fa fa-spinner fa-pulse',
                                                opacity: 1
                                            });
                                            $('#mactions option[value="none"]').prop("selected",true);
                                        },
                                        always: function() {
                                            $('#mactions option[value="none"]').prop("selected", true);
                                        }
                                    });
                                } else {
                                    new PNotify({
                                        title: "Cancelled",
                                        text: "",
                                        hide: true,
                                        delay: 1000,
                                        icon: 'fa fa-info',
                                        opacity: 1,
                                        type: 'info'
                                    });
                                    $('#mactions option[value="none"]').prop("selected",true);
                                }
                            }
                        },
                        {
                            text: "Cancel",
                            addClass: "",
                            click: function(notice){
                                notice.remove();
                                $('#mactions option[value="none"]').prop("selected",true);
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
    } );

    $('#domains').find('tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        var row = domains_table.row( tr );
        domain_id=row.data().id

        if ( row.child.isShown() ) {
            // This row is already open - close it
            opened_row=null;
            row.child.hide();
            tr.removeClass('shown');
        }
        else {
             if (row.data().status=='Creating'){
                 //In this case better not to open detail as ajax snippets will fail
                 //Maybe needs to be blocked also on other -ing's
                        new PNotify({
                        title: "Domain is being created",
                            text: "Wait till domain ["+row.data().name+"] creation completes to view details",
                            hide: true,
                            delay: 3000,
                            icon: 'fa fa-alert-sign',
                            opacity: 1,
                            type: 'error'
                        });
             }else{
                // Open this row
                opened_row=row
                row.child( addDomainDetailPannel(row.data()) ).show();
                $.ajax({
                    type: "GET",
                    url:"/api/v3/admin/domain/" + domain_id+ "/details",
                    success: function (data) {
                        $('#status-detail-'+domain_id).html(data.detail.replace(/\"/g,''));
                        $('#description-'+domain_id).html(data.description);
                    }
                })
                actionsDomainDetail();
                setDomainDetailButtonsStatus(domain_id,row.data(),{})
                setDomainHotplug(domain_id);
                setHardwareDomainDefaultsDetails(domain_id, 'domain');
                setDomainStorage(domain_id)
                setDesktopTemplateTree(domain_id)
                 // Close other rows
                 if (domains_table.row('.shown').length) {
                     $('.details-control', domains_table.row('.shown').node()).click();
                 }
                 tr.addClass('shown');
            }
        }
    } );

    adminShowIdCol(domains_table)

    renderBooking = (reservables, booking_id) => {
        if (!reservables || reservables.length == 0 || !reservables.vgpus || reservables.vgpus.length == 0){
            return ' '
        } else {
            var color, tooltip = {}
            var sort_order = '3'
            if( booking_id == false || booking_id == null){
                color="slategrey"
                tooltip='This desktop needs to be booked'
                sort_order='0'
            } else {
                color='mediumseagreen'
                tooltip='This desktop is now in booking time'
                sort_order='2'
            }
        style = "color:"+color+"; position:absolute; margin-top:-5px; margin-left: -15px; text-shadow: 0 0 1px grey"
        return '<div style=display:none>'+sort_order+'</div><i data-toggle="tooltip" title="'+tooltip+'" class="fa fa-calendar" aria-hidden="true" style="'+style+'"></i>'
        }
    }

	// DataTable buttons
    $('#domains tbody').on( 'click', 'button', function () {
        var data = domains_table.row( $(this).parents('tr') ).data();
        switch($(this).attr('id')){
            case 'btn-play':
                if($('.quota-play .perc').text() >=100){
                    new PNotify({
                        title: "Quota for running desktops full.",
                            text: "Can't start another desktop, quota full.",
                            hide: true,
                            delay: 3000,
                            icon: 'fa fa-alert-sign',
                            opacity: 1,
                            type: 'error'
                        });
                }else{
                    $.ajax({
                        type: "GET",
                        url:"/api/v3/admin/domain/" + data['id'] + "/viewer_data",
                        success: function (resp) {
                            checkReservablesAndStart(resp.create_dict.reservables, data['id'], data['booking_id'])
                        }
                    });
                }
                break;
            case 'btn-stop':
                $.ajax({
                    type: "GET",
                    url: '/api/v3/desktop/stop/' + data["id"],
                    contentType: "application/json",
                    cache: false,
                    error: function(data) {
                        new PNotify({
                            title: 'ERROR stopping desktop',
                            text: data.responseJSON.description,
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 5000,
                            opacity: 1
                        })
                    },
                })
                break;
            case 'btn-display':
                new PNotify({
                        title: 'Connect to user viewer!',
                            text: "By connecting to desktop "+ data["name"]+" you will disconnect and gain access to that user current desktop.\n\n \
                                   Please, think twice before doing this as it could be illegal depending on your relation with the user. \n\n ",
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
                        }).get().on('pnotify.confirm', function() {
                            setViewerButtons(data.id)
                            $('#modalOpenViewer').modal({
                                backdrop: 'static',
                                keyboard: false
                            }).modal('show');
                        }).on('pnotify.cancel', function() {
                });
                break;
            case 'btn-alloweds':
                modalAllowedsFormShow('domains',data)
                break;
            case 'btn-update':
                $.ajax({
                    type: "GET",
                    url: '/api/v3/desktop/updating/' + data["id"],
                    contentType: "application/json",
                    cache: false,
                    error: function(data) {
                        new PNotify({
                            title: 'ERROR updating desktop status',
                            text: data.responseJSON.description,
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 5000,
                            opacity: 1
                        })
                    },
                })
                break;
            case 'btn-cancel':
                new PNotify({
                    title: 'Confirmation Needed',
                    text: "Are you sure you want to cancel current storage operation: " + data.current_action + "?",
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
                        type: "GET",
                        url: '/api/v3/admin/domain/storage/' + data["id"],
                        contentType: "application/json",
                        cache: false,
                        error: function (data) {
                            new PNotify({
                                title: 'ERROR retrieving desktop storage',
                                text: data.responseJSON ? data.responseJSON.description : "Something went wrong",
                                type: 'error',
                                hide: true,
                                icon: 'fa fa-warning',
                                delay: 5000,
                                opacity: 1
                            })
                        },
                        success: function (storageList) {
                            $.each(storageList, function (index, storage) {
                                $.ajax({
                                    type: "PUT",
                                    url: "/api/v3/storage/" + storage.id + "/abort_operations",
                                    contentType: "application/json",
                                    cache: false,
                                    error: function (data) {
                                        new PNotify({
                                            title: 'ERROR aborting storage operations',
                                            text: data.responseJSON ? data.responseJSON.description : "Something went wrong",
                                            type: 'error',
                                            hide: true,
                                            icon: 'fa fa-warning',
                                            delay: 5000,
                                            opacity: 1
                                        });
                                    },
                                    success: function (data) {
                                        console.log(data)
                                        new PNotify({
                                            title: 'Cancelling current storage operation...',
                                            text: '',
                                            type: 'success',
                                            hide: true,
                                            icon: 'fa fa-info',
                                            delay: 5000,
                                            opacity: 1
                                        });
                                    }
                                });
                            });
                        }
                    });
                }).on('pnotify.cancel', function () {
                });
                break;
        }
    });

    $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on)
})

function socketio_on(){
    startClientVpnSocket(socket)
    socket.on('desktop_data', function(data){
        var data = JSON.parse(data);
        if(data.status =='Started' && 'viewer' in data && 'guest_ip' in data['viewer']){
            try {
                if(!('viewer' in domains_table.row('#'+data.id).data()) || !('guest_ip' in domains_table.row('#'+data.id).data())){
                    viewerButtonsIP(data.id,data['viewer']['guest_ip'])
                }
            } catch {
                return
            }
        }
        data = {...domains_table.row("#"+data.id).data(),...data}
        if ((!($('#filter-section #category').val()) || $('#filter-section #category').val().includes(data['category']))) {
            dtUpdateInsert(domains_table, data, false);
        }
        setDomainDetailButtonsStatus(data.id, data.status, data.server);
        $('#domains tr.active .form-check-input').prop("checked", true);
    });

    socket.on('desktop_delete', function(data){
        var data = JSON.parse(data);
        if(typeof(domains_table.row('#'+data.id).id())=='undefined'){
            deleted_events.push(data)
        }else{
            domains_table.row('#'+data.id).remove().draw();
        }
    });

    socket.on ('result', function (data) {
        var data = JSON.parse(data);
        if(data.result){
            $('.modal').modal('hide');
        }
        new PNotify({
                title: data.title,
                text: data.text,
                hide: true,
                delay: 4000,
                icon: 'fa fa-'+data.icon,
                opacity: 1,
                type: data.type
        });
    });

    socket.on('add_form_result', function (data) {
        var data = JSON.parse(data);
        if(data.result){
            $("#modalAddFromBuilder #modalAdd")[0].reset();
            $("#modalAddFromBuilder").modal('hide');
            $("#modalAddFromMedia #modalAdd")[0].reset();
            $("#modalAddFromMedia").modal('hide');
            $("#modalTemplateDesktop #modalTemplateDesktopForm")[0].reset();
            $("#modalTemplateDesktop").modal('hide');
        }
        new PNotify({
                title: data.title,
                text: data.text,
                hide: true,
                delay: 4000,
                icon: 'fa fa-'+data.icon,
                opacity: 1,
                type: data.type
        });
    });

    socket.on('adds_form_result', function (data) {
        var data = JSON.parse(data);
        if(data.result){
            $("#modalAddDesktop #modalAdd")[0].reset();
            $("#modalAddDesktop").modal('hide');
        }
        new PNotify({
                title: data.title,
                text: data.text,
                hide: true,
                delay: 4000,
                icon: 'fa fa-'+data.icon,
                opacity: 1,
                type: data.type
        });
    });

    socket.on('edit_form_result', function (data) {
        var data = JSON.parse(data);
        if(data.result){
            $("#modalEdit")[0].reset();
            $("#modalEditDesktop").modal('hide');
            $("#modalBulkEditForm")[0].reset();
            $("#modalBulkEdit").modal('hide');
        }
        new PNotify({
                title: data.title,
                text: data.text,
                hide: true,
                delay: 4000,
                icon: 'fa fa-'+data.icon,
                opacity: 1,
                type: data.type
        });
    });
    socket.on('desktop_action', function (data) {
        PNotify.removeAll();
        var data = JSON.parse(data);
        if (data.status === 'failed') {
            new PNotify({
                title: `ERROR: ${data.action} on ${data.count} desktop(s).`,
                text: data.msg,
                hide: false,
                icon: 'fa fa-warning',
                opacity: 1,
                type: 'error'
            });
        } else if (data.status === 'completed') {
            new PNotify({
                title: `Action Succeeded: ${data.action}`,
                text: `The action "${data.action}" completed on ${data.count} desktop(s).`,
                hide: true,
                delay: 4000,
                icon: 'fa fa-success',
                opacity: 1,
                type: 'success'
            });
        }
    });
}
function setDesktopTemplateTree(desktop_id) {
    $.ajax({
        url: "/api/v3/admin/domain/template_tree/" + desktop_id,
        type: 'GET',
        contentType: 'application/json',
        success: function(data)
        {
            const rootElement = $('#domain_template_tree_'+desktop_id+' tbody');
            renderTable(data, rootElement,1, renderDesktopTree);
        }
    });
}

function actionsDomainDetail(){

    $('.btn-edit').on('click', function () {
        var pk=$(this).closest("[data-pk]").attr("data-pk");
        $("#modalEdit")[0].reset();
        setHardwareOptions('#modalEditDesktop','hd',pk);
        setHardwareDomainIdDefaults('#modalEditDesktop',pk);
        setMedia_add('#modalEditDesktop #media-block')
        $('#modalEditDesktop').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        $('#modalEdit').parsley();
    });

    $('.btn-xml').on('click', function () {
            var pk=$(this).closest("[data-pk]").attr("data-pk");
            $("#modalEditXmlForm")[0].reset();
            $('#modalEditXml').modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');
            $('#modalEditXmlForm #id').val(pk);
            $.ajax({
                type: "GET",
                url:"/api/v3/admin/domains/xml/" + pk,
                success: function(data)
                {
                    $('#modalEditXmlForm #xml').val(data);
                }
            });
    });

    $('.btn-server').on('click', function () {
        var pk=$(this).closest("[data-pk]").attr("data-pk");
        $("#modalServerForm")[0].reset();
        $('#modalServer').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        $('#modalServerForm #id').val(pk);
        $('#modalServerForm #server').on("ifChecked", function () {
            $('#modalServerForm #autostart').parent().removeClass("disabled");
            $('#modalServerForm #autostart').closest('.checkbox').css("opacity", 1);
        });
        $('#modalServerForm #server').on("ifUnchecked", function () {
            $('#modalServerForm #autostart').parent().addClass("disabled");
            $('#modalServerForm #autostart').closest('.checkbox').css("opacity", 0.5);
            $('#modalServerForm #server').iCheck('uncheck').iCheck('update');
        });
        $.ajax({
            type: "POST",
            url:"/api/v3/admin/table/domains",
            data: JSON.stringify({
                'id': pk,
                'pluck': ["server", "server_autostart"]
            }),
            contentType: 'application/json',
            success: function (data) {
                if (data.server == true) {
                    $('#modalServerForm #server').iCheck('check').iCheck('update').trigger('ifChecked');
                    if (data.server_autostart == true) {
                        $('#modalServerForm #autostart').iCheck('check').iCheck('update');
                    } else {
                        $('#modalServerForm #autostart').iCheck('uncheck').iCheck('update');
                    }
                } else {
                    $('#modalServerForm #server').iCheck('uncheck').iCheck('update').trigger('ifUnchecked');
                }
            }
        });
    });

    $('.btn-owner').on('click', function () {
        var pk = $(this).closest("[data-pk]").attr("data-pk");
        $("#modalChangeOwnerDomainForm")[0].reset();
        $('#modalChangeOwnerDomain').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        $('#modalChangeOwnerDomainForm #id').val(pk);
        $("#new_owner").val("");
        if ($("#new_owner").data('select2')) {
            $("#new_owner").select2('destroy');
        }
        $('#new_owner').select2({
            placeholder: "Type at least 2 letters to search.",
            minimumInputLength: 2,
            dropdownParent: $('#modalChangeOwnerDomain'),
            ajax: {
                type: "POST",
                url: '/admin/allowed/term/users',
                dataType: 'json',
                contentType: "application/json",
                delay: 250,
                data: function (params) {
                    return JSON.stringify({
                        term: params.term,
                        pluck: ['id', 'name']
                    });
                },
                processResults: function (data) {
                    return {
                        results: $.map(data, function (item, i) {
                            return {
                                text: item.name + '[' + item['uid'] + '] ',
                                id: item.id
                            }
                        })
                    };
                }
            },
        });
    });

    $("#modalChangeOwnerDomain #send").off('click').on('click', function (e) {
        var form = $('#modalChangeOwnerDomainForm');
        form.parsley().validate();

        if (form.parsley().isValid()) {
            data = form.serializeObject();
            let pk = $('#modalChangeOwnerDomainForm #id').val()
            if (domains_table.row('#' + pk).data().status == 'Started') {
                new PNotify({
                    title: 'Warning!',
                    text: "Desktop is running, changing owner will shut it down. Continue?",
                    hide: false,
                    opacity: 0.9,
                    icon: 'fa fa-warning',
                    type: 'error',
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
                    changeOwner(pk, data)
                }).on('pnotify.cancel', function () {
                });
            } else {
                changeOwner(pk, data)
            }
        }
    });

    function changeOwner(pk, data) {
        $.ajax({
            type: "PUT",
            url: `/api/v3/desktop/owner/${pk}/${data['new_owner']}`,
            contentType: 'application/json',
            success: function () {
                $('form').each(function () { this.reset() });
                $('.modal').modal('hide');
                new PNotify({
                    title: "Owner changed succesfully",
                    text: "",
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-success',
                    opacity: 1,
                    type: "success"
                });
                domains_table.ajax.reload();
            },
            error: function ({ responseJSON: { description } = {} }) {
                const msg = description ? description : 'Something went wrong';
                new PNotify({
                    title: "ERROR",
                    text: msg,
                    type: 'error',
                    icon: 'fa fa-warning',
                    hide: true,
                    delay: 15000,
                    opacity: 1
                });
            }
        });
    }


    $('.btn-template').on('click', function () {
        if($('.quota-templates .perc').text() >=100){
            new PNotify({
                title: "Quota for creating templates full.",
                text: "Can't create another template, quota full.",
                hide: true,
                delay: 3000,
                icon: 'fa fa-alert-sign',
                opacity: 1,
                type: 'error'
            });
        }else{
            var pk=$(this).closest("[data-pk]").attr("data-pk");

            setDefaultsTemplate(pk);

            $('#modalTemplateDesktop').modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');

            setAlloweds_add('#modalTemplateDesktop #alloweds-add');
        }
    });

    $('.btn-delete').on('click', function () {
        var pk=$(this).closest("[data-pk]").attr("data-pk");
        var name=$(this).closest("[data-pk]").attr("data-name");
        new PNotify({
            title: 'Confirmation Needed',
                text: "Are you sure you want to delete virtual machine: "+name+"?",
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
            }).get().on('pnotify.confirm', function() {
                $.ajax({
                    type: "DELETE",
                    url:"/api/v3/desktop/" + pk,
                    success: function(data)
                    {
                        new PNotify({
                            title: "Desktop deleted",
                            text: "Desktop "+name+" has been deleted",
                            hide: true,
                            delay: 4000,
                            icon: 'fa fa-success',
                            opacity: 1,
                            type: 'success'
                        });
                    }
                });
            }).on('pnotify.cancel', function() {
        });
    });

    $('.btn-jumperurl').on('click', function () {
        var pk=$(this).closest("[data-pk]").attr("data-pk");
        $("#modalJumperurlForm")[0].reset();
        $('#modalJumperurlForm #id').val(pk);
        $('#modalJumperurl').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        // setModalUser()
        // setQuotaTableDefaults('#edit-users-quota','users',pk)
        $.ajax({
            url: '/api/v3/desktop/jumperurl/' + pk,
            type: 'GET',
        }).done(function(data) {
            if(data.jumperurl != false){
                $('#jumperurl').show();
                $('.btn-copy-jumperurl').show();
                //NOTE: With this it will fire ifChecked event, and generate new key
                // and we don't want it now as we are just setting de initial state
                // and don't want to reset de key again if already exists!
                //$('#jumperurl-check').iCheck('check');
                $('#jumperurl-check').prop('checked',true).iCheck('update');

                $('#jumperurl').val(location.protocol + '//' + location.host+'/vw/'+data.jumperurl);
            }else{
                $('#jumperurl-check').iCheck('update')[0].unchecked;
                $('#jumperurl').hide();
                $('.btn-copy-jumperurl').hide();
            }
        }
        );
    });

    $('#jumperurl-check').unbind('ifChecked').on('ifChecked', function(event){
        if($('#jumperurl').val()==''){
            pk=$('#modalJumperurlForm #id').val();
            $.ajax({
                url: '/api/v3/desktop/jumperurl_reset/' + pk,
                type: 'PUT',
                contentType: "application/json",
                data: JSON.stringify({"disabled" : false}),
                success: function(data) {
                    $('#jumperurl').val(location.protocol + '//' + location.host+'/vw/'+data);
                }
            })
            $('#jumperurl').show();
            $('.btn-copy-jumperurl').show();
        }
        });
    $('#jumperurl-check').unbind('ifUnchecked').on('ifUnchecked', function(event){
        pk=$('#modalJumperurlForm #id').val();
        new PNotify({
            title: 'Confirmation Needed',
                text: "Are you sure you want to delete direct viewer access url?",
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
            }).get().on('pnotify.confirm', function() {
                pk=$('#modalJumperurlForm #id').val();
                $.ajax({
                    url: '/api/v3/desktop/jumperurl_reset/' + pk,
                    type: 'PUT',
                    contentType: "application/json",
                    data: JSON.stringify({"disabled" : true}),
                    success: function(data) {
                        $('#jumperurl').val('');
                    }
                })
                $('#jumperurl').hide();
                $('.btn-copy-jumperurl').hide();
            }).on('pnotify.cancel', function() {
                $('#jumperurl-check').iCheck('check');
                $('#jumperurl').show();
                $('.btn-copy-jumperurl').show();
            });
        });

    $('.btn-copy-jumperurl').on('click', function () {
        $('#jumperurl').prop('disabled',false).select().prop('disabled',true);
        document.execCommand("copy");
    });

    $('.btn-forcedhyp').on('click', function () {
        var pk=$(this).closest("[data-pk]").attr("data-pk");
        $("#modalForcedhypForm")[0].reset();
        $('#modalForcedhypForm #id').val(pk);
        $('#modalForcedhyp').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        $.ajax({
            type: "POST",
            url:"/api/v3/admin/table/domains",
            data: JSON.stringify({
                'id': pk,
                'pluck': "forced_hyp"
            }),
            contentType: 'application/json',
            accept: 'application/json',
            success: function(data)
            {
                if('forced_hyp' in data && data.forced_hyp != false && data.forced_hyp != []){
                    HypervisorsDropdown(data.forced_hyp[0]);
                    $('#modalForcedhypForm #forced_hyp').show();
                    //NOTE: With this it will fire ifChecked event, and generate new key
                    // and we don't want it now as we are just setting de initial state
                    // and don't want to reset de key again if already exists!
                    //$('#jumperurl-check').iCheck('check');
                    $('#forcedhyp-check').prop('checked',true).iCheck('update');
                }else{
                    $('#forcedhyp-check').iCheck('update')[0].unchecked;
                    $('#modalForcedhypForm #forced_hyp').hide();
                }
            }
        });
    });

    $('#forcedhyp-check').unbind('ifChecked').on('ifChecked', function(event){
        if($('#forced_hyp').val()==''){
            pk=$('#modalForcedhypForm #id').val();
            $.ajax({
                type: "POST",
                url:"/api/v3/admin/table/domains",
                data: JSON.stringify({
                    'id': pk,
                    'pluck': "forced_hyp"
                }),
                contentType: 'application/json',
                accept: 'application/json',
                success: function(data)
                {
                    if('forced_hyp' in data && data.forced_hyp != false && data.forced_hyp != []){
                        HypervisorsDropdown(data.forced_hyp[0]);
                    }else{
                        HypervisorsDropdown('');
                    }
                }
            });
            $('#modalForcedhypForm #forced_hyp').show();
        }
    });

    $('#forcedhyp-check').unbind('ifUnchecked').on('ifUnchecked', function(event){
        pk=$('#modalForcedhypForm #id').val();

        $('#modalForcedhypForm #forced_hyp').hide();
        $("#modalForcedhypForm #forced_hyp").empty();
    });

    $("#modalForcedhyp #send").off('click').on('click', function(e){
        var notice = new PNotify({
            text: 'Updating selected item...',
            hide: false,
            opacity: 1,
            icon: 'fa fa-spinner fa-pulse'
        })
        data=$('#modalForcedhypForm').serializeObject();
        $.ajax({
            type: 'PUT',
            url: `/api/v3/domain/${data["id"]}`,
            data: JSON.stringify({
                ...( ! ("forced_hyp"  in data) && {"forced_hyp": false} ),
                ...( "forced_hyp" in data && {"forced_hyp": [data.forced_hyp]} ),
            }),
            contentType: 'application/json',
            error: function(data) {
                notice.update({
                    title: 'ERROR updating forced hypervisor',
                    text: data.responseJSON.description,
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 5000,
                    opacity: 1
                })
            },
            success: function(data) {
                $('form').each(function() { this.reset() });
                $('.modal').modal('hide');
                notice.update({
                    title: 'Updated',
                    text: 'Forced hypervisor updated successfully',
                    hide: true,
                    delay: 2000,
                    icon: 'fa fa-' + data.icon,
                    opacity: 1,
                    type: 'success'
                })
            }
        })
    });

    $('.btn-favouritehyp').on('click', function () {
        var pk=$(this).closest("[data-pk]").attr("data-pk");
        $("#modalFavouriteHypForm")[0].reset();
        $('#modalFavouriteHypForm #id').val(pk);
        $('#modalFavouriteHyp').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        $.ajax({
            type: "POST",
            url:"/api/v3/admin/table/domains",
            data: JSON.stringify({
                'id': pk,
                'pluck': "favourite_hyp"
            }),
            contentType: 'application/json',
            accept: 'application/json',
            success: function(data)
            {
                if('favourite_hyp' in data && data.favourite_hyp != false && data.favourite_hyp != []){
                    HypervisorsFavDropdown(data.favourite_hyp[0]);
                    $('#modalFavouriteHypForm #favourite_hyp').show();
                    $('#favouritehyp-check').prop('checked',true).iCheck('update');
                }else{
                    $('#favouritehyp-check').iCheck('update')[0].unchecked;
                    $('#modalFavouriteHypForm #favourite_hyp').hide();
                }
            }
        });
    });


    $('#favouritehyp-check').unbind('ifChecked').on('ifChecked', function(event){
        if($('#favourite_hyp').val() == ''){
            pk=$('#modalFavouriteHypForm #id').val();
            $.ajax({
                type: "POST",
                url:"/api/v3/admin/table/domains",
                data: JSON.stringify({
                    'id': pk,
                    'pluck': "favourite_hyp"
                }),
                contentType: 'application/json',
                accept: 'application/json',
                success: function(data)
                {
                    if('favourite_hyp' in data && data.favourite_hyp != false && data.favourite_hyp != []){
                        HypervisorsFavDropdown(data.favourite_hyp[0]);
                    }else{
                        HypervisorsFavDropdown('');
                    }
                }
            });
            $('#modalFavouriteHypForm #favourite_hyp').show();
        }
    });

    $('#favouritehyp-check').unbind('ifUnchecked').on('ifUnchecked', function(event){
        pk=$('#modalFavouriteHypForm #id').val();
        $('#modalFavouriteHypForm #favourite_hyp').hide();
        $("#modalFavouriteHypForm #favourite_hyp").empty();
    });

    $("#modalFavouriteHyp #send").off('click').on('click', function(e){
        var notice = new PNotify({
            text: 'Updating selected item...',
            hide: false,
            opacity: 1,
            icon: 'fa fa-spinner fa-pulse'
        })
        data=$('#modalFavouriteHypForm').serializeObject();
        $.ajax({
            type: 'PUT',
            url: `/api/v3/domain/${data["id"]}`,
            data: JSON.stringify({
                ...( ! ("favourite_hyp"  in data) && {"favourite_hyp": false} ),
                ...( "favourite_hyp" in data && {"favourite_hyp": [data.favourite_hyp]} ),
            }),
            contentType: 'application/json',
            error: function(data) {
                notice.update({
                    title: 'ERROR updating favourite hypervisor',
                    text: data.responseJSON.description,
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 5000,
                    opacity: 1
                })
            },
            success: function(data) {
                $('form').each(function() { this.reset() });
                $('.modal').modal('hide');
                notice.update({
                    title: 'Updated',
                    text: 'Favourite hypervisor updated successfully',
                    hide: true,
                    delay: 2000,
                    icon: 'fa fa-' + data.icon,
                    opacity: 1,
                    type: 'success'
                })
            }
        })
    });

    $("#modalServer #send").off('click').on('click', function(e){
        data=$('#modalServerForm').serializeObject();
        let server=$('#modalServerForm #server').prop('checked')
        let autostart=$('#modalServerForm #autostart').prop('checked')
        $.ajax({
            type: "PUT",
            url: `/api/v3/domain/${data["id"]}`,
            data: JSON.stringify({
                'server': server,
                'server_autostart': server ? autostart : false
            }),
            contentType: "application/json",
            success: function(data)
            {
                $('form').each(function() { this.reset() });
                $('.modal').modal('hide');
                new PNotify({
                    title: "Updated",
                    text: "Server updated successfully",
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-success',
                    opacity: 1,
                    type: "success"
                });
                $("#modalServer").modal('hide');
            },
            error: function(data){
                new PNotify({
                    title: "ERROR updating server",
                    text: data.responseJSON.description,
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 15000,
                    opacity: 1
                });
            }
        });
    });

}

function HypervisorsDropdown(selected) {
    $("#modalForcedhypForm #forced_hyp").empty();
    $.ajax({
        type: "POST",
        url:"/api/v3/admin/table/hypervisors",
        data: JSON.stringify({
            'pluck':['id','hostname']
        }),
        contentType: 'application/json',
        accept: 'application/json',
        success: function(data)
        {
            data.forEach(function(hypervisor){
                $("#modalForcedhypForm #forced_hyp").append('<option value=' + hypervisor.id + '>' + hypervisor.id+' ('+hypervisor.hostname+')' + '</option>');
                if(hypervisor.id == selected){
                    $('#modalForcedhypForm #forced_hyp option[value="'+hypervisor.id+'"]').prop("selected",true);
                }
            });
        }
    });
}

function HypervisorsFavDropdown(selected) {
    $("#modalFavouriteHypForm #favourite_hyp").empty();
    $.ajax({
        type: "POST",
        url:"/api/v3/admin/table/hypervisors",
        data: JSON.stringify({
            'pluck':['id','hostname']
        }),
        contentType: 'application/json',
        accept: 'application/json',
        success: function(data)
        {
            data.forEach(function(hypervisor){
                $("#modalFavouriteHypForm #favourite_hyp").append('<option value=' + hypervisor.id + '>' + hypervisor.id+' ('+hypervisor.hostname+')' + '</option>');
                if(hypervisor.id == selected){
                    $('#modalFavouriteHypForm #favourite_hyp option[value="'+hypervisor.id+'"]').prop("selected",true);
                }
            });
        }
    });
}

function setDefaultsTemplate(id) {
    $.ajax({
        type: "GET",
        url:"/api/v3/domain/info/" + id,
        success: function(data)
        {
            $('.template-id').val(id);
            $('.template-id').attr('data-pk', id);
            $('.template-name').val('Template '+data.name);
            $('.template-description').val(data.description);
        }
    });
}

//~ RENDER DATATABLE
function addDomainDetailPannel ( d ) {
        $newPanel = $template_domain.clone();
        $newPanel = $template_domain.clone();
        $newPanel.find('#derivates-d\\.id').remove();
        $newPanel.html(function(i, oldHtml){
            return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name);
        });
        return $newPanel
}

disabled_status=['Starting','Started','Shutting-down','Stopping']
function setDomainDetailButtonsStatus(id,data,old_data){
    if(old_data.status != data.server){
        $('#actions-'+id+' .btn-server').prop('disabled', data.server);
    }
    if(old_data.status != data.status){
        if(disabled_status.includes(old_data.status) && disabled_status.includes(data.status)){
            return
        }
        if( ! old_data.status in ['Starting','Started','Shutting-down','Stopping'] && ! disabled_status.includes(data.status)){
            return
        }
        if(disabled_status.includes(data.status)){
            $('#actions-'+id+' *[class^="btn"]').prop('disabled', true);
            $('#actions-'+id+' .btn-jumperurl').prop('disabled', false);
            $('#actions-'+id+' .btn-owner').prop('disabled', false);
            $('#actions-'+id+' .btn-server').prop('disabled', false);
        }else{
            $('#actions-'+id+' *[class^="btn"]').prop('disabled', false);
        }
    }
}

function icon(data){
       viewer=""
       viewerIP="'No client viewer'"
       if(data['viewer-client_since']){viewer=" style='color:green' ";viewerIP="'Viewer client from IP: "+data['viewer-client_addr']+"'";}
       if(data.icon=='windows' || data.icon=='linux'){
           return "<i class='fa fa-"+data.icon+" fa-2x ' "+viewer+" title="+viewerIP+"></i>";
        }else{
            return "<span class='fl-"+data.icon+" fa-2x' "+viewer+" title="+viewerIP+"></span>";
        }
}

function renderDisplay(data){
        if(['Started', 'Shutting-down', 'Stopping'].includes(data.status)){
            return '<button type="button" id="btn-display" class="btn btn-pill-right btn-success btn-xs"> \
                    <i class="fa fa-desktop"></i> Show</button>';
        }
        return ''
}

function renderStatus(data) {
    if (data.status != "Maintenance") {
        return data.status;
    } else {
        tooltip = 'Operations are being performed over the desktop disk: ' + data.current_action;
        style = "color:grey; position:absolute;margin-right:2px";
        return ' <i data-toggle="tooltip" title="' + tooltip + '" class="fa fa-info-circle fa-md" aria-hidden="true" style="' + style + '"></i><p style="margin-left:12px">' + data.status +'</p>'
    }
    //To return the guest ip
    if('viewer' in data && 'guest_ip' in data['viewer']){
        return data['viewer']['guest_ip']
    }else{
        return 'No ip'
    }
} 

function renderHypStarted(data){
    res=''
    if('favourite_hyp' in data && data.favourite_hyp != ''){ res=res+'<b>Fav: </b>'+ data.favourite_hyp;}
    if('forced_hyp' in data && data.forced_hyp != ''){ res=res+'<br/><b>Forced: </b>'+ data.forced_hyp;}
    if('hyp_started' in data && data.hyp_started != ''){ res=res+'<br/><b>Started: </b>'+ data.hyp_started;}
    return res
}

function renderAction(data){
    var status=data.status;
    if(status=='Stopped'){
        return '<button type="button" id="btn-play" class="btn btn-pill-right btn-success btn-xs"><i class="fa fa-play"></i> Start</button>';
    }
    if(status=='Failed'){
        return '<button type="button" id="btn-update" class="btn btn-pill btn-warning btn-xs"><i class="fa fa-refresh"></i> Retry</button>'
    }
    if(status=='Maintenance'){
        return '<button type="button" id="btn-cancel" class="btn btn-pill btn-warning btn-xs"><i class="fa fa-ban"></i> Cancel task</button>'
    }
    if(status=='Started' || status=='Paused'){
        return '<button type="button" id="btn-stop" class="btn btn-pill-left btn-danger btn-xs"><i class="fa fa-stop"></i> Stop</button>';
    }
    if(status=='Shutting-down'){
        return '<button type="button" id="btn-stop" class="btn btn-pill-left btn-danger btn-xs"><i class="fa fa-spinner fa-pulse fa-fw"></i> Force stop</button>';
    }
    if(status=='Crashed'){
        return '<div class="Change"> <i class="fa fa-thumbs-o-down fa-2x"></i> </div>';
    }
    if(status=='Disabled'){
            return '<i class="fa fa-times fa-2x"></i>';
    }
    if(status=='DownloadFailed'){
        return '<i class="fa fa-thumbs-down fa-2x"></i>';
    }

    return '<i class="fa fa-spinner fa-pulse fa-2x fa-fw"></i>';
}


    $("#modalEditDesktop #send").on('click', function(e){
            var form = $('#modalEdit');
            form.parsley().validate();
            if (form.parsley().isValid()){
                data=$('#modalEdit').serializeObject();
                data['reservables-vgpus'] = [data['reservables-vgpus']]
                data=parse_desktop(JSON.unflatten(parseViewersOptions(data)));
                var notice = new PNotify({
                    text: 'Updating selected item...',
                    hide: false,
                    opacity: 1,
                    icon: 'fa fa-spinner fa-pulse'
                })
                $.ajax({
                    type: 'PUT',
                    url: '/api/v3/domain/'+data["id"],
                    data: JSON.stringify(data),
                    contentType: 'application/json',
                    error: function(data) {
                        notice.update({
                            title: 'ERROR updating desktop',
                            text: data.responseJSON.description,
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 5000,
                            opacity: 1
                        })
                    },
                    success: function(data) {
                        $("#modalEdit")[0].reset();
                        $("#modalEditDesktop").modal('hide');
                        domains_table.ajax.reload()
                        notice.update({
                            title: 'Updated',
                            text: 'Domain updated successfully',
                            hide: true,
                            delay: 2000,
                            icon: 'fa fa-' + data.icon,
                            opacity: 1,
                            type: 'success'
                        })
                    }
                })
            }
        });

    $("#modalEditXml #send").on('click', function(e){
        var notice = new PNotify({
            text: 'Updating xml for selected item(s)...',
            hide: false,
            opacity: 1,
            icon: 'fa fa-spinner fa-pulse'
        })
        var form = $('#modalEditXmlForm');
        id=$('#modalEditXmlForm #id').val();
        xml=$('#modalEditXmlForm #xml').val();
        $.ajax({
            type: 'PUT',
            url: '/api/v3/domain/'+id,
            data: JSON.stringify({'xml':xml}),
            contentType: 'application/json',
            error: function(data) {
                notice.update({
                    title: 'ERROR updating XML',
                    text: data.responseJSON.description,
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 5000,
                    opacity: 1
                })
            },
            success: function(data) {
                $("#modalEditXmlForm")[0].reset();
                $("#modalEditXml").modal('hide');
                notice.update({
                    title: 'Updated',
                    text: 'Domain XML updated successfully',
                    hide: true,
                    delay: 2000,
                    icon: 'fa fa-' + data.icon,
                    opacity: 1,
                    type: 'success'
                })
            }
        })
    });

        function parse_desktop(data){
            return {
                "id": data["id"],
                "name": data["name"],
                "description": data["description"],
                "guest_properties": data["guest_properties"],
                "hardware": {
                    ...("virtualization_nested" in data["hardware"]) && {"virtualization_nested": true},
                    ...(! ("virtualization_nested" in data["hardware"]) && {"virtualization_nested": false}),
                    ...("vcpus" in data["hardware"]) && {"vcpus": parseInt(data["hardware"]["vcpus"])},
                    ...("memory" in data["hardware"]) && {"memory": parseFloat(data["hardware"]["memory"])},
                    ...("videos" in data["hardware"]) && {"videos": [data["hardware"]["videos"]]},
                    ...("boot_order" in data["hardware"]) && {"boot_order": [data["hardware"]["boot_order"]]},
                    ...("interfaces" in data["hardware"]) && {"interfaces": data["hardware"]["interfaces"]},
                    ...("disk_bus" in data["hardware"]) && {"disk_bus": data["hardware"]["disk_bus"]},
                    ...("disk_size" in data["hardware"]) && {"disk_size": parseInt(data["hardware"]["disk_size"])},
                    ...( true) && {"isos":[]},
                    ...("m" in data && "isos" in data["m"]) && {"isos": setMediaIds(data["m"]["isos"])},
                    ...( true) && {"floppies":[]},
                    ...("m" in data && "floppies" in data["m"]) && {"floppies": setMediaIds(data["m"]["floppies"])},
                    "reservables": {
                        ...( true ) && {"vgpus":data["reservables"]["vgpus"]},
                        ...( data["reservables"]["vgpus"].includes(undefined) || data["reservables"]["vgpus"] == null || data["reservables"]["vgpus"].includes("None") ) &&  {"vgpus": null},
                    },
                  },
                }
        }

        function parse_desktop_bulk(data) {
            return {
                "ids": data['ids'],
                ...("edit-hardware" in data) && {
                    "hardware": {
                        ...("hardware-vcpus" in data) && { "vcpus": parseInt(data["hardware-vcpus"]) },
                        ...("hardware-memory" in data) && { "memory": parseFloat(data["hardware-memory"]) },
                        ...("hardware-videos" in data) && { "videos": [data["hardware-videos"]] },
                        ...("hardware-boot_order" in data) && { "boot_order": [data["hardware-boot_order"]] },
                        ...("hardware-edit_network" in data) && { "interfaces": data["hardware-interfaces"] },
                        ...("hardware-disk_bus" in data) && { "disk_bus": data["hardware-disk_bus"] },
                        ...("hardware-disk_size" in data) && { "disk_size": parseInt(data["hardware-disk_size"]) },
                        ...("reservables-vgpus" in data) && {
                            "reservables": {
                                ...(true) && { "vgpus": [data["reservables-vgpus"]] },
                                ...(data["reservables-vgpus"].includes(undefined) || data["reservables-vgpus"] == null || data["reservables-vgpus"].includes("None")) && { "vgpus": null },
                            },
                        },
                        ...("edit-network" in data) && { "interfaces": data['hardware-interfaces'] },
                    }
                },
                ...("edit-viewers" in data) && {
                    "guest_properties": {
                        "viewers": {
                            ...("viewers-file_rdpgw" in data) && { "file_rdpgw": { "options": null } },
                            ...("viewers-file_rdpvpn" in data) && { "file_rdpvpn": { "options": null } },
                            ...("viewers-file_spice" in data) && { "file_spice": { "options": null } },
                            ...("viewers-browser_rdp" in data) && { "browser_rdp": { "options": null } },
                            ...("viewers-browser_vnc" in data) && { "browser_vnc": { "options": null } },
                        },
                        ...("edit-credentials" in data) && {
                            "credentials": {
                                ...("guest_properties-credentials-password" in data) && { "password": data["guest_properties-credentials-password"] },
                                ...("guest_properties-credentials-username" in data) && { "username": data["guest_properties-credentials-username"] },
                            }
                        }
                    },
                },

            }
        }

        function populate_users(){
            if($("#user_id").data('select2')){
                $("#user_id").select2('destroy');
            }
            $("#user_id").select2({
                placeholder:"Type at least 2 letters to search.",
                minimumInputLength: 2,
                maximumSelectionLength: 1,
                multiple: true,
                dropdownparent: $("#modalDuplicateTemplateForm"),
                ajax: {
                    type: "POST",
                    url: '/admin/allowed/term/users',
                    dataType: 'json',
                    contentType: "application/json",
                    delay: 250,
                    data: function (params) {
                        return  JSON.stringify({
                            term: params.term,
                            pluck: ['id','name']
                        });
                    },
                    processResults: function (data) {
                        return {
                            results: $.map(data, function (item, i) {
                                return {
                                    text: item.name + '['+item['uid']+'] ',
                                    id: item.id
                                }
                            })
                        };
                    }
                },
            });
        };

        function startDesktop(domain_id) {
            $.ajax({
                type: "GET",
                url: '/api/v3/desktop/start/' + domain_id,
                contentType: "application/json",
                cache: false,
                error: function(data) {
                    new PNotify({
                        title: 'ERROR starting desktop',
                        text: data.responseJSON.description,
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 5000,
                        opacity: 1
                    })
                },
            })
        }

        function checkReservablesAndStart(reservables, domain_id, booking_id) {
            if (!(!reservables || reservables.length == 0 || !reservables.vgpus || reservables.vgpus.length == 0) || booking_id){
                        new PNotify({
                            title: 'Start this non-booked desktop?',
                            text: "You could interfere with the GPU: " + reservables.vgpus +" from another desktop. Continue?",
                            hide: false,
                            opacity: 0.9,
                            icon: 'fa fa-warning',
                            type: 'error',
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
                        }).get().on('pnotify.confirm', function() {
                            startDesktop(domain_id)
                        }).on('pnotify.cancel', function() { });
            } else {
                // start without verifications if it doesn't have bookables or has an active booking
                startDesktop(domain_id)
            }
        }

        function newFilterBox(item) {
            $('#filter-select').val('null');
            const operator =
                item !== 'category'
                    ? `
                        <select class="form-control operator-select" id="operator-${item}" style="width: 100%;">
                            <option value="is" selected=""> is </option>
                            <option value="is-not"> is not </option>
                        </select>`
                    : ''
            return `
                <div class="filter-item col-md-3 col-sm-8 col-xs-12 select2-container--focus select2-container--resize" id="filter-${item}" style="margin-bottom:20px;margin-right:10px">
                    <button name="${item}" class="btn btn-delete-filter btn-xs" type="button" data-placement="top"><i class="fa fa-times" style="color:darkred"></i></button>
                    <label>
                        <h4>${item.charAt(0).toUpperCase() + item.slice(1).replace(/_/g, ' ')}</h4>
                    </label>
                    <div style="display: inline-flex;margin-left: 10px;">
                        ${operator}
                    </div>
                    <select class="filter-box form-control" id="${item}" name="${item}[]"
                    ${$('meta[id=user_data]').attr('data-role') == 'manager' && item == 'category' ? "disabled" : ""} 
                    multiple="multiple"></select>
                    <div class="select2-resize-handle"></div>
                </div>
            `;
        }

        function fetchCategories() {
            $.ajax({
                type: "GET",
                async: false,
                url:"/api/v3/admin/userschema",
                success: function (data) {
                    return data.category
                }
            })
        } 
    
        function populateSelect(item) {
            const elem = $("#" + item)
            elem.select2();
            elem.attr("index", item);
            switch (item) {
                case ("category"):
                case ("group"):
                    $.ajax({
                        type: "GET",
                        async: false,
                        url:"/api/v3/admin/userschema",
                        success: function (d) {
                            $.each(d[item], function(pos, it) {
                                if (item=='category') { var value = it.id } else { var value = it.name }
                                if ($("#" + item + " option:contains(" + it.name + ")").length == 0) {
                                    elem.append('<option value=' + value + '>' + it.name + '</option>');
                                }
                            });
                        }
                    });
                    if (item=='category') { elem.val([$('meta[id=user_data]').attr('data-categoryid')]); }
                    break;
                case ("user"):
                    $.each(domains_table.data(), function (pos, it) {
                        var itemName = item != 'user' ? item + "_name" : "username";
                        if ($("#" + item + " option:contains(" + it[itemName] + ")").length == 0) {
                            elem.append('<option value=' + it[itemName] + '>' + it[itemName] + '</option>');
                        }
                    });
                    break;
                case ('memory'):
                    $.ajax({
                        type: "GET",
                        async: false,
                        url:"/api/v3/admin/domains/"+item+"/desktop",
                        contentType: 'application/json',
                        success: function (data) {
                            data = JSON.parse(data)
                            $.each(data, function(pos, field) {
                                field = field[item]
                                if (elem.find('option[value="' + field + 'GB"]').length === 0) {
                                    elem.append('<option value="' + field+ '">' + field + 'GB</option>');
                                }
                            });
                        }
                    });
                    elem.attr("index", 'ram(gb)')
                    break;
                case ("hyp_started"):
                case ("forced_hyp"):
                case ("favourite_hyp"):
                    $.ajax({
                        type: "POST",
                        async: false,
                        url:"/api/v3/admin/table/hypervisors",
                        data: JSON.stringify({
                            'pluck':['id','hostname']
                        }),
                        contentType: 'application/json',
                        accept: 'application/json',
                        success: function (f) {
                            $.each(f, function(pos, field) {
                                field = field['id']
                                if (typeof field === 'undefined' || field === false) {
                                    field = '-'
                                }
                                if (elem.find('option[value="' + field + '"]').length === 0) {
                                    elem.append('<option value="' + field+ '">' + field + '</option>');
                                }
                            });
                            elem.append('<option value="-">-</option>');
                        }
                    });
                    index = item.replace(/_/g, "").replace("hyp", "")
                    elem.attr("index", index)
                    break;
                case ("server"):
                    const FIELDS = ["SERVER", "AUTO", "-"];
                    $.each(FIELDS, function(pos, field) {
                        elem.append(`<option value=${field}>${field}</option>`);
                    })
                    break;
                default:
                    $.ajax({
                        type: "GET",
                        async: false,
                        url:"/api/v3/admin/domains/"+item+"/desktop",
                        success: function (data) {
                            data = JSON.parse(data)
                            $.each(data, function(pos, field) {
                                field = field[item]
                                if (elem.find('option[value="' + field + '"]').length === 0) {
                                    elem.append('<option value="' + field+ '">' + field + '</option>');
                                }
                            });
                        }
                    });
                    break;
            }
            elem.html(elem.children('option').sort(function(a, b){
                return a.text.localeCompare(b.text);
            }));
        }

  
    // set the filter box category on loading the document
    function initial_filters() {
        var node = newFilterBox('category');
        $('#filter-boxes').append(node);
        populateSelect('category');
        $('#filter-select').find(`option[value='category']`).remove();
    }

    function reloadOtherFiltersContent(table) {
        table.draw(false);
        $("#filter-boxes .filter-item[id!='filter-category']").each(function () {
          index = $(this).find(".filter-box").attr("id")
          populateSelect(index);
        });
      }


    function removeFilter(name) {
        if ($('#filter-' + name + ' #' + name).val() && name !== 'category') {
            var title = $('#filter-' + name + ' #' + name).attr("index");
            $('#domains').DataTable().columns().every(function () {
                header = $(this.header()).text().trim().toLowerCase();
                if (header === title) {
                    this.search('').draw();
                }
            });
        }
        if (name != 'category' || $('meta[id=user_data]').attr('data-role') == 'admin') {
            $('#filter-' + name).remove();
            $('#filter-select').append(`<option value="${name}">${name.charAt(0).toUpperCase() + name.slice(1).replace(/_/g, ' ')}</option>`);
            $('#filter-select').children('option').sort(function(a, b) {
                if (a.value === 'null') {
                  return -1;
                } else if (b.value === 'null') {
                  return 1;
                } else {
                  return a.text.localeCompare(b.text);
                }
              }).appendTo('#filter-select');            $('#filter-select').val('null');
        }
    }


    
