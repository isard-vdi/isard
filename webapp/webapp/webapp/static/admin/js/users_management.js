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
    $('.external-apps .collapse-link ').find('i').toggleClass('fa-chevron-down fa-chevron-up');
    $("#modalMigrateUser #modalMigrateUserForm .collapse-link").off("click").on("click", function () {
        // Show or hide resources-table
        $(this).find('i').toggleClass('fa-chevron-down fa-chevron-up');
        var opened = $(this).find('i').hasClass('fa-chevron-up');
        $(this).closest('.collapse-link').find('span').html(opened ? 'hide' : 'show');
        $(this).closest('.collapse-link').parent().next('.x_content').slideToggle();
    });
    $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on)
})
function socketio_on(){
    $template = $(".template-detail-users");

	$('.btn-new-user').on('click', function () {
        setQuotaMax('#users-quota',kind='category',id=false,disabled=false);
        $('#modalAddUser .email-verified').iCheck('uncheck').iCheck('update');
        $('#modalAddUser .apply').html('group quota');
        $('#modalAddUser').modal({backdrop: 'static', keyboard: false}).modal('show');
        $('#modalAddUserForm')[0].reset();

        current_category = $('#modalAddUserForm #category').val();

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
        var users_to_enable = data['users'].map(user => user["active"] === true ? user["id"] : null).filter(id => id !== null);
        checkMigratedAndProceed(users_to_enable, function () {
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
    })
    });

	$('.btn-new-bulkusers').on('click', function () {
        $("#csv_error").hide()
        $('#bulk-allow-update').iCheck('uncheck').iCheck('update');
        setQuotaMax('#bulkusers-quota',kind='category',id=false,disabled=false);
        $('#modalAddBulkUsers .apply').html('group quota');
        $("#modalAddBulkUsers #send").attr("disabled", true);
        $('#modalAddBulkUsers').modal({backdrop: 'static', keyboard: false}).modal('show');
        $('#modalAddBulkUsersForm')[0].reset();
        $('#modalAddBulkUsersForm :checkbox').iCheck('uncheck').iCheck('update');
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
            $(modal + ' .email-verified').iCheck('check').iCheck('update');
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
            showAndHideByCheckbox($(modal + " #edit-email-verified-checkbox"), $(modal + " #email-verified-panel"));
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

            (async function () {
                // every ajax call here is awaited so the modal can be hidden only if no errors are found
                if (['active'] in update_data) {
                    var action = update_data['active'] ? 'enable' : 'disable';
                    if (update_data['active']) {
                        await checkMigratedAndProceed(data['ids'], function () {
                            hideModal = updateUserBulkData(update_data, form, hideModal);
                        });
                    } else {
                        hideModal = updateUserBulkData(update_data, form, hideModal);
                    }
                }
                if (data["edit-secondary-group"] === 'on') {
                    await $.ajax({
                        type: 'PUT',
                        url: `/api/v3/admin/user/secondary-groups/${data['action-secondary-group']}`,
                        data: JSON.stringify({
                            "secondary_groups": data['secondary_groups'] ? data['secondary_groups'] : [],
                            "ids": data['ids']
                        }),
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
                if (data["edit-email-verified"] === 'on') {
                    await $.ajax({
                        type: 'PUT',
                        url: '/api/v3/admin/users/bulk',
                        data: JSON.stringify({ "email_verified": data['email-verified'] === 'on', "ids": data['ids'] }),
                        contentType: 'application/json',
                        success: function () {
                            showAlert(form.find("#general-alert"), "Updated successfully", "success");
                        },
                        error: function (data) {
                            hideModal = false;
                            showAlert(form.find("#general-alert"), data.responseJSON.description, "error");
                        }
                    });
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
            })();
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
                [`username,name,email,group,category,role\njdoe,John Doe,jdoe@isardvdi.com,Default,Default,advanced\nauser,Another User,auser@domain.com,Default,Default,user`
                ], { type: "text/csv" });
        } else if (kind === 'download-generated') {
            $("#modalAddBulkUsers #send").attr("disabled", false);

            var notice = new PNotify({
                title: "Creating CSV file...",
                icon: 'fa fa-spinner fa-spin',
            })
            var form = $('#modalAddBulkUsersForm');
            $("#modalAddBulkUserForm #bulk_secondary_groups").empty().trigger('change')
            formdata = form.serializeObject()
            form.parsley().validate();
            if (form.parsley().isValid()) {
                users = csv_preview.data().toArray()
                filecontents = users.map(user => {
                    return `${user.username},${user.name},${user.email},\"${user.password.replace(/"/g, '""')}\",${user.group},${user.category},${user.role}`
                }
                ).join('\n')
                viewerFile = new Blob([`username,name,email,password,group,category,role\n` + filecontents], { type: "text/csv" });
                notice.update({
                    title: "CSV file created",
                    hide: true,
                    delay: 5000,
                    icon: 'fa fa-success',
                    opacity: 1,
                    type: 'success'
                });
            } else {
                notice.update({
                    title: "ERROR creating CSV file",
                    text: 'Please fill all the required fields',
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 5000,
                    opacity: 1
                });
                return;
            }
        }
        var a = document.createElement('a');
            if (kind === 'download-generated') {
                a.download = 'bulk-users.csv';
            } else {
                a.download = 'bulk-users-template.csv';
            }
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
            data['email_verified'] = data['email-verified'] === 'on';
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
            data['email_verified'] = data['email-verified'] === 'on';
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

    $("#modalMigrateUser #send").on("click", function (e) {
        var form = $('#modalMigrateUserForm');
        form.parsley().validate();
        if (form.parsley().isValid()) {
            data = form.serializeObject();
            var notice = new PNotify({});
            $.ajax({
                type: "PUT",
                url: "/api/v3/admin/user/migrate/" + data['id'] + "/" + data['target_user'],
                data: {},
                contentType: "application/json",
            }).done(function () {
                $('.modal').modal('hide');
                notice.update({
                    title: `Processing...`,
                    text: `Migrating user`,
                    hide: false,
                    opacity: 1,
                    icon: 'fa fa-spinner fa-pulse'
                });
            }).fail(function (data) {
                notice.update({
                    title: "ERROR migrating user",
                    text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-cross',
                    opacity: 1,
                    type: 'error'
                });
            });
        }
    })

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
            var notice = new PNotify({})
            $.ajax({
                type: 'DELETE',
                url: '/api/v3/admin/user',
                data: JSON.stringify({ 'user': user, 'delete_user': formData['delete-user'] == 'true' }),
                contentType: 'application/json',
                error: function (data) {
                    if (data.responseJSON && data.responseJSON.exceptions) {
                        const exceptionsList = data.responseJSON.exceptions.map(exception => `<li>${exception}</li>`).join('');
                        notice.update({
                            title: "ERROR deleting user(s)",
                            text: `<ul>${exceptionsList}</ul>`,
                            hide: true,
                            delay: 3000,
                            icon: 'fa fa-alert-sign',
                            opacity: 1,
                            type: 'error'
                        });
                    } else {
                        notice.update({
                            title: "ERROR deleting user(s)",
                            text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                            hide: false,
                            opacity: 1,
                            icon: 'fa fa-spinner fa-pulse'
                        })
                    }
                },
                success: function (data) {
                    $('form').each(function () {
                        this.reset()
                    })
                    $('.modal').modal('hide')
                    notice.update({
                        title: `Processing...`,
                        text: `Deleting ${user.length} user(s)`,
                        hide: false,
                        opacity: 1,
                        icon: 'fa fa-spinner fa-pulse'
                    })
                }
            })
        };
    });

    $('#csv, #csv-edit').on('change', function (evt) {
        var files = evt.target.files;
        var file = files[0];
        var filecontents=''
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
            var modal = this.id === 'csv' ? '#modalAddBulkUsers' : '#modalUpdateFromCSV';
            reader.onload = function (event) {
                filecontents = event.target.result;
                csv2datatables(filecontents, modal)
            }
            reader.readAsText(file, 'UTF-8')
        }
    })

    $("#modalAddBulkUsers #send").on('click', function(e){
        var form = $('#modalAddBulkUsersForm');
        $("#modalAddBulkUserForm #bulk_secondary_groups").empty().trigger('change')
        formdata = form.serializeObject()
        form.parsley().validate();
        formdata['email-verified'] = formdata['email-verified'] === 'on'
        if (form.parsley().isValid()){
            users=csv_preview.data().toArray()
            var notice = new PNotify({
                title: "Adding users",
            })
            $.ajax({
                type: 'POST',
                url: "/api/v3/admin/bulk/user",
                data: JSON.stringify({ users: users, email_verified: formdata['email-verified'] }),
                contentType: "application/json",
                success: function(data)
                {
                    $('form').each(function() { this.reset() });
                    $('.modal').modal('hide');
                notice.update({
                        title: `Adding ${ users.length } users`,
                        text: "This process may take a while, please wait",
                        hide: true,
                        delay: 4000,
                        opacity: 1
                    });
                },
                error: function(data){
                    new PNotify({
                        title: "ERROR adding users",
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
            {
                "data": "group_name", "width": "10px", "render": function (data, type, full, meta) {
                    return full.group_name ? full.group_name : ''
                }
            },
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
                        return `<i class="fa fa-circle" aria-hidden="true"  style="color:green" title="Verified ${new Date(full["email_verified"]*1000).toLocaleString()}"></i>`
                    } else {
                        return `<i class="fa fa-circle" aria-hidden="true"  style="color:darkgray"></i>`
                    }
                }
            },
            {
                "data": "email", "defaultContent": 'NaN', "render": function (data, type, full, meta) {
                    if ('email_verified' in full && full['email_verified']) {
                        return `<p style="color:green" title="Verified ${new Date(full["email_verified"]).toLocaleString()}">${full['email'] ? full['email'] : ''}</p>`
                    } else {
                        return `<p>${full['email'] ? full['email'] : ''}</p>`
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

notice = {}

function initUsersSockets () { 
    socket.on('msg', function (data) {
        var data = JSON.parse(data);
        if (data.id !== ""){
            if (!(data.id in notice)) {
                notice[data.id] = new PNotify({
                    title: data.title,
                    text: data.description,
                    hide: (data.params.hide != undefined ? data.params.hide : true),
                    delay: (data.params.delay != undefined ? data.params.delay : 4000),
                    icon: 'fa fa-' + (data.params.icon != undefined ? data.params.icon : 'info'),
                    opacity: 1,
                    type: data.type
                });
            }
            
            if (data.params.delete == true){
                notice[data.id].remove()
            } else {
                notice[data.id].update({
                    title: data.title,
                    text: data.description,
                    hide: (data.params.hide != undefined ? data.params.hide : true),
                    delay: (data.params.delay != undefined ? data.params.delay : 4000),
                    icon: 'fa fa-' + (data.params.icon != undefined ? data.params.icon : 'info'),
                    type: data.type
                });
            }
        } else {
            new PNotify({
                title: data.title,
                text: data.description,
                hide: (data.params.hide != undefined ? data.params.hide : true),
                delay: (data.params.delay != undefined ? data.params.delay : 4000),
                icon: 'fa fa-' + (data.params.icon != undefined ? data.params.icon : 'info'),
                opacity: 1,
                type: data.type
            });
        }
    });

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

    socket.on('user_action', function (data) {
        PNotify.removeAll();
        var data = JSON.parse(data);
        if (data.status === 'failed') {
          new PNotify({
            title: `ERROR: ${data.action} on ${data.count} user(s)`,
            text: data.msg,
            hide: false,
            icon: 'fa fa-warning',
            opacity: 1,
            type: 'error'
          });
        } else if (data.status === 'completed') {
          users_table.ajax.reload();
          new PNotify({
            title: `Action Succeeded: ${data.action}`,
            text: `The action "${data.action}" completed on ${data.count} user(s).`,
            hide: true,
            delay: 4000,
            icon: 'fa fa-success',
            opacity: 1,
            type: 'success'
          });
        }
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
            $('#modalEditUserForm #email-verified').iCheck('uncheck').iCheck('update');
            if (user.email_verified) {
                $('#modalEditUserForm #email-verified').iCheck('check').iCheck('update');
            }
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
            current_category = $('#modalEditUserForm #category').val();
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
        var action = active ? 'enable' : 'disable';
        new PNotify({
            title: 'Confirmation Needed',
            text: "Are you sure you want to "+action+": "+name+"?",
            hide: false,
            opacity: 0.9,
            confirm: { confirm: true },
            buttons: { closer: false, sticker: false },
            history: { history: false },
            addclass: 'pnotify-center'
        }).get().on('pnotify.confirm', function() {
            if (active) {
                checkMigratedAndProceed([id], function() {
                    enableDisableUser(id, active);
                });
            } else {
                enableDisableUser(id, active);
            }
        }).on('pnotify.cancel', function() {});
    });

    $('.btn-migrate').on('click', function () {
        var closest = $(this).closest("div");
        var id = closest.attr("data-pk");
        var rowData = users_table.row("#" + id).data();
        var category = rowData.category_name;
        let modal = "#modalMigrateUser"
        resetMigrationModalForm();
        $(modal + ' #modalMigrateUserForm #id').val(id);
        $(modal + ' .modal-migration-title span#user-name').text(rowData.name);
        $.ajax({
            type: "POST",
            url: "/api/v3/admin/user/delete/check",
            data: JSON.stringify({ "ids": [id] }),
            contentType: "application/json"
        }).done(function (items) {
            $(modal).modal({
                backdrop: 'static',
                keyboard: false
            }).modal('show');
            // Filter out items that do not belong to the user being migrated (deployed desktops and dependant templates)
            items.desktops = items.desktops.filter(function (item) { return item.user == id });
            items.templates = items.templates.filter(function (item) { return item.user == id });
            const resourceTypes = [
                { type: 'desktops', columns: ["name", "persistent"] },
                { type: 'templates', columns: ["name", "duplicate_parent_template"] },
                { type: 'deployments', columns: ["name"] },
                { type: 'media', columns: ["name"] }
            ];
            let hasItems = false;
            $.each(resourceTypes, function (_, resource) {
                const itemsCount = items[resource.type].length;
                const table = `${modal} #table_modal_delete_${resource.type}`;
                const qtySpan = `${modal} #modalMigrateUserForm #resources-summary .qty-${resource.type}`;
                populateDeleteModalTable(items[resource.type], $(table), resource.columns);
                $(qtySpan).parent().parent().show();
                $(qtySpan).text(itemsCount);
                if (itemsCount) {
                    hasItems = true;
                }
            });

            $(modal + ' #target-user').select2({
                minimumInputLength: 2,
                dropdownParent: $(modal + "Form"),
                placeholder: 'Select a user from category ' + rowData.category_name,
                ajax: {
                    type: "POST",
                    url: '/api/v3/admin/allowed/term/users/',
                    dataType: 'json',
                    contentType: "application/json",
                    delay: 250,
                    data: function (params) {
                        return JSON.stringify({
                            term: params.term,
                            pluck: ['id', 'username', 'role', 'name', 'group_name'],
                        });
                    },
                    processResults: function (data) {
                        // Filter out users with category_name that does not match 'category'
                        if ($('meta[id=user_data]').data('role') != 'admin') {
                            userData = data;
                        } else {
                            userData = data.filter(function (item) {
                                return item.category_name === category;
                            });
                        }
                        // Filter out the user being migrated
                        userData = userData.filter(function (item) {
                            return item.id != rowData.id;
                        });
                        // Filter out users with role 'admin' if the user being migrated is not role 'admin'
                        if ($('meta[id=user_data]').data('role') != 'admin') {
                            userData = userData.filter(function (item) {
                                return item.role != 'admin';
                            });
                        }
                        return {
                            results: $.map(userData, function (item, i) {
                                return {
                                    text: `[${item.role}] ${item.username} - ${item.name} (${item.group_name})`,
                                    id: item.id
                                }
                            })
                        };
                    }
                },
            })
            if (!hasItems) {
                var alert = $(modal + ' #modalMigrateUserForm #alert-migrate-user-errors');
                alert.empty();
                alert.append("<b>Errors:</b><br><ul>");
                alert.append(`<li>The user has no items to migrate!</li>`);
                alert.append("</ul>");
                alert.show();
                $(modal + ' #send').prop('disabled', true);
                $(modal + ' #target-user').prop('disabled', true);
            }
        });
    });

    // When selecting a user call to the API to check whether the user can migrate (role/quota checks)
    $('#modalMigrateUser #target-user').off('select2:select').on('select2:select', function (e) {
        var modal = "#modalMigrateUser";
        var originUserId = $(modal + ' #modalMigrateUserForm #id').val();
        var targetUserId = e.params.data.id;
        resetMigrationModalErrors(modal+ ' #modalMigrateUserForm');
        $.ajax({
            type: "GET",
            url: "/api/v3/admin/user/migrate/check/" + originUserId + "/" + targetUserId,
            contentType: "application/json",
            success: function (data) {
                if (data.errors.length > 0) {
                    $(modal + ' #send').prop('disabled', true);
                    var alert = $(modal + ' #modalMigrateUserForm #alert-migrate-user-errors');
                    alert.empty();
                    alert.append("<b>Errors:</b><br><ul>");
                    data.errors.forEach(function (error) {
                        alert.append(`<li>${error.description}</li>`);
                        const errorMapping = {
                            'role_migration_user': ["deployments", "templates", "media"],
                            'migration_desktop_quota_error': ["desktops"],
                            'migration_template_quota_error': ["templates"],
                            'migration_media_quota_error': ["media"],
                            'migration_deployments_quota_error': ["deployments"]
                        };

                        if (error.description_code in errorMapping) {
                            errorMapping[error.description_code].forEach(resource => {
                                $(`#modalMigrateUserForm #resources-summary .qty-${resource}`).parent().css('color', 'red');
                            });
                        }

                    });
                    alert.append("</ul>");
                    alert.show();
                } else {
                    $(modal + ' #send').prop('disabled', false);
                }
            },
            error: function (data) {
                $(modal + ' #send').prop('disabled', true);
                $(modal + ' #send').prop('title', data.responseJSON.description);
            }
        });
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
                        setAjaxHeader()
                        $.ajax({
                            type: "GET",
                            url: "/isard-admin/login",
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

    $('.btn-revoke').on('click', function () {
        var closest = $(this).closest("div");
        var id = closest.attr("data-pk");
        var name = closest.attr("data-name");
        new PNotify({
            title: 'Confirmation Needed',
            text: "Are you sure you want to log out " + name + "?",
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
                type: "PUT",
                url: "/api/v3/admin/user/" + id + "/logout",
            }).done(function (data) {
                new PNotify({
                    title: "Logged out",
                    text: name + " logged out successfully",
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-success',
                    opacity: 1,
                    type: "success"
                });
            }).fail(function (data) {
                new PNotify({
                    title: "ERROR logging out",
                    text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                    hide: true,
                    delay: 4000,
                    icon: 'fa fa-cross',
                    opacity: 1,
                    type: 'error'
                });
            });
        }).on('pnotify.cancel', function () { });
    });
};

function resetMigrationModalForm() {

    var modal = '#modalMigrateUser'
    var modalForm = `${modal} #modalMigrateUserForm`

    $(modalForm + ' select').empty();
    $(modalForm + ' #resources-tables').hide();
    $(modalForm + ' .collapse-link').find('i').removeClass('fa-chevron-up').addClass('fa-chevron-down');
    $(modalForm + ' .collapse-link').find('span').html('show');
    resetMigrationModalErrors(modalForm)
    $(modal + ' #target-user').prop('disabled', false);
    $(modal + '  #send').prop('disabled', true);

}

function resetMigrationModalErrors(modalForm) {
    $(modalForm + ' #alert-migrate-user-errors').hide();
    ["desktops", "deployments", "templates", "media"].forEach(resource => {
        $(`#modalMigrateUserForm #resources-summary .qty-${resource}`).parent().css('color', 'black');
    });
}

function renderUsersDetailPannel ( d ) {
    if(d.id == 'local-default-admin-admin'){
        $('.template-detail-users .btn-delete').hide()
    }else{
        $('.template-detail-users .btn-delete').show()
    }
    if ($('meta[id=user_data]').attr('data-role') == 'manager' && d.role == 'admin') {
        $('.template-detail-users .btn-revoke').hide()
    } else {
        $('.template-detail-users .btn-revoke').show()
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


function csv2datatables(csv, modal) {
    csv = csv.replace(/</g, '&lt;').replace(/>/g, '&gt;')
    var csv_data = parseCSV(csv)
    if (csv_data.error !== "") {
        $(modal + " #csv_correct").hide()
        $(modal + " #send").attr("disabled", true);
        $(modal + " #csv_error #csv_error_html").html(csv_data.error)
        $(modal + " #csv_error").show()
        if ($.fn.dataTable.isDataTable(modal + ' #csv_preview')) {
            csv_preview.clear()
        }
        return
    }
    if (modal == "#modalUpdateFromCSV") {
        $.each(csv_data.users, function (key, user) {
            if (user.active !== undefined) {
                switch (user['active'].toLowerCase()) {
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
    }
    $.ajax({
        type: modal == "#modalUpdateFromCSV" ? "PUT" : "POST",
        url: "/api/v3/admin/users/csv/validate",
        data: JSON.stringify(csv_data.users),
        contentType: "application/json",
        async: false,
    }).done(function (data) {
        $(modal + " #csv_correct").show()
        // $(modal + " #send").attr("disabled", false);
        if (data.errors && data.errors.length > 0) {
            $(modal + " #csv_error").show()
            let errorsHtml = '<ul>'
            data.errors.forEach(function (error) {
                errorsHtml += '<li>' + error + '</li>'
            })
            errorsHtml += '</ul>'
            $(modal + " #csv_error #csv_error_html").html(errorsHtml)
        }
        $(modal + " #csv_preview").DataTable().destroy();
        csv_preview = $(modal + " #csv_preview").DataTable({
            data: modal == "#modalUpdateFromCSV" ? data : data.users,
            rowId: modal == "#modalUpdateFromCSV" ? "id": "username",
            columns: modal == "#modalUpdateFromCSV" ? [
                {
                    "data": "active",
                    "width": "50px",
                    "render": function (data, type, full, meta) {
                        if (full.active) {
                            active = true
                            return '<i class="fa fa-check" style="color:lightgreen"></i>';
                        } else if (full.active === false) {
                            return '<i class="fa fa-close" style="color:darkgray"></i>';
                        }
                    }
                },
                { "data": "name", "width": "88px", },
                { "data": "provider", "width": "50px", "className": "no-update" },
                { "data": "category", "width": "88px", "defaultContent": "", "className": "no-update" },
                { "data": "uid", "width": "88px", "className": "no-update" },
                { "data": "group", "width": "88px", "defaultContent": "", "className": "no-update" },
                { "data": "secondary_groups_names", "width": "88px", "defaultContent": "", },
                {
                    "data": "password",
                    "width": "88px",
                    "render": function (data, type, full, meta) {
                        return "*****"
                    }
                },
            ] : [
                { "data": "username", "width": "88px" },
                { "data": "name", "width": "88px" },
                { "data": "email", "width": "88px" },
                {
                    "data": "password",
                    "width": "88px",
                    "render": function (data, type, full, meta) {
                        return "*****"
                    }
                },
                { "data": "group", "width": "88px", "defaultContent": "" },
                { "data": "category", "width": "88px", "defaultContent": "" },
                { "data": "role", "width": "88px", "defaultContent": "" },
            ],
            "order": [[0, 'asc']],
        });
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


function parseCSV(csv) {
    lines = csv.split(/\r?\n/)
    if (lines.length > 202) {
        return {
            users: [],
            error: "The maximum number of users that can be added at once is 200"
        }
    }
    var separator = ''
    const separators = [',', ';']
    for (var i = 0; i < separators.length; i++) {
        header = lines[0].split(separators[i])
        if (header.length < 2) {
            continue
        } else {
            separator = separators[i]
            break
        }
    }
    if (separator == '') {
        return {
            users: [],
            error: "Header must be separated by " + separators.join(" or ")
        }
    }
    users = []
    $.each(lines, function (n, l) {
        if (n != 0 && l.length > 10) {
            // var regex = /("[^"]*"|[^,]+)(?=,|$)/g;
            usr = toObject(header, l.split(separator));

            // remove enclosing quotes and unescape fields
            for (var key in usr) {
                usr[key] = usr[key].replace(/^"(.*)"$/, '$1').replace(/""/g, '"');
            }
            usr['id'] = usr['username']
            users.push(usr)
        }
    })
    return { users: users, error: "" };
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
                title: "csv-users",
                titleAttr: "Export the current displayed data to a CSV file",
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

                        csv_data = csv_data + csv_cell_array.join(",") + '\n';
                    });
                    return csv_data
                }
            },
            'excel',
            {
                extend:'print',
                title: "print-users",
                titleAttr: "Print the current displayed data",
            },
            {
                extend: 'csv',
                text: 'CSV for update',
                exportOptions: {
                    columns: [16] // ID column
                },
                title: "update-from-csv-export",
                titleAttr: "Generate a CSV file from the current displayed data, to use in the \"Update from CSV\" feature.",
                customize: function (csv) {
                    var csv_data = ['active,name,provider,category,uid,username,group,secondary_groups,password\n']
                    var split_csv = csv.split("\n");
                    $.each(split_csv.slice(1), function (index, csv_row) {
                        var csv_cell_array = csv_row.split('","');
                        csv_cell_array[0] = csv_cell_array[0].replace(/"/g, '');
                        var rowData = table.row('#' + csv_cell_array[0]).data();
                        csv_data = csv_data + (`${rowData.active},${rowData.name},${rowData.provider},${rowData.category_name},${rowData.uid},${rowData.username},${rowData.group_name},${rowData.secondary_groups_names.join("/")},\n`);
                    });
                    return csv_data
                }
            },
            {
                extend: 'csv',
                text: 'CSV for create',
                exportOptions: {
                    columns: [16] // ID column
                },
                title: "bulk-users-export",
                titleAttr: `Generate a CSV file from the current displayed data, to use in the \"Bulk create\" feature.`,
                customize: function (csv) {
                    var csv_data = ['username,name,email,group,category,role\n']
                    var split_csv = csv.split("\n");
                    $.each(split_csv.slice(1), function (index, csv_row) {
                        var csv_cell_array = csv_row.split('","');
                        csv_cell_array[0] = csv_cell_array[0].replace(/"/g, '');
                        var rowData = table.row('#' + csv_cell_array[0]).data();
                        csv_data = csv_data + (`${rowData.uid},${rowData.name},${rowData.email},${rowData.group_name},${rowData.category_name},${rowData.role}\n`);
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

function enableDisableUser(user_id, active) {
    $.ajax({
        type: "PUT",
        url: "/api/v3/admin/user/" + user_id,
        data: JSON.stringify({ user_id, active }),
        contentType: "application/json",
        success: function (data) {
            $('form').each(function () { this.reset(); });
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
        error: function (data) {
            new PNotify({
                title: "ERROR updating user",
                text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                type: 'error',
                hide: true,
                icon: 'fa fa-warning',
                delay: 15000,
                opacity: 1
            });
        }
    });
}


function updateUserBulkData(update_data, form, hideModal) {
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
    return hideModal;
}


async function checkMigratedAndProceed(users, onSuccess) {
    return new Promise((resolve, reject) => {
        $.ajax({
            type: "POST",
            url: `/api/v3/admin/user/check/migrated`,
            data: JSON.stringify({ "users": users }),
            contentType: "application/json",
            success: function (data) {
                if (data.migrated) {
                    new PNotify({
                        title: 'Warning!',
                        text: `You are about to enable a migrated user that was disabled by the system.`,
                        hide: false, opacity: 0.9, type: 'error',
                        confirm: {
                            confirm: true,
                            buttons: [
                                {
                                    text: "Ok", promptTrigger: true,
                                    click: function (notice, value) {
                                        notice.remove();
                                        onSuccess();
                                        resolve();
                                    }
                                },
                                { 
                                    text: "Cancel", promptTrigger: true,
                                    click: function (notice) {
                                        notice.remove();
                                        reject();
                                    }
                                }
                            ]
                        }
                    }).open()
                } else {
                    onSuccess();
                    resolve();
                }
            },
            error: function (xhr) {
                new PNotify({
                    title: "ERROR",
                    text: xhr.responseJSON ? xhr.responseJSON.description : 'Something went wrong',
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 5000,
                    opacity: 1
                });
                reject();
            }
        });
    });
}
