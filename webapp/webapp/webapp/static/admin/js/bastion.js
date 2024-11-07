$(document).ready(function () {
    $("#BastionConfig #btn-alloweds").on('click', function (e) {
        new PNotify({
            title: "Warning!",
            text: `Removing a user's access will remove the bastion targets for ALL their desktops. 
            This action is irreversible.`,
            type: "error",
            addclass: 'pnotify-center-large',
            confirm: {
                confirm: true,
                buttons: [
                    {
                        text: 'Edit', click: function (notice) {
                            modalAllowedsFormShow("bastion", { id: 1, name: 'Bastion' });
                            notice.remove();
                        }
                    },
                    {
                        text: 'Cancel', click: function (notice) {
                            notice.remove();
                        }
                    }
                ]
            },
        });
    });

    $.ajax({
        type: 'GET',
        url: "/api/v3/admin/bastion/",
        contentType: 'application/json',
        success: function (data) {
            if (data['bastion_enabled'] === true) {
                $("#BastionConfig #bastionStatusLabel").text("Bastion enabled in cfg. SSH port: " + data['bastion_ssh_port']);
                $("#BastionConfig #btn-alloweds").show();
                $("#BastionConfig #btn-delete-disallowed").show();
            } else {
                $("#BastionConfig #bastionStatusLabel").text("Bastion disabled in cfg.");
                $("#BastionConfig #bastionStatusDescription").html(`<b>
                        The bastion feature is disabled in in your configuration file. <br>
                        To enable it, please edit the configuration file to uncomment 'BASTION_ENABLED' and set it to true. <br>
                        Then execute build.sh and restart isard to apply the changes.
                    </b>`);
                $("#BastionConfig #btn-alloweds").hide();
                $("#BastionConfig #btn-delete-disallowed").hide();
            }
        },
        error: function (data) {
            new PNotify({
                title: `ERROR getting configuration`,
                text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                type: 'error',
                hide: true,
                icon: 'fa fa-warning',
                delay: 5000,
                opacity: 1
            });
        }
    })

    $("#BastionConfig #btn-delete-disallowed").on("click", function () {
        new PNotify({
            title: "Are you sure you want to delete disallowed bastion targets?",
            text: `This action is irreversible and may take a while.`,
            addclass: 'pnotify-center-large',
            confirm: {
                confirm: true,
                buttons: [
                    {
                        text: 'Delete', click: function (notice) {
                            $.ajax({
                                type: "DELETE",
                                url: "/api/v3/admin/bastion/disallowed",
                                accept: "application/json",
                            }).done(() => {
                                new PNotify({
                                    title: "Deleting bastion targets...",
                                    text: `Disallowed bastion targets are being deleted`,
                                    hide: true,
                                    delay: 1000,
                                    icon: 'fa fa-spinner fa-pulse',
                                    opacity: 1,
                                    type: 'success'
                                });
                            }).fail(function (data) {
                                new PNotify({
                                    title: "ERROR deleting bastion targets",
                                    text: data.responseJSON ? data.responseJSON.description : "Something went wrong",
                                    hide: true,
                                    delay: 1000,
                                    icon: 'fa fa-error',
                                    opacity: 1,
                                    type: 'error'
                                });
                            });
                            notice.remove();
                        }
                    },
                    {
                        text: 'Cancel', click: function (notice) {
                            notice.remove();
                        }
                    }
                ]
            },
        });
    });

});