function initDomainSearchModal() {
    var modal = "#modalSearchDomain";
    $(modal + " #domain-info").hide();
    $(modal + "Form")[0].reset();

    $(modal + " #search-domain-btn").off("click").on("click", function () {
        var domainId = $(modal + " #domain-id").val();
        if (!domainId) {
            new PNotify({
                title: "Error",
                text: "Please enter a domain ID to search for.",
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
            var msg = xhr.responseJSON && xhr.responseJSON.description ? xhr.responseJSON.description : "ERROR: Something went wrong";
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
