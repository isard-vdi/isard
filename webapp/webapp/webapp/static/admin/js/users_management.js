/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

var users_table= ''
var current_category = ''

$(document).ready(function() {
    $('.collapsed').find('.x_content').css('display', 'none');
    $('.collapse-link ').find('i').toggleClass('fa-chevron-up fa-chevron-down');
    $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on)
})
function socketio_on(){
    $template = $(".template-detail-users");

	$('.btn-new-user').on('click', function () {
        setQuotaMax('#users-quota',kind='category',id=false,disabled=false);
        $('#modalAddUser .apply').html('group quota');
        $('#modalAddUser').modal({backdrop: 'static', keyboard: false}).modal('show');
        $('#modalAddUserForm')[0].reset();

        $('#modalAddUserForm #secondary_groups').select2({
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
                                text: item.name + " [" + item.category_name + "]",
                                id: item.id
                            }
                        })
                    };
                }
            },
        });

        setModalUser();
	});

    $('.btn-update-from-csv').on('click', function () {
        var modal = '#modalUpdateFromCSV';
        $(modal + "Form")[0].reset();
        $(modal + " #csv_correct").hide();
        $(modal + " #csv_error").hide();
        $(modal).modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
    });

    $("#modalUpdateFromCSV #send").on('click', function(e) {
        var data = {};
        data['users'] = csv_preview.data().toArray()
        data['bulk'] = true;
        data['csv'] = true;
        $.each(data['users'], function(index, user) {
            if (user.secondary_groups
                && user.secondary_groups.length === 1
                && user.secondary_groups[0] === "") {
              delete user.secondary_groups;
            }
            user.category = user.category_id
            delete user.category_id
            
            user.group = user.group_id
            delete user.group_id
        });

        $.ajax({
            type: 'PUT',
            url: '/api/v3/admin/users/csv',
            data: JSON.stringify(data),
            contentType: 'application/json',
            success: function (xhr) {
                $('form').each(function () {
                    this.reset()
                })
                $('.modal').modal('hide')
                new PNotify({
                    title: 'Updated',
                    text: data.users.length + ' user(s) updated successfully',
                    hide: true,
                    icon: 'fa fa-success',
                    delay: 4000,
                    opacity: 1,
                    type: 'success'
                })
            },
            error: function (xhr) {
                new PNotify({
                    title: 'ERROR updating multiple users',
                    text: xhr.responseJSON.description,
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 5000,
                    opacity: 1
                })
            }
        });
    });

	$('.btn-new-bulkusers').on('click', function () {
        $("#csv_error").hide()
        $('#bulk-allow-update').iCheck('uncheck').iCheck('update');
        setQuotaMax('#bulkusers-quota',kind='category',id=false,disabled=false);
        $('#modalAddBulkUsers .apply').html('group quota');
        $("#modalAddBulkUsers #send").attr("disabled", true);
        $('#modalAddBulkUsers').modal({backdrop: 'static', keyboard: false}).modal('show');
        $('#modalAddBulkUsersForm')[0].reset();
        if ( $.fn.dataTable.isDataTable( '#csv_preview' ) ) {
            csv_preview.clear().draw()
            $("#csv_correct").hide()
            $("#csv_error").hide()
        }
        setModalUser();

        $('#modalAddBulkUsersForm #bulk_secondary_groups').select2({
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
                                text: item.name + " [" + item.category_name + "]",
                                id: item.id
                            }
                        })
                    };
                }
            },
        });
	});

    $('.btn-bulk-edit-users').on('click', function () {
        let usersToEdit = getSelectedUserList();
        if (usersToEdit.length != 0) {
            var modal = '#modalBulkEditUser';
            $(modal + "Form")[0].reset();
            $(modal + " .alert").empty();
            $(modal + " .alert").hide();
            $(modal + "Form #active").empty();
            $(modal + 'Form #id').val(JSON.stringify(usersToEdit));
            $(modal).modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');
            $(modal + ' #users-list').empty();
            render_users_to_edit_table(usersToEdit);
            $(modal + " #active").append(`<option value="true">True</option><option value="false">False</option>`);

            $(modal + ' :checkbox').iCheck('uncheck').iCheck('update');
            $(modal + ' :radio').iCheck('uncheck').iCheck('update');
            $(modal + ' #active').iCheck('check').iCheck('update');
            $(modal + ' #overwrite-secondary-group-checkbox').iCheck('check').iCheck('update');

            $(modal + ' #secondary_groups').select2({
                minimumInputLength: 2,
                multiple: true,
                ajax: {
                    type: "POST",
                    url: '/api/v3/admin/allowed/term/groups/',
                    dataType: 'json',
                    contentType: "application/json",
                    delay: 250,
                    data: function (params) {
                        return JSON.stringify({
                            term: params.term,
                            category: current_category,
                        });
                    },
                    processResults: function (data) {
                        return {
                            results: $.map(data, function (item, i) {
                                return {
                                    text: item.name + " [" + item.category_name + "]",
                                    id: item.id
                                }
                            })
                        };
                    }
                },
            });

            showAndHideByCheckbox($(modal + " #edit-secondary-group-checkbox"), $(modal + " #secondary-groups-panel"));
            showAndHideByCheckbox($(modal + " #edit-active-inactive-checkbox"), $(modal + " #active-inactive-panel"));

            var ids = [];
            $.each(usersToEdit, function (key, value) {
                ids.push(value.id);
            })
            $(modal + ' #ids').val(ids.join(','));

            $(modal + ' #secondary_groups option:first').remove();
        } else {
            new PNotify({
                title: 'Please select at least one user',
                hide: true,
                icon: 'fa fa-warning',
                type: 'info',
                delay: 4000,
                opacity: 1,
            })
        }
    });


    $("#modalBulkEditUser #send").on('click', function (e) {
        var form = $('#modalBulkEditUserForm');
        var formdata = form.serializeObject();
        form.parsley().validate();
        var data = formdata;
        var update_data = {};
        var hideModal = true;

        if (form.parsley().isValid()) {
            data['ids'] = update_data['ids'] = data['ids'].split(',');

            if (data["edit-active-inactive"] === 'on') {
                update_data['active'] = (data['active'] === 'on');
            }

            if (['active'] in update_data) {
                $.ajax({
                    type: 'PUT',
                    url: '/api/v3/admin/users/bulk',
                    data: JSON.stringify(update_data),
                    contentType: 'application/json',
                    async: false,
                    success: function () {
                        showAlert(form.find("#general-alert"), "Updated successfully", "success");
                    },
                    error: function (data) {
                        hideModal = false;
                        showAlert(form.find("#general-alert"), data.responseJSON.description, "error");
                    }
                });
            }

            if (data["edit-secondary-group"] === 'on') {
                $.ajax({
                    type: 'PUT',
                    url: `/api/v3/admin/user/secondary-groups/${data['action-secondary-group']}`,
                    data: JSON.stringify({
                        "secondary_groups": data['secondary_groups'] ? data['secondary_groups'] : [],
                        "ids": data['ids']
                    }),
                    async: false,
                    contentType: 'application/json',
                    success: function () {
                        showAlert(form.find(".edit-secondary-groups .alert"), "Updated successfully", "success");
                    },
                    error: function (data) {
                        hideModal = false;
                        showAlert(form.find(".edit-secondary-groups .alert"), data.responseJSON.description, "error");
                    }
                })
            }

            if (hideModal) {
                $('.modal').modal('hide');
                if (data["edit-active-inactive"] === 'on' || data["edit-secondary-group"] === 'on') {
                    new PNotify({
                        title: 'Updated',
                        text: data['ids'].length + ' user(s) updated successfully',
                        hide: true,
                        icon: 'fa fa-success',
                        delay: 4000,
                        opacity: 1,
                        type: 'success'
                    });
                }
            };
        }
    });


    $('.btn-bulkdelete').on('click', function () {
        let usersToDelete = getSelectedUserList().map(({id})=>id);
        if (usersToDelete.includes("local-default-admin-admin")) {
            new PNotify({
                text: "Can not delete default admin",
                hide: true,
                opacity: 1,
                delay: 1000
            });
        } else if (usersToDelete.includes(($('meta[id=user_data]').attr('data-userid')))) {
            new PNotify({
                text: "Can not delete your own user",
                hide: true,
                opacity: 1,
                delay: 1000
            });
        } else if (!(usersToDelete.length == 0)) {
            $("#modalDeleteUserForm")[0].reset();
            $('#modalDeleteUserForm :radio').iCheck('uncheck').iCheck('update');
            $('#modalDeleteUserForm #id').val(usersToDelete.join(','));
            $('#modalDeleteUser').modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');
            showLoadingData('#table_modal_delete_desktops')
            showLoadingData('#table_modal_delete_templates')
            showLoadingData('#table_modal_delete_deployments')
            showLoadingData('#table_modal_delete_media')
            showLoadingData('#table_modal_delete_users')
            $('#modalDeleteUser #send').prop('disabled', true);
            $.ajax({
                type: "POST",
                url: "/api/v3/admin/user/delete/check",
                data: JSON.stringify({"ids": usersToDelete}),
                contentType: "application/json"
            }).done(function (items) {
                $('#modalDeleteUser #send').prop('disabled', false)
                populateDeleteModalTable(items.desktops, $('#table_modal_delete_desktops'));
                populateDeleteModalTable(items.templates, $('#table_modal_delete_templates'));
                populateDeleteModalTable(items.deployments, $('#table_modal_delete_deployments'));
                populateDeleteModalTable(items.media, $('#table_modal_delete_media'));
                populateDeleteModalTable(items.users, $('#table_modal_delete_users'));
            });
        } else {
            new PNotify({
                text: "Please select the users you want to delete",
                hide: true,
                opacity: 1,
                delay: 1000
            });
        }
    });

    $('.btn-download-bulkusers').on('click', function () {
        var kind = $(this)[0].id;
        var viewerFile;

        if (kind === 'download-edit') {
            viewerFile = new Blob(
                [`active,name,provider,category,uid,group,secondary_groups,password\ntrue,John Doe,local,Default,jdoe,Default,Default,cS227@tB\n,Another User,local,Default,auser,Default,`
                ], { type: "text/csv" });

        } else if (kind === 'download-create') {
            viewerFile = new Blob(
                [`username,name,email,password,group,category,role\njdoe,John Doe,jdoe@isardvdi.com,7j5*0Z/g,Default,Default,advanced\nauser,Another User,auser@domain.com,kE1)n4E1,Default,Default,user`
                ], { type: "text/csv" });
        }
        var a = document.createElement('a');
            a.download = 'bulk-users-template.csv';
            a.href = window.URL.createObjectURL(viewerFile);
        var ev = document.createEvent("MouseEvents");
            ev.initMouseEvent("click", true, false, self, 0, 0, 0, 0, 0, false, false, false, false, 0, null);
            a.dispatchEvent(ev);
	});

    function filter_groups(category_select, group_select) {
        // Hide all options
        group_select.find('option').attr("hidden","hidden")
        // Show groups from the selected category
        group_select.find('option[parent-category='+ category_select.val() + ']').removeAttr('hidden')
        // Select the first group option from the category
        let group = group_select.find('option:not(option[hidden="hidden"])').first().val()
        group_select.val(group)
    }

    $("#add-category").on('change', function () {
        current_category = ($(this).val())
        filter_groups($(this), $('#add-group'))
        $("#secondary_groups").empty().trigger('change')
    })
    $("#bulk-category").on('change', function () {
        current_category = ($(this).val())
        filter_groups($(this), $('#bulk-group'))
        $("#secondary_groups").empty().trigger('change')
    })

    $("#modalAddUser #send").on('click', function(e){
        var form = $('#modalAddUserForm');
        formdata = form.serializeObject()
        form.parsley().validate();
        if (form.parsley().isValid()){   // || 'unlimited' in formdata){
            data=formdata;
            data['password']=data['password-add-user'];
            delete data['password-add-user'];
            delete data['password2-add-user'];
            delete data['unlimited'];
            delete data['id'];
            data['provider']='local';
            data['bulk']=false;
            data['username']=$('#modalAddUserForm #id').val();
            var notice = new PNotify({
                text: 'Creating user...',
                hide: true,
                opacity: 1,
                icon: 'fa fa-spinner fa-pulse'
            })
            $.ajax({
                type: "POST",
                url:"/api/v3/admin/user" ,
                data: JSON.stringify(data),
                contentType: "application/json",
                error: function (data) {
                    notice.update({
                        title: "ERROR creating user",
                        text: data.responseJSON.description,
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 15000,
                        opacity: 1
                    });
                },
                success: function(data)
                {
                    $('form').each(function() { this.reset() });
                    $('.modal').modal('hide');
                    notice.update({
                        title: "Created",
                        text: 'User created successfully',
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

    $("#modalEditUser #send").on('click', function(e){
        var form = $('#modalEditUserForm');
        disabled = $('#modalEditUserForm').find(':input:disabled').removeAttr('disabled');
        formdata = form.serializeObject();
        disabled.attr('disabled', 'disabled');
        form.parsley().validate();
        if (form.parsley().isValid()){
            data=formdata;
            data['secondary_groups'] = data['secondary_groups'] || [];
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

    $("#modalPasswdUser #send").on('click', function(e){
        var form = $('#modalPasswdUserForm');
        form.parsley().validate();
        if (form.parsley().isValid()){
            data={}
            data['id']=$('#modalPasswdUserForm #id').val();
            data['name']=$('#modalPasswdUserForm #name').val();
            data['password']=$('#modalPasswdUserForm #password-reset').val();
            $('#passwd-error').empty();
            $.ajax({
                type: "PUT",
                url:"/api/v3/admin/user/" + data['id'],
                data: JSON.stringify(data),
                contentType: "application/json",
                success: function(data)
                {
                    $('#passwd-error').hide();
                    $('form').each(function() { this.reset() });
                    $('.modal').modal('hide');
                },
                error: function(data) {
                    $('#passwd-error').show();
                    const msg = data.responseJSON ? data.responseJSON.description : 'Something went wrong';
                    $('#passwd-error').html(msg);
                }
            });
        }
    });

    $('#modalDeleteUser #send').on('click', function (e) {
        var form = $('#modalDeleteUserForm');
        form.parsley().validate();
        if (form.parsley().isValid()) {
            var formData = form.serializeObject()
            user = $('#modalDeleteUserForm #id').val().split(',');
            var notice = new PNotify({
                text: 'Deleting user(s)...',
                hide: false,
                opacity: 1,
                icon: 'fa fa-spinner fa-pulse'
            })

            $.ajax({
                type: 'DELETE',
                url: '/api/v3/admin/user',
                data: JSON.stringify({ 'user': user, 'delete_user': formData['delete-user'] == 'true' }),
                contentType: 'application/json',
                error: function (data) {
                    notice.update({
                        title: 'ERROR deleting user(s)',
                        text: data.responseJSON && data.responseJSON.description ? data.responseJSON.description : 'Something went wrong.',
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 5000,
                        opacity: 1
                    })
                },
                success: function (data) {
                    $('form').each(function () {
                        this.reset()
                    })
                    $('.modal').modal('hide')
                    notice.update({
                        title: 'Deleted',
                        text: 'User(s) deleted successfully',
                        hide: true,
                        delay: 2000,
                        icon: '',
                        opacity: 1,
                        type: 'success'
                    })
                }
            })
        };
    });

    document.getElementById('csv').addEventListener('change', readFile, false);
    var filecontents=''
    function readFile(evt) {
        var files = evt.target.files;
        var file = files[0];
        var fileExtension = file.name.split('.').pop().toLowerCase();
        if (fileExtension!=="csv" || (file.type !== 'text/csv' && file.type !== 'application/vnd.ms-excel')) {
            new PNotify({
                title: 'ERROR uploading file',
                text: 'File must be a CSV file',
                type: 'error',
                hide: true,
                icon: 'fa fa-warning',
                delay: 5000,
                opacity: 1
            });
        } else if (file.size > 25000) { //25kB
            new PNotify({
                title: 'ERROR uploading CSV',
                text: 'File size must be less than 25kB',
                type: 'error',
                hide: true,
                icon: 'fa fa-warning',
                delay: 5000,
                opacity: 1
            });
        } else {
            var reader = new FileReader();
            var modal = '#modalAddBulkUsers';
            reader.onload = function (event) {
                filecontents = event.target.result;
                csv2datatables(filecontents, modal)
            }
            reader.readAsText(file, 'UTF-8')
        }
    }

    document.getElementById('csv-edit').addEventListener('change', readFileEdit, false);
    var filecontents = ''
    function readFileEdit(evt) {
        var files = evt.target.files;
        var file = files[0];
        var fileExtension = file.name.split('.').pop().toLowerCase();
        if (fileExtension!=="csv" || (file.type !== 'text/csv' && file.type !== 'application/vnd.ms-excel')) {
            new PNotify({
                title: 'ERROR uploading file',
                text: 'File must be a CSV file',
                type: 'error',
                hide: true,
                icon: 'fa fa-warning',
                delay: 5000,
                opacity: 1
            });
        } else if (file.size > 25000) { //25kB
            new PNotify({
                title: 'ERROR uploading CSV',
                text: 'File size must be less than 25kB',
                type: 'error',
                hide: true,
                icon: 'fa fa-warning',
                delay: 5000,
                opacity: 1
            });
        } else {
            var reader = new FileReader();
            var modal = '#modalUpdateFromCSV';
            reader.onload = function (event) {
                filecontents = event.target.result;
                csv2datatables(filecontents, modal)
            }
            reader.readAsText(file, 'UTF-8')
        }
    }

    $("#modalAddBulkUsers #send").on('click', function(e){
        var form = $('#modalAddBulkUsersForm');
        $("#modalAddBulkUserForm #bulk_secondary_groups").empty().trigger('change')
        formdata = form.serializeObject()
        form.parsley().validate();
        if (form.parsley().isValid()){
            data=formdata;
            delete data['unlimited']
            data['provider']='local';
            users=csv_preview.data().toArray()
            var notice = new PNotify({
                title: "Adding users",
            });
            var usersAdded = 1;
            users.forEach(function (user) {
                data['uid'] = user['username'];
                user['bulk'] = true
                if(user["exists"] && !$('#bulk-allow-update').prop("checked")){
                    notice.update({
                        title: "Adding users",
                        text: "Skipping user "+user["username"]+" as already exists",
                        hide: true,
                        delay: 4000,
                        opacity: 1
                    });
                    return true
                }

                if(user["exists"] && $('#bulk-allow-update').prop("checked")){
                    user['secondary_groups'] = data['secondary_groups']
                    user['quota'] = data['quota']
                    $.ajax({
                        type: 'POST',
                        url: "/api/v3/admin/users/check/by/provider",
                        data: JSON.stringify({
                            "provider":data['provider'],
                            "category":user['category'],
                            "uid":user['username']
                        }),
                        contentType: "application/json",
                        success: function(data){
                            $.ajax({
                                type: 'PUT',
                                url: "/api/v3/admin/user/"+data,
                                data: JSON.stringify(user) ,
                                contentType: "application/json",
                                success: function(data)
                                {
                                    $('form').each(function() { this.reset() });
                                    $('.modal').modal('hide');
                                notice.update({
                                        title: "Updating",
                                        text: "Updating user (" + ( usersAdded ) + "/" + users.length + "): ",
                                        hide: true,
                                        delay: 4000,
                                        opacity: 1
                                    });
                                usersAdded ++;
                                 },
                                 error: function(data){
                                    new PNotify({
                                        title: "ERROR updating user",
                                        text: data.responseJSON.description,
                                        type: 'error',
                                        hide: true,
                                        icon: 'fa fa-warning',
                                        delay: 15000,
                                        opacity: 1
                                    });
                                 }
                            });
                        }
                    })
                }else{
                    delete user["exists"]
                    $.ajax({
                        type: 'POST',
                        url: "/api/v3/admin/user",
                        data: JSON.stringify(Object.assign({},data,user)) ,
                        contentType: "application/json",
                        success: function(data)
                        {
                            $('form').each(function() { this.reset() });
                            $('.modal').modal('hide');
                        notice.update({
                                title: "Adding users",
                                text: "Added user (" + ( usersAdded ) + "/" + users.length + "): ",
                                hide: true,
                                delay: 4000,
                                opacity: 1
                            });
                        usersAdded ++;
                        },
                        error: function(data){
                            new PNotify({
                                title: "ERROR adding user",
                                text: data.responseJSON.description,
                                type: 'error',
                                hide: true,
                                icon: 'fa fa-warning',
                                delay: 15000,
                                opacity: 1
                            });
                        }
                    });
                }
            });
        }
    });

    $("#add-category").on('change', function(e){
        setQuotaMax('#users-quota',kind='category',id=$(this).val(),disabled=false);
    });
    $("#add-group").on('change', function(e){
        setQuotaMax('#users-quota',kind='group',id=$(this).val(),disabled=false);
    });

    $("#bulk-category").on('change', function(e){
        setQuotaMax('#bulkusers-quota',kind='category',id=$(this).val(),disabled=false);
    });
    $("#bulk-group").on('change', function(e){
        setQuotaMax('#bulkusers-quota',kind='group',id=$(this).val(),disabled=false);
    });

    users_table=$('#users').DataTable( {
        "initComplete": function(settings, json) {
            initUsersSockets()
            let searchUserId = getUrlParam('searchUser');
            if (searchUserId) {
                this.api().column([6]).search("(^" + searchUserId + "$)", true, false).draw();
                $('#users .xe-username input').val(searchUserId)
            }
        },
        "ajax": {
            "url": "/admin/users/management/users",
            "dataSrc": "",
            "type" : "GET",
            "data": function(d){return JSON.stringify({})}
        },
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "rowId": "id",
        "deferRender": true,
        "createdRow": (row, data, index) => {
            if ($('thead #select-all').prop('checked')) {
                $(row).find('.select-checkbox input[type="checkbox"]').prop('checked', true)
                $(row).addClass('active');
            }
        },
        "columns": [
            {
                "className": 'details-control',
                "orderable": false,
                "data": null,
                "width": "10px",
                "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
            },
            {
                "data": "active", "width": "10px", "render": function (data, type, full, meta) {
                    if (type === "display") {
                        if (full.active == true) {
                            return '<i class="fa fa-check" style="color:lightgreen"></i>';
                        } else {
                            return '<i class="fa fa-close" style="color:darkgray"></i>';
                        }
                    }
                    return data;
                }
            },
            { "data": "name" },
            { "data": "provider", "width": "10px", },
            {
                "data": "category_name", "render": function (data, type, full, meta) {
                    return full.category_name ? full.category_name : ''
                }
            },
            { "data": "uid" },
            {
                "data": "username", className: "xe-username", "render": function (data, type, full, meta) {
                    return '<a href="/isard-admin/admin/users/QuotasLimits?searchUser=' + full.username + '">' + full.username + '</a>'
                }
            },
            { "data": "role_name", "width": "10px" },
            { "data": "group_name", "width": "10px" },
            {
                "data": "secondary_groups", "width": "100px", "render": function (data, type, full, meta) {
                    var secondary_groups = full.secondary_groups_names.join(",");
                    if (secondary_groups.length > 50) {
                        return `<p title="${secondary_groups}">${secondary_groups.substring(0, 50)}...</p>`
                    } else {
                        return full.secondary_groups_names
                    }
                }
            },
            {
                "data": "email_verified", "defaultContent": 'NaN', "render": function (data, type, full, meta) {
                    if ('email_verified' in full && full['email_verified']) {
                        return `<i class="fa fa-circle" aria-hidden="true"  style="color:green" title="Verified ${new Date(full["email_verified"]).toLocaleString()}"</i>`
                    } else {
                        return '<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>'
                    }
                }
            },
            {
                "data": "disclaimer_acknowledged", "defaultContent": 'NaN', "render": function (data, type, full, meta) {
                    if ('disclaimer_acknowledged' in full && full['disclaimer_acknowledged']) {
                        return `<i class="fa fa-circle" aria-hidden="true"  style="color:green"</i>`
                    } else {
                        return '<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>'
                    }
                }
            },
            {
                "data": "vpn.wireguard.connected", "width": "10px", "defaultContent": 'NaN', "render": function (data, type, full, meta) {
                    if ('vpn' in full && full['vpn']['wireguard']['connected']) {
                        return '<i class="fa fa-circle" aria-hidden="true"  style="color:green" title="' + full["vpn"]["wireguard"]["remote_ip"] + ':' + full["vpn"]["wireguard"]["remote_port"] + '"></i>'
                    } else {
                        return '<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>'
                    }
                }
            },
            {
                "data": "accessed", "render": function (data, type, full, meta) {
                    return formatTimestampUTC(full.accessed * 1000)
                }
            },
            {
                "className": 'select-checkbox',
                "data": null,
                "orderable": false,
                "width": "10px",
                "defaultContent": '<input type="checkbox" class="form-check-input"></input>',
            },
            { "data": "id", "visible": false }
        ]
    });

    showUserExportButtons(users_table, 'users-buttons-row')
    adminShowIdCol(users_table)

    // Hide 'Category' users list column when manager
    if ($('meta[id=user_data]').attr('data-role') == 'manager') {
        var column = users_table.column(4);
        column.visible(!column.visible());
    }

    // Setup - add a text input to each footer cell
    $('#users tfoot tr:first th').each( function () {
        var title = $(this).text();
        if (['', 'Active', 'Select'].indexOf(title) == -1){
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

    users_table.on( 'click', 'tbody tr', function (e) {
        toggleRow(this, e);
    });

    $('thead #select-all').on('ifChecked', function (event) {
        var rows = users_table.rows({ filter: 'applied' }).nodes();
        $.each(rows, function (index, row) {
            $(row).find('.select-checkbox input[type="checkbox"]').prop('checked', true)
            $(row).addClass('active');
        });
    });

    $('thead #select-all').on('ifUnchecked', function (event) {
        var rows = users_table.rows({ filter: 'applied' }).nodes();
        $.each(rows, function (index, row) {
            $(row).find('.select-checkbox input[type="checkbox"]').prop('checked', false)
            $(row).removeClass('active');
        });
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
            tr.addClass('shown');
        }
    });
}

function initUsersSockets () {
    socket.on('users_data', function(data) {
        var data = JSON.parse(data);
        data['secondary_groups_names'] = data['secondary_groups_data'].map(group => group['name']);
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
                                text: item.name + " [" + item.category_name + "]",
                                id: item.id
                            }
                        })
                    };
                }
            },
        });
        setModalUser();
        $.ajax({
            type: "GET",
            url: '/api/v3/admin/user/' + pk,
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
            $.each(user.secondary_groups_data, function(i, group) {
                var newOption = new Option(group.name, group.id, true, true);
                $("#modalEditUserForm #secondary_groups").append(newOption).trigger('change');
            })
        });

	});

	$('.btn-passwd').on('click', function () {
            var closest=$(this).closest("div");
            var pk=closest.attr("data-pk");
            var name=closest.attr("data-name");
            var username=closest.attr("data-username");
            $("#modalPasswdUserForm")[0].reset();
            $("#modalPasswdUserForm .alert").empty();
            $.ajax({
                url: "/api/v3/admin/user/password-policy/" + pk,
                success: function (data) {
                    var alert = $("#modalPasswdUserForm #password-policy-list")
                    alert.append("<b>Password must contain:</b><br><ul>")
                    if (data.digits) { alert.find("ul").append(`<li>At least ${data.digits} numerical digit(s)</li>`) }
                    if (data["length"]) { alert.find("ul").append(`<li>At least ${data["length"]} character(s)</li>`) }
                    if (data.lowercase) { alert.find("ul").append(`<li>At least ${data.lowercase} lowercase character(s)</li>`) }
                    if (data.uppercase) { alert.find("ul").append(`<li>At least ${data.uppercase} uppercase character(s)</li>`) }
                    if (data.special_characters) { alert.find("ul").append(`<li>At least ${data.special_characters} special character(s)</li>`) }
                    if (data.not_username) { alert.append(`<br><b>It can not contain this user's username<b></br>`) }
                    if (data.old_passwords) { alert.append(`<br><b>It can not be one of this user's last ${data.old_passwords} passwords<b></br>`) }
                    alert.append("</ul>")
                }
            });
			$('#modalPasswdUser').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            $('#modalPasswdUserForm #name').val(name);
            $('#modalPasswdUserForm #id').val(pk);
            $('#modalPasswdUserForm #username').val(username);
	});
    $('.btn-vpn').on('click', function () {
        var closest=$(this).closest("div");
        var pk=closest.attr("data-pk");
        new PNotify({
            title: 'Reset the user\'s VPN?',
            text: "The user will have to download a new VPN file",
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
                type: "PUT",
                url: "/api/v3/admin/user/reset-vpn/" + pk,
            }).done(function (data) {
                new PNotify({
                    title: "Success",
                    text: "User VPN reset successfully",
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-success',
                    opacity: 1,
                    type: "success"
                });
            }).fail(function(data) {
                new PNotify({
                    title: "ERROR resetting VPN",
                    text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-cross',
                    opacity: 1,
                    type: 'error'
                });
            });
        }).on('pnotify.cancel', function() {});
    });


    $('.btn-delete').on('click', function () {
        var pk = $(this).closest("div").attr("data-pk");
        $("#modalDeleteUserForm")[0].reset();
        $('#modalDeleteUserForm :radio').iCheck('uncheck').iCheck('update');
        $('#modalDeleteUserForm #id').val(pk)
        if (pk == ($('meta[id=user_data]').attr('data-userid'))) {
            new PNotify({
                text: "Can not delete your own user",
                hide: true,
                opacity: 1,
                delay: 1000
            }); 
    } else {
        $('#modalDeleteUser').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
        showLoadingData('#table_modal_delete_desktops')
        showLoadingData('#table_modal_delete_templates')
        showLoadingData('#table_modal_delete_deployments')
        showLoadingData('#table_modal_delete_media')
        showLoadingData('#table_modal_delete_users')
        $.ajax({
            type: "POST",
            url: "/api/v3/admin/user/delete/check",
            data: JSON.stringify({
                "ids": [pk]
            }),
            contentType: "application/json"
        }).done(function (items) {
            populateDeleteModalTable(items.desktops, $('#table_modal_delete_desktops'));
            populateDeleteModalTable(items.templates, $('#table_modal_delete_templates'));
            populateDeleteModalTable(items.deployments, $('#table_modal_delete_deployments'));
            populateDeleteModalTable(items.media, $('#table_modal_delete_media'));
            populateDeleteModalTable(items.users, $('#table_modal_delete_users'));
        });
    }
    });

    $('.btn-active').on('click', function () {
        var closest=$(this).closest("div");
        var id=closest.attr("data-pk");
        var name=closest.attr("data-name");
        var active = !(users_table.row($(this).closest("tr").prev()).data().active)
        new PNotify({
            title: 'Confirmation Needed',
            text: "Are you sure you want to enable/disable: "+name+"?",
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
                type: "PUT",
                url: "/api/v3/admin/user/" + id,
                data: JSON.stringify({ id, active }),
                contentType: "application/json",
                success: function(data) {
                    $('form').each(function() { this.reset() });
                    $('.modal').modal('hide');
                    new PNotify({
                        title: "Updated",
                        text: "User status updated successfully",
                        hide: true,
                        delay: 4000,
                        icon: 'fa fa-success',
                        opacity: 1,
                        type: "success"
                    });
                },
                error: function(data) {
                    new PNotify({
                        title: "ERROR updating user",
                        text: data.responseJSON.description,
                        type: 'error',
                        hide: true,
                        icon: 'fa fa-warning',
                        delay: 15000,
                        opacity: 1
                    });
                }
            });
        }).on('pnotify.cancel', function() {});
    });

    $('.btn-impersonate').on('click', function () {
        var closest=$(this).closest("div");
        var id=closest.attr("data-pk");
        var name=closest.attr("data-name");
        new PNotify({
            title: 'Confirmation Needed',
            text: "Are you sure you want to impersonate as: "+name+"?",
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
                type: "GET",
                url: "/api/v3/admin/jwt/"+id,
            }).done(function (data) {
                deleteCookie('authorization')
                saveCookie('isardvdi_session', data.jwt)
                $.ajax({
                    type: "GET",
                    url: "/isard-admin/logout/remote",
                    headers: {
                        'Authorization': 'Bearer ' + data.jwt
                    },
                    success: function () {
                        $.ajax({
                            type: "GET",
                            url: "/isard-admin/login",
                            headers: {
                                'Authorization': 'Bearer ' + data.jwt
                            },
                            success: function () {
                                window.location = "/Desktops"
                            }
                        })
                    }
                })
            }).fail(function(data) {
                new PNotify({
                    title: "ERROR impersonating",
                    text: "Not allowed to impersonate as a higher role",
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-cross',
                    opacity: 1,
                    type: 'error'
                });
            });
        }).on('pnotify.cancel', function() {});
    });
};

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


function csv2datatables(csv, modal){
    csv = csv.replace(/</g, '&lt;').replace(/>/g, '&gt;')
    var csv_data = parseCSV(csv)
    if (modal=="#modalUpdateFromCSV") {
        $.each(csv_data, function(key, user) {
            if (user.active !== undefined) {
                switch(user['active'].toLowerCase()) {
                    case "true":
                        user["active"] = true
                        break;
                    case "false":
                        user["active"] = false
                        break;
                    case "":
                        delete user["active"]
                        break;
                    }
            }
            if (user.name == "") { delete user.name; }
            if (user.password == "") { delete user.password; }
            if (user.secondary_groups) { user.secondary_groups = user.secondary_groups.split("/"); } else {
                delete user.secondary_groups
            }
        });
    } else {
        $(modal + ' #bulk-allow-update').iCheck('uncheck').iCheck('update');
    }
    $.ajax({
        type: "POST",
        url: modal == "#modalUpdateFromCSV" ?
            "/api/v3/admin/users/csv/validate" :
            "/api/v3/admin/users/validate/allow_update",
        data: JSON.stringify(csv_data),
        contentType: "application/json",
        async: false,
    }).done(function (data) {
        $(modal + " #csv_correct").show()
        $(modal + " #csv_error").hide()
        $(modal + " #send").attr("disabled", false);
        if ( $.fn.dataTable.isDataTable(modal +  ' #csv_preview' ) ) {
            $.each( data, function( index, value ){
                if(value.exists){exists=true; return false}
            });
            csv_preview.clear().rows.add(data).draw()
        }else{
            csv_preview = $(modal + " #csv_preview").DataTable( {
                data: data,
                rowId: 'username',
                columns: modal == "#modalUpdateFromCSV" ? [
                    { "data": "active", "width": "50px", "render": function (data, type, full, meta) {
                        if (full.active) {
                            active = true
                            return '<i class="fa fa-check" style="color:lightgreen"></i>';
                        } else if (full.active===false) {
                            return '<i class="fa fa-close" style="color:darkgray"></i>';
                        }
                    } },
                    { "data": "name", "width": "88px", },
                    { "data": "provider", "width": "50px", "className": "no-update" },
                    { "data": "category", "width": "88px", "defaultContent": "", "className": "no-update" },
                    { "data": "uid", "width": "88px", "className": "no-update" },
                    { "data": "group", "width": "88px", "defaultContent": "", "className": "no-update" },
                    { "data": "secondary_groups_names", "width": "88px", "defaultContent": "", },
                    { "data": "password", "width": "88px" },
                ] : [
                    { "data": "exists", "width": "88px", "render": function (data, type, full, meta) {
                        if (full.exists) {
                            exists = true
                            return '<i class="fa fa-check" style="color:lightgreen"></i>';
                        } else {
                            return '<i class="fa fa-close" style="color:darkgray"></i>';
                        }
                    } },
                    { "data": "username", "width": "88px", "className": "no-update" },
                    { "data": "name", "width": "88px" },
                    { "data": "email", "width": "88px" },
                    { "data": "password", "width": "88px" },
                    { "data": "group", "width": "88px", "defaultContent": "", "className": "no-update" },
                    { "data": "category", "width": "88px", "defaultContent": "", "className": "no-update" },
                    { "data": "role", "width": "88px", "defaultContent": "" },
                ] ,
                "order": [[0, 'asc']],
            } );
        }
    }).fail(function (data) {
        $(modal + " #csv_correct").hide()
        $(modal + " #send").attr("disabled", true);
        $(modal + " #csv_error #csv_error_html").html(data.responseJSON.description)
        $(modal + " #csv_error").show()
        if ($.fn.dataTable.isDataTable(modal + ' #csv_preview')) {
            csv_preview.clear()
        }
    });
}


