/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$(document).ready(function() {
    $template_group = $(".template-detail-groups");
    var groups_table=$('#groups').DataTable( {
        "initComplete": function(settings, json) {
            waitDefined('socket', initGroupSockets)
            let searchGroupId = getUrlParam('searchGroup');
            if (searchGroupId) {
                this.api().column([1]).search("(^" + searchGroupId + "$)", true, false).draw();
                window.location.hash = '#groups'
                $('#groups .xe-name input').val(searchGroupId)
            }
        },
        "ajax": {
            "url": "/admin/users/quotas_limits/groups",
            "dataSrc": "",
            "type" : "GET",
            "data": function(d){return JSON.stringify({})}
        },
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "columns": [
            {
                "className": 'details-show',
                "orderable": false,
                "data": null,
                "width": "10px",
                "defaultContent": '<button class="btn btn-xs btn-info" type="button" data-placement="top" ><i class="fa fa-plus"></i></button>'
            },
            { "data": "name", className: "xe-name" },
            { "data": "parent_category_name", className: "xe-category" },
            { "data": "description", className: "xe-description" },
            { "data": "limits.users", className: "xe-description", defaultContent: "-" },
            { "data": "domains_size", className: "xe-desktops", defaultContent: "-"},
            { "data": "media_size", className: "xe-desktops", defaultContent: "-"},
            { "data": null, className: "xe-desktops", defaultContent: "-"},
            { "data": "quota.total_size", className: "xe-desktops", defaultContent: "-"},
            { "data": "limits.total_size", className: "xe-desktops", defaultContent: "-"},
            { "data": "quota.desktops", className: "xe-desktops", defaultContent: "-"},
            { "data": "limits.desktops", className: "xe-desktops", defaultContent: "-"},
            { "data": "quota.volatile", className: "xe-desktops", defaultContent: "-"},
            { "data": "limits.volatile", className: "xe-desktops", defaultContent: "-"},
            { "data": "quota.running", className: "xe-running", defaultContent: "-"},
            { "data": "limits.running", className: "xe-running", defaultContent: "-"},
            { "data": "quota.vcpus", className: "xe-vcpu", defaultContent: "-"},
            { "data": "limits.vcpus", className: "xe-vcpu", defaultContent: "-"},
            { "data": "quota.memory", className: "xe-memory", defaultContent: "-"},
            { "data": "limits.memory", className: "xe-memory", defaultContent: "-"},
            { "data": "quota.templates", className: "xe-templates", defaultContent: "-"},
            { "data": "limits.templates", className: "xe-templates", defaultContent: "-"},
            { "data": "quota.isos", className: "xe-isos", defaultContent: "-"},
            { "data": "limits.isos", className: "xe-isos", defaultContent: "-"},
            { "data": "quota.deployments_total", className: "xe-deployments", defaultContent: "-"},
            { "data": "limits.deployments_total", className: "xe-deployments", defaultContent: "-"},
            { "data": "quota.deployment_desktops", className: "xe-deployments", defaultContent: "-"},
            { "data": "limits.deployment_desktops", className: "xe-deployments", defaultContent: "-"},
            { "data": "id", "visible": false}
        ],
        "columnDefs": [
            {
                "targets": 1,
                "render": function ( data, type, full, meta ) {
                    return '<a href="/isard-admin/admin/users/Management?searchGroup='+ full.name +'">'+ full.name +'</a>'
                }
            },
            {
                "targets": 2,
                "render": function ( data, type, full, meta ) {
                    return full.parent_category_name ? full.parent_category_name : ''
                }
            },
            {
                "targets": 5,
                "render": function ( data, type, full, meta ) {
                    return full.domains_size.toFixed(1);
                }
            },
            {
                "targets": 6,
                "render": function ( data, type, full, meta ) {
                    return full.media_size.toFixed(1);
                }
            },
            {
                "targets": 7,
                "render": function ( data, type, full, meta ) {
                    return (full.domains_size + full.media_size).toFixed(1);
                }
            }
        ], 
        footerCallback: function (row, data, start, end, display) {
            var api = this.api();

            // Total over this page
            pageTotal = api
                .column(7, {search: 'applied'})
                .data()
                .reduce(function (a, b) {
                    return a + b['domains_size'] + b['media_size']
                }, 0);

            // Update footer
            $('.groups-total-size').html('Applied filter total storage size: ' + pageTotal.toFixed(1) + ' GB');
        },
    } );

    adminShowIdCol(groups_table)

    // Hide 'Category' group list column when manager
    if ($('meta[id=user_data]').attr('data-role') == 'manager') {
        var column = groups_table.column(2);
        column.visible(!column.visible());
    }

    // Setup - add a text input to each footer cell
    $('#groups tfoot tr:first th').each( function () {
        var title = $(this).text();
        if (['','Limits','Domains', 'Media', 'Total used', 'Quota'].indexOf(title) == -1){
            $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
        }
    } );

    // Apply the search
    groups_table.columns().every( function () {
        var that = this;

        $( 'input', this.footer() ).on( 'keyup change', function () {
            if ( that.search() !== this.value ) {
                that
                .search( this.value )
                .draw();
            }
        } );
    } );

    $('#groups').find('tbody').on('click', 'td.details-show', function () {
        var tr = $(this).closest('tr');
        var row = groups_table.row( tr );

        if ( row.child.isShown() ) {
            // This row is already open - close it
            row.child.hide();
            tr.removeClass('shown');
        }
        else {
            if ( groups_table.row( '.shown' ).length ) {
                $('.details-show', groups_table.row( '.shown' ).node()).click();
            }
            row.child( renderGroupsDetailPannel(row.data()) ).show();
            actionsGroupDetail()
            tr.addClass('shown');
        }
    });

    function initGroupSockets() {
        socket.on('groups_data', function (data) {
            groups_table.ajax.reload()
        });

        socket.on('groups_delete', function (data) {
            groups_table.ajax.reload()
        });
    }

});


function actionsGroupDetail(){
    $('.btn-edit-group-quotas').off('click').on('click', function () {
        var pk=$(this).closest("div").attr("data-pk");
        $("#modalEditQuotaForm")[0].reset();
        $("#modalEditQuotaForm #propagate").removeAttr('checked').iCheck('update')
        $('#modalEditQuotaForm #id').val(pk);
        $('#modalEditQuota .kind').html('group');
        $('#modalEditQuota .apply').html('category quota');
        setModalUser();
        $('#modalEditQuotaForm #add-role').append('<option selected="selected" value=all_roles> All roles</option>')
        $('#modalEditQuotaForm #add-role').val('all_roles')
        $('#modalEditQuotaForm #add-role').trigger("change")
        $('#modalEditQuota').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        setQuotaMax('#modalEditQuotaForm',kind='group',id=pk,disabled=false);
	});

    $("#modalEditQuota #send").off('click').on('click', function(e){
        form = $('#modalEditQuotaForm')
        pk=$('#modalEditQuotaForm #id').val();
        form.parsley().validate();
        formdata=form.serializeObject()
        if (form.parsley().isValid() || 'unlimited' in formdata){
            if('unlimited' in formdata){
                dataform={}
                dataform['quota']=false
            }else{
                dataform=quota2dict(formdata)
            }
            data={}
            data['quota']=dataform['quota']
            if('propagate' in formdata){
                data['propagate']=true;
            }
            data['role']=formdata['role']
            var notice = new PNotify({
                text: 'Updating quota...',
                hide: false,
                opacity: 1,
                icon: 'fa fa-spinner fa-pulse'
            })
            $.ajax({
                type: "PUT",
                url:"/api/v3/admin/quota/group/"+pk ,
                data: JSON.stringify(data),
                contentType: "application/json",
                success: function(data)
                {
                    $('form').each(function() { this.reset() });
                    $('.modal').modal('hide');
                    notice.update({
                        title: 'Updated',
                        text: 'Quotas updated successfully',
                        hide: true,
                        delay: 1000,
                        icon: 'fa fa-' + data.icon,
                        opacity: 1,
                        type: 'success'
                    })
                },
                error: function(data) {
                    notice.update({
                        title: 'ERROR updating quota',
                        text: data.responseJSON.description,
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 5000,
                        opacity: 1
                    })
                },
            });
        }
    });

    $('.btn-edit-limits').off('click').on('click', function () {
        var pk=$(this).closest("div").attr("data-pk");
        $("#modalEditLimitsForm")[0].reset();
        $('#modalEditLimitsForm #id').val(pk);
        $('#modalEditLimits .apply').html('category limits');
        $('#modalEditLimits').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        setLimitsMax('#modalEditLimitsForm',kind='group',id=pk,disabled=false);
        $('#modalEditLimitsForm #propagate-form').css("display", "none");
    });

    $("#modalEditLimits #send").off('click').on('click', function(e){
        form = $('#modalEditLimitsForm')
        pk=$('#modalEditLimitsForm #id').val();

        form.parsley().validate();
        formdata=form.serializeObject();
        if (form.parsley().isValid() || 'unlimited' in formdata){
            if('unlimited' in formdata){
                dataform={}
                dataform['limits']=false
            }else{
                dataform=quota2dict(form.serializeObject())
            }
            data={}
            data['limits']=dataform['limits']
            var notice = new PNotify({
                text: 'Updating limits...',
                hide: false,
                opacity: 1,
                icon: 'fa fa-spinner fa-pulse'
            })
            $.ajax({
                type: "PUT",
                url:"/api/v3/admin/limits/group/"+pk ,
                data: JSON.stringify(data),
                contentType: "application/json",
                success: function(data)
                {
                    $('form').each(function() { this.reset() });
                    $('.modal').modal('hide');
                    notice.update({
                        title: 'Updated',
                        text: 'Limits updated successfully',
                        hide: true,
                        delay: 1000,
                        icon: 'fa fa-' + data.icon,
                        opacity: 1,
                        type: 'success'
                    })
                },
                error: function(data) {
                    notice.update({
                        title: 'ERROR updating limits',
                        text: data.responseJSON.description,
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 2000,
                        opacity: 1
                    })
                },
            });
        }
    });

}

function renderGroupsDetailPannel ( d ) {
    $newPanel = $template_group.clone();
    $newPanel.html(function(i, oldHtml){
        var linked_groups_names = []
            $.each(d.linked_groups_data, function(i, group) {
                linked_groups_names.push(group.name)
            })
        return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name).replace(/d.description/g, d.description).replace(/d.linked_groups/g, linked_groups_names);
    });
    return $newPanel
}

$('#modalEditQuotaForm #add-role').on('change', function() {
    role = ($(this).val())
    if (role=="all_roles"){
        $('#propagate-form').css("display", "block");
    } else {
        $('#propagate-form').css("display", "none");
    }
})
