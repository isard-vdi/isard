// UUID validation helper
function isValidUUID(str) {
    var uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    return uuidRegex.test(str);
}

function initDomainSearchModal(expectedKind) {
    var modal = "#modalSearchDomain";
    var itemName = expectedKind || "domain";
    $(modal + " #domain-info").hide();
    $(modal + "Form")[0].reset();

    $(modal + " #search-domain-btn").off("click").on("click", function () {
        var domainId = $(modal + " #domain-id").val().trim();
        if (!domainId) {
            new PNotify({
                title: "Error",
                text: "Please enter a " + itemName + " ID to search for.",
                type: "error",
                hide: true,
                delay: 3000,
                icon: "fa fa-warning",
                opacity: 1,
            });
            return;
        }

        // Validate UUID format
        if (!isValidUUID(domainId)) {
            new PNotify({
                title: "Invalid UUID",
                text: "Please enter a valid UUID format (e.g., xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx).",
                type: "error",
                hide: true,
                delay: 3000,
                icon: "fa fa-warning",
                opacity: 1,
            });
            return;
        }

        $.ajax({
            url: `/api/v3/admin/domain/search-info/${domainId}`,
            type: "GET",
            contentType: "application/json",
        }).done(function (data) {
            // Kind validation
            if (expectedKind && data.kind !== expectedKind) {
                new PNotify({
                    title: "Wrong Type",
                    text: "The UUID belongs to a " + data.kind + ", not a " + expectedKind + ".",
                    type: "error",
                    hide: true,
                    delay: 3000,
                    icon: "fa fa-warning",
                    opacity: 1,
                });
                $(modal + " #domain-info").hide();
                return;
            }

            function copyBtn(text) {
                return (text && text !== '-') ? ` <button class="btn btn-xs btn-primary btn-copy" data-copy-value="${text}" type="button" title="Copy to clipboard" style="margin-left:3px;margin-right:8px;"><i class="fa fa-clipboard"></i></button>` : '';
            }

            const domainFields = [
                { label: 'ID', value: data.id || '-', selector: '#domain-info-id' },
                { label: 'Name', value: data.name || '-', selector: '#domain-info-name' },
                { label: 'Status', value: data.status || '-', selector: '#domain-info-status' },
                { label: 'Storage', value: (data.create_dict && data.create_dict.hardware && data.create_dict.hardware.disks && data.create_dict.hardware.disks.length > 0) ? data.create_dict.hardware.disks.map(disk => disk.storage_id).join(", ") : '-', selector: '#domain-info-storage' },
                { label: 'Kind', value: (data.kind) || '-', selector: '#domain-info-kind' }
            ];
            domainFields.forEach(field => {
                const html = `${field.value}${copyBtn(field.value)}`;
                $(modal + ' ' + field.selector).html(html);
            });

            if (data.owner_data) {
                const ownerFields = [
                    { selector: '#domain-info-user', name: data.owner_data.username || '-', id: data.user || '-' },
                    { selector: '#domain-info-group', name: data.owner_data.group_name || '-', id: data.owner_data.group || '-' },
                    { selector: '#domain-info-category', name: data.owner_data.category_name || '-', id: data.owner_data.category || '-' }
                ];
                ownerFields.forEach(field => {
                    let html = `<b>Name: </b>${field.name}${copyBtn(field.name)}<br><b>ID: </b>${field.id}${copyBtn(field.id)}`;
                    $(modal + ' ' + field.selector).html(html);
                });
            } else {
                $(modal + ' #domain-info-category').text('-');
                $(modal + ' #domain-info-group').text('-');
                $(modal + ' #domain-info-user').html('<i>The user does not exist</i>');
            }
            $(modal + " #domain-info").show();
        }).fail(function (xhr) {
            var msg;
            if (xhr.status === 404) {
                msg = itemName.charAt(0).toUpperCase() + itemName.slice(1) + " with UUID '" + domainId + "' not found.";
            } else if (xhr.responseJSON && xhr.responseJSON.description) {
                msg = xhr.responseJSON.description;
            } else {
                msg = "An error occurred while searching for the " + itemName + ".";
            }
            new PNotify({
                title: "Error",
                text: msg,
                type: "error",
                hide: true,
                delay: 3000,
                icon: "fa fa-warning",
                opacity: 1,
            });
            $(modal + " #domain-info").hide();
        });
    });

    $(modal).modal({ backdrop: "static", keyboard: false }).modal("show");
}