function parseCSV(csv){
    lines=csv.split(/\r?\n/)
    header=lines[0].split(',')
    users=[]
    $.each(lines, function(n, l){
        if(n!=0 && l.length > 10){
            // var regex = /("[^"]*"|[^,]+)(?=,|$)/g;
            usr = toObject(header,l.split(","));
            usr['id']=usr['username']
            users.push(usr)
        }
    })
    return users;
}

function toObject(names, values) {
    var result = {};
    for (var i = 0; i < names.length; i++)
         result[names[i]] = values[i];
    return result;
}

function showUserExportButtons(table, buttonsRowClass) {
    new $.fn.dataTable.Buttons(table, {
        buttons: [
            {
                extend: 'csv',
                exportOptions: {
                },
                customize: function (csv) {
                    var split_csv = csv.split("\n");
                    var csv_data = 'Active,Name,Provider,Category,UID,Role,Group,Secondary groups,VPN,Last access,ID\n';

                    $.each(split_csv.slice(1), function (index, csv_row) {
                        var csv_cell_array = csv_row.split('","');
                        csv_cell_array.splice(0, 1);
                        csv_cell_array.splice(10, 1);
                        pk = csv_cell_array[csv_cell_array.length - 1].replace(/"/g, '');

                        var rowData = table.row('#' + pk).data();
                        csv_cell_array[0] = rowData.active;
                        csv_cell_array[7] = csv_cell_array[8].replace(/,/g, ' | ');
                        csv_cell_array[8] = rowData.vpn.wireguard.connected;

                        csv_data = csv_data + csv_cell_array + '\n';
                    });
                    return csv_data
                }
            },
            'excel',
            'print',
            {
                extend: 'csv',
                text: 'CSV with import format',
                exportOptions: {
                    columns: [15] // ID column
                },
                title: "csv_with_import_format",
                titleAttr: "Generate a CSV file from the current displayed data, to use in the \"Update from CSV\" feature.",
                customize: function (csv) {
                    var csv_data = ['active,name,provider,category,uid,username,group,secondary_groups,password\n']
                    var split_csv = csv.split("\n");
                    $.each(split_csv.slice(1), function (index, csv_row) {
                        var csv_cell_array = csv_row.split('","');
                        csv_cell_array[0] = csv_cell_array[0].replace(/"/g, '');
                        var rowData = table.row('#' + csv_cell_array[0]).data();
                        csv_data = csv_data + (`${rowData.active},\"${rowData.name}\",${rowData.provider},${rowData.category_name},${rowData.uid},${rowData.username},${rowData.group_name},${rowData.secondary_groups_names.join("/")},\n`);
                    });
                    return csv_data
                }
            },
        ]
    }).container()
        .appendTo($('.' + buttonsRowClass));
}

function getSelectedUserList() {
    let userList = [];
    users_table.rows({ filter: 'applied' }).every(function () {
        var rowNodes = this.nodes();
        var rowData = this.data();
        if ($('thead #select-all').prop('checked')) { // case select all is checked
            userList.push(rowData); // get all the users filtered in the table
            rowNodes.each(function () {
                if (!$(this).hasClass('active')) {
                    var index = userList.indexOf(rowData);
                    if (index !== -1) {
                        userList.splice(index, 1);
                    } // delete the unchecked rows
                    return false;
                }
            })
        } else {
            rowNodes.each(function () {
                if ($(this).hasClass('active')) {
                    userList.push(rowData);
                    return false;
                }
            });
        }
    });
    return userList;
}

function showAlert(alertSelector, msg, type) {
    alertSelector.empty();
    alertSelector.html(msg);
    alertSelector.addClass('alert-' + type);
    alertSelector.removeClass('alert-' + type == 'error' ? 'success' : 'error')
    alertSelector.show();
}

function render_users_to_edit_table(usersToEdit) {
    $("#users-to-edit tbody").empty();

    $.each(usersToEdit, function (key, user) {
        $("#users-to-edit tbody").append(`
        <tr>
            <td>${user.active == true ?
                '<i class="fa fa-check" style="color:lightgreen"></i>'
                :
                '<i class="fa fa-close" style="color:darkgray"></i>'}
            <td>${user.username}</td>
            <td>${user.name}</td>
            <td>${user.group_name}</td>
            <td>${user["secondary_groups_names"].join(",")}</td>
        </tr>
        `)
    });
}