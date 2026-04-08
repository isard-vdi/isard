$(document).ready(function () {
    $("#btnEditLoginNotification").on("click", function () {
        var modal = "#modalEditLoginNotification";
        $.ajax({
            type: "GET",
            url: "/api/v3/login_config",
        }).done(function (data) {
            populateLoginNotificationForm(modal, data);
        });
        $(modal).modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
    });

    $("#modalEditLoginNotification #send").on("click", function () {
        var form = $('#modalEditLoginNotificationForm');
        form.parsley().validate();
        data = collectLoginNotificationData(form);
        $.ajax({
            type: "PUT",
            url: "/api/v3/login_config/notification",
            contentType: 'application/json',
            data: JSON.stringify(data)
        }).done(function (xhr) {
            new PNotify({
                title: 'Updated',
                text: `Login notification updated successfully`,
                hide: true,
                delay: 2000,
                opacity: 1,
                type: 'success'
            });
            $('.modal').modal('hide');
           showConfig();
        }).fail(function (data) {
            new PNotify({
                title: `ERROR editing login notification`,
                text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                type: 'error',
                hide: true,
                icon: 'fa fa-warning',
                delay: 5000,
                opacity: 1
            });
        });
    });
    showConfig();
    enableNotificationBindCheckbox();
});

function showConfig() {
    $.ajax({
        type: "GET",
        url: "/api/v3/login_config",
    }).done(function (data) {
        $("#enable_cover_notification_checkbox").iCheck(data.notification_cover?.enabled ? 'check' : 'uncheck');
        $("#enable_form_notification_checkbox").iCheck(data.notification_form?.enabled ? 'check' : 'uncheck');
        renderLoginNotificationPreview("#LoginNotificationsPanel #preview-panel", data);
    });
}

enableNotificationBindCheckbox = () => {
    $("#enable_cover_notification_checkbox").on("ifChecked", () => {
        enableNotificationUpdateStatus("cover", true);
    });
    $("#enable_cover_notification_checkbox").on("ifUnchecked", () => {
        enableNotificationUpdateStatus("cover", false);
    });

    $("#enable_form_notification_checkbox").on("ifChecked", () => {
        enableNotificationUpdateStatus("form", true);
    });
    $("#enable_form_notification_checkbox").on("ifUnchecked", () => {
        enableNotificationUpdateStatus("form", false);
    });
}

enableNotificationUpdateStatus = (type, enabled) => {
    $.ajax({
        type: "PUT",
        url: "/api/v3/login_config/notification/" + type + "/enable",
        accept: "application/json",
        data: JSON.stringify({
            enabled: enabled
        }),
        contentType: 'application/json'
    }).done(() => {
        new PNotify({
            title: "Notification " + type + (enabled ? ' enabled' : ' disabled'),
            text: "",
            hide: true,
            delay: 1000,
            icon: 'fa fa-success',
            opacity: 1,
            type: 'success'
        });
        showConfig();
    }).fail(function (data) {
        new PNotify({
            title: `ERROR ${(enabled ? 'enabling' : 'disabling')} notification`,
            text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
            type: 'error',
            hide: true,
            icon: 'fa fa-warning',
            delay: 5000,
            opacity: 1
        });
    });
}
