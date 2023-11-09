/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

var users_table= ''
var current_category = ''

$(document).ready(function() {
    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/administrators', {
        'query': {'jwt': localStorage.getItem("token")},
        'path': '/api/v3/socket.io/',
        'transports': ['websocket']
    });

    $template = $(".template-detail-users");

    users_table=$('#users').DataTable( {
        "initComplete": function(settings, json) {
            initUsersSockets()
            let searchUserId = getUrlParam('searchUser');
            if (searchUserId) {
                this.api().column([2]).search("(^" + searchUserId + "$)", true, false).draw();
                $('#users .xe-username input').val(searchUserId)
            }
        },
        "ajax": {
            "url": "/admin/users/quotas_limits/users",
            "dataSrc": "",
            "type" : "GET",
            "data": function(d){return JSON.stringify({})}
        },
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
                "width": "10px",
                "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
            },
            { "data": "name"},
            { "data": "username", className: "xe-username" },
            { "data": "role_name"},
            { "data": "category_name"},
            { "data": "group_name", "width": "10px"},
            { "data": "templates", "width": "10px", defaultContent: "0"},
            { "data": "desktops", "width": "10px", defaultContent: "0"},
            { "data": "domains_size", className: "xe-desktops", defaultContent: "-"},
            { "data": "media_size", className: "xe-desktops", defaultContent: "-"},
            { "data": null, className: "xe-desktops", defaultContent: "-"},
            { "data": null, className: "xe-desktops", defaultContent: "-"},
            { "data": "id", "visible": false}
        ],
		"columnDefs": [
            {
                "targets": 2,
                "render": function ( data, type, full, meta ) {
                    return '<a href="/isard-admin/admin/users/Management?searchUser='+ full.username +'">'+ full.username +'</a>'
                }
            },
            {
                "targets": 4,
                "render": function ( data, type, full, meta ) {
                    return full.category_name ? full.category_name : ''
                }
            },
            {
                "targets": 8,
                "render": function ( data, type, full, meta ) {
                    return full.domains_size ? full.domains_size.toFixed(1) : 0.0;
                }
            },
            {
                "targets": 9,
                "render": function ( data, type, full, meta ) {
                    return full.media_size ? full.media_size.toFixed(1) : 0.0;
                }
            },
            {
                "targets": 10,
                "render": function ( data, type, full, meta ) {
                    return (full.domains_size && full.media_size) ? (full.domains_size + full.media_size).toFixed(1) : 0.0;
                }
            },
            {
                "targets": 11,
                "render": function ( data, type, full, meta ) {
                    if (full.hasOwnProperty('user_storage')){
                        return full.user_storage.provider_quota.used +' ('+full.user_storage.provider_quota.relative+'%)'
                    }
                }
            }
        ],
        footerCallback: function (row, data, start, end, display) {
            var api = this.api();

            // Total over this page
            pageTotal = api
                .column(10, {search: 'applied'})
                .data()
                .reduce(function (a, b) {
                    return a + b['domains_size'] + b['media_size']
                }, 0);

            // Update footer
            $('.users-total-size').html('Applied  filter storage size: ' + pageTotal.toFixed(1) + ' GB');
        },
    });

    adminShowIdCol(users_table)

    if ($('meta[id=user_data]').attr('data-role') == 'manager'){
        // Get the column API object
        var column = users_table.column(4);
    
        // Toggle the visibility
        column.visible(!column.visible());
    }

    // Setup - add a text input to each footer cell
    $('#users tfoot tr:first th').each( function () {
        var title = $(this).text();
        if (['','Templates', 'Desktops', 'Domains size (GB)', 'Media size (GB)', 'Total size (GB)'].indexOf(title) == -1){
            $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
        }
    } );

    // Apply the search
    users_table.columns().every( function () {
        var that = this;

        $( 'input', this.footer() ).on( 'keyup change', function () {
            if ( that.search() !== this.value ) {
                that
                .search( this.value )
                .draw();
            }
        } );
    } );

    users_table.on( 'click', 'tr[role="row"]', function (e) {
        toggleRow(this, e);
    });

    $('#users').find('tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        var row = users_table.row( tr );
        if ( row.child.isShown() ) {
            row.child.hide();
            tr.removeClass('shown');
        } else {
            if ( users_table.row( '.shown' ).length ) {
                $('.details-control', users_table.row( '.shown' ).node()).click();
            }
            row.child(renderUsersDetailPannel(row.data())).show()
            actionsUserDetail()
            id = row.data().id
            $('#show-users-quota-' + id + ' .apply').html('group quota');
            setQuotaMax(
                '#show-users-quota-' + id,
                kind='user',
                id=id,
                disabled=true
            )
            setLimitsMax(
                '#show-users-limits-' + id,
                kind='user',
                id=id,
                disabled=true
            )
            tr.addClass('shown');
        }
    });

    $("#modalEditUser #send").on('click', function(e){
        var form = $('#modalEditUserForm');
        disabled = $('#modalEditUserForm').find(':input:disabled').removeAttr('disabled');
        formdata = form.serializeObject();
        disabled.attr('disabled', 'disabled');
        form.parsley().validate();
        if (form.parsley().isValid()){
            data=userQuota2dict(formdata);
            delete data['unlimited']
            var notice = new PNotify({
                text: 'Updating user...',
                hide: true,
                opacity: 1,
                icon: 'fa fa-spinner fa-pulse'
            })
            $.ajax({
                type: "PUT",
                url:"/api/v3/admin/user/" + data['id'],
                data: JSON.stringify(data),
                contentType: "application/json",
                error: function(data) {
                    notice.update({
                        title: 'ERROR updating user',
                        text: data.responseJSON.description,
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 5000,
                        opacity: 1
                    })
                },
                success: function(data)
                {
                    $('form').each(function() { this.reset() });
                    $('.modal').modal('hide');
                    notice.update({
                        title: 'Updated',
                        text: 'User updated successfully',
                        hide: true,
                        delay: 2000,
                        icon: 'fa fa-' + data.icon,
                        opacity: 1,
                        type: 'success'
                    })
                }
            });     
        }
    });
});

function initUsersSockets () {
    socket.on('connect', function() {
        connection_done();
        console.log('Listening users namespace');
    });

    socket.on('connect_error', function(data) {
      connection_lost();
    });

    socket.on('users_data', function(data) {
        var data = JSON.parse(data);
        data = {...users_table.row("#"+data.id).data(),...data}
        dtUpdateInsert(users_table,data,false);
        users_table.draw(false)
    });

    socket.on('users_delete', function(data) {
        var data = JSON.parse(data);
        users_table.row('#'+data.id).remove().draw();
    });

    socket.on('add_form_result', function (data) {
        var data = JSON.parse(data);
        $('form').each(function() { this.reset() });
        $('.modal').modal('hide');
        $('#modalAddBulkUsers #send').prop('disabled', false);
        new PNotify({
            title: data.title,
            text: data.text,
            hide: true,
            delay: 4000,
            icon: 'fa fa-'+data.icon,
            opacity: 1,
            type: data.type
        });
        users_table.ajax.reload()
    });

    socket.on ('result', function (data) {
        var data = JSON.parse(data);
        new PNotify({
                title: data.title,
                text: data.text,
                hide: true,
                delay: 4000,
                icon: 'fa fa-'+data.icon,
                opacity: 1,
                type: data.type
        });
        users_table.ajax.reload()
    });
}

function actionsUserDetail(){
	$('.btn-edit').on('click', function () {
        var pk=$(this).closest("div").attr("data-pk");
        $("#modalEditUserForm")[0].reset();
        $("#modalEditUserForm #secondary_groups").empty().trigger('change')
        $('#modalEditUserForm .apply').html('group quota');
        $('#modalEditUser').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        
        $('#modalEditUserForm #secondary_groups').select2({
            minimumInputLength: 2,
            multiple: true,
            ajax: {
                type: "POST",
                url: '/api/v3/admin/allowed/term/groups/',
                dataType: 'json',
                contentType: "application/json",
                delay: 250,
                data: function (params) {
                    return  JSON.stringify({
                        term: params.term,
                        category: current_category,
                    });
                },
                processResults: function (data) {
                    return {
                        results: $.map(data, function (item, i) {
                            return {
                                text: item.name + ' [' + item.category_name + ']',
                                id: item.id
                            }
                        })
                    };
                }
            },
        });
        setModalUser();
        $.ajax({
            type: "POST",
            url: '/api/v3/admin/table/users',
            data: JSON.stringify({'id':pk}),
            contentType: "application/json",
            accept: "application/json",
            async: false
        }).done(function(user) {
            $('#modalEditUserForm #name').val(user.name);
            $('#modalEditUserForm #id').val(user.id);
            $('#modalEditUserForm #uid').val(user.uid);
            $('#modalEditUserForm #email').val(user.email);
            $('#modalEditUserForm #role option:selected').prop("selected", false);
            $('#modalEditUserForm #role option[value="'+user.role+'"]').prop("selected",true);
            $('#modalEditUserForm #category option:selected').prop("selected", false);
            $('#modalEditUserForm #category option[value="'+user.category+'"]').prop("selected",true);
            $('#modalEditUserForm #group option:selected').prop("selected", false);
            $('#modalEditUserForm #group option[value="'+user.group+'"]').prop("selected",true);
            $('#modalEditUserForm').parsley().validate();
            $.each(user.secondary_groups, function(i, group) {
                var newOption = new Option(group, group, true, true);
                $("#modalEditUserForm #secondary_groups").append(newOption).trigger('change');
            })
        });
        setQuotaMax('#edit-users-quota',kind='user',id=pk,disabled=false);
	});
}

function renderUsersDetailPannel ( d ) {
    if(d.username == 'admin'){
        $('.template-detail-users .btn-delete').hide()
    }else{
        $('.template-detail-users .btn-delete').show()
    }

    $newPanel = $template.clone();
    $newPanel.html(function(i, oldHtml){
        var secondary_groups_names = []
        $.each(d.secondary_groups_data, function(i, group) {
            secondary_groups_names.push(group.name)
        })
        return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name).replace(/d.username/g, d.username).replace(/d.secondary_groups/g, secondary_groups_names);
    });
    return $newPanel
}

function setModalUser(){
    $.ajax({
        type: "GET",
        url:"/api/v3/admin/userschema",
        async: false,
        success: function (d) {
            $.each(d, function (key, value) {
                $("." + key).find('option').remove().end();
                for(var i in d[key]){
                    if (key == 'group') {
                        $("."+key).append('<option value=' + value[i].id + ' parent-category=' + value[i].parent_category + '>' + value[i].name + '</option>');
                    } else {
                        $("."+key).append('<option value=' + value[i].id + '>' + value[i].name + '</option>');
                    }
                }
            });
            $('#add-category').trigger("change")
            $('#bulk-category').trigger("change")
            current_category = ($('#add-category').val())
        }
    });
}