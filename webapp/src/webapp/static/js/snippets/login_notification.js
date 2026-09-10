/*
 *   Copyright © 2024 Pau Abril Iranzo
 *   Copyright © 2026 Josep Maria Viñolas Auquer
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

function escapeHtml(str) {
    if (str == null) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

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

function createNotificationPreview (notification, position) {
    if (notification?.description || notification?.title || notification?.button?.text) {
    return `
        <div id="${position}_panel" class="x_panel col-md-6 col-sm-6 col-xs-12 ${notification?.enabled == false ? "disabled-preview" : ''}" style="${notification?.extra_styles}">
        <small>${notification?.icon ? `<i class="roundbox fa fa-${mapIconChange[notification.icon]}"></i>` : ""}</small>
        <b id="preview_${position}_title">${escapeHtml(notification?.title)}</b>
        <p class="notification-body" id="preview_${position}_description">${escapeHtml(notification?.description)}</p>
        <a class="notification-body" href="${escapeHtml(notification?.button?.url)}" style="${notification?.button?.extra_styles}">${escapeHtml(notification?.button?.text)}</a>
        </div>
    `;
    } else {
    return `<div class="col-md-6 col-sm-6 col-xs-12"><i><h4> No ${position} notification available</h4></i></div>`;
    }
};

function populateLoginNotificationForm(modal, data, enableCheckboxPrefix) {
    ["cover", "form"].forEach(position => {
        if (enableCheckboxPrefix) {
            $(modal + ` #${enableCheckboxPrefix}${position}_notification_checkbox`).iCheck(data[`notification_${position}`]?.enabled ? 'check' : 'uncheck');
        }
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
}

function collectLoginNotificationData($form, enableCheckboxPrefix) {
    data = $form.serializeObject();
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
    if (enableCheckboxPrefix) {
        var modal = $form.closest('.modal');
        ["cover", "form"].forEach(position => {
            data[position].enabled = modal
                .find(`#${enableCheckboxPrefix}${position}_notification_checkbox`)
                .is(":checked");
        });
    }
    return data;
}

function renderLoginNotificationPreview(containerSelector, data) {
    var previewHtml = createNotificationPreview(data.notification_cover, 'cover') + createNotificationPreview(data.notification_form, 'form');
    $(containerSelector).html(previewHtml);
}
