$(document).ready(function () {
    $("#btnEditLoginNotification").on("click", function () {
        var modal = "#modalEditLoginNotification";
        $.ajax({
            type: "GET",
            url: "/api/v3/login_config",
        }).done(function (data) {
            ["cover", "form"].forEach(position => {
                $(modal + ` #${position}_enabled`).iCheck(data[`notification_${position}`]?.enabled ? 'check' : 'uncheck');
                $(modal + ` #${position}_icon`).val(data[`notification_${position}`]?.icon || 'null');
                $(modal + ` #${position}_title`).val(data[`notification_${position}`]?.title);
                $(modal + ` #${position}_description`).val(data[`notification_${position}`]?.description);
                $(modal + ` #${position}_link_url`).val(data[`notification_${position}`]?.button?.url);
                $(modal + ` #${position}_link_text`).val(data[`notification_${position}`]?.button?.text);
                $(modal + ` #${position}_link_styles`).val(data[`notification_${position}`]?.button?.extra_styles);
                $(modal + ` #${position}_background_styles`).val(data[`notification_${position}`]?.extra_styles);

                handleIconChange(modal, position);
                handleUseDefaultColor(modal, position);

                const linkStyles = data[`notification_${position}`]?.button?.extra_styles || '';
                const linkColorMatch = linkStyles.match(/color:([^;]+)/);
                const linkColor = linkColorMatch ? linkColorMatch[1].trim() : '#114955';
                $(modal + ` #${position}_link_color`).val(linkColor);

                const backgroundStyles = data[`notification_${position}`]?.extra_styles || '';
                const backgroundColorMatch = backgroundStyles.match(/background-color:([^;]+)/);
                const backgroundColor = backgroundColorMatch ? backgroundColorMatch[1].trim() : '#FFFFFF';
                $(modal + ` #${position}_background_color`).val(backgroundColor);
            });
        });
        $(modal).modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');
    });

    $("#modalEditLoginNotification #send").on("click", function () {
        var form = $('#modalEditLoginNotificationForm');
        data = form.serializeObject();
        form.parsley().validate();
        data = {
            cover: {
                icon: data.cover_icon !== 'null' ? data.cover_icon : '',
                title: data.cover_title,
                description: data.cover_description,
                extra_styles: `background-color: ${data.cover_background_color};`,
                button: {
                    url: data.cover_link_url,
                    text: data.cover_link_text,
                    extra_styles: `color: ${data.cover_link_color};`
                }
            },
            form: {
                icon: data.form_icon !== 'null' ? data.form_icon : '',
                title: data.form_title,
                description: data.form_description,
                extra_styles: `background-color: ${data.form_background_color};`,
                button: {
                    url: data.form_link_url,
                    text: data.form_link_text,
                    extra_styles: `color: ${data.form_link_color};`
                }
            }
        };
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

const mapIconChange = {
    "alert-triangle": "exclamation-triangle",
    "info-circle": "info-circle",
    "tool-01": "wrench",
}

function handleUseDefaultColor(modal, position) {
    $(`${modal} #${position}-panel .btn-default-link-color`).off('click').on("click", function () {
        $(`${modal} #${position}_link_color`).val('#114955')
    });
    $(`${modal} #${position}-panel .btn-default-background-color`).off('click').on("click", function () {
        $(`${modal} #${position}_background_color`).val('#FFFFFF')
    })
}

function handleIconChange(modal, position) {
    $(`${modal} #${position}_icon`).off('change').on("change", function () {
        var icon = $(this).val();
        if (icon) {
            icon = mapIconChange[icon];
            if (!icon || icon == "null") {
                $(`${modal} #${position}-panel #icon_display`).hide();
            } else {
                $(`${modal} #${position}-panel #icon_display`).show().removeClass(function (index, className) {
                    return (className.match(/(^|\s)fa-\S+/g) || []).join(' ');
                }).addClass(`fa fa-${icon}`);
            }
        } else {
            $(`${modal} #${position}-panel #icon_display`).hide();
        }
    });
    $(`${modal} #${position}_icon`).trigger('change');
}

function showConfig() {
    $.ajax({
        type: "GET",
        url: "/api/v3/login_config",
    }).done(function (data) {
        $("#enable_cover_notification_checkbox").iCheck(data.notification_cover?.enabled ? 'check' : 'uncheck');
        $("#enable_form_notification_checkbox").iCheck(data.notification_form?.enabled ? 'check' : 'uncheck');
        var previewHtml = createNotificationPreview(data.notification_cover, 'cover') + createNotificationPreview(data.notification_form, 'form');
        $("#LoginNotificationsPanel #preview-panel").html(previewHtml);
    });
}

function createNotificationPreview (notification, position) {
    if (notification?.description || notification?.title || notification?.button?.text) {
    return `
        <div id="${position}_panel" class="x_panel col-md-6 col-sm-6 col-xs-12 ${notification?.enabled == false ? "disabled-preview" : ''}" style="${notification?.extra_styles}">
        <small>${notification?.icon ? `<i class="roundbox fa fa-${mapIconChange[notification.icon]}"></i>` : ""}</small>
        <b id="preview_${position}_title">${notification?.title}</b>
        <p class="notification-body" id="preview_${position}_description">${notification?.description}</p>
        <a class="notification-body" href="${notification?.button?.url}" style="${notification?.button?.extra_styles}">${notification?.button?.text}</a>
        </div>
    `;
    } else {
    return `<div class="col-md-6 col-sm-6 col-xs-12"><i><h4> No ${position} notification available</h4></i></div>`;
    }
};



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