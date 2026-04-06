// XML Sections Editor for IsardVDI admin
// Splits domain XML into discrete snippets with engine override control

// Map section keys to capabilities fields
var SECTION_CAPS_MAP = {
    'vcpus': ['vcpu_max'],
    'cpu': ['cpu_modes', 'cpu_models'],
    'boot_order': ['os_firmware'],
    'disks': ['disk_buses', 'disk_devices'],
    'isos': ['disk_devices'],
    'video': ['video_models'],
    'graphics': ['graphics_types'],
    'hostdev': ['hostdev_subsys_types'],
    'rng': ['rng_models'],
    'filesystem': ['filesystem_drivers'],
    'channels': ['channel_types'],
    'network': ['interface_backends'],
    'redirdev': ['redirdev_buses'],
    'features': ['features'],
    'tpm': ['tpm_models', 'tpm_backend_versions'],
    'audio': ['audio_types'],
    'serial': ['serial_target_types'],
    'watchdog': ['watchdog_models', 'watchdog_actions']
};

// Global state for XML sections editor mode
var xmlSectionsMode = 'domain'; // 'domain' or 'virt_install'

function xmlSectionsApiUrl(id) {
    if (xmlSectionsMode === 'virt_install') {
        return '/api/v3/admin/virt_install/xml_sections/' + id;
    }
    return '/api/v3/admin/domains/xml_sections/' + id;
}

function openXmlSections(domainId, mode) {
    xmlSectionsMode = mode || 'domain';
    $('#xmlSectionsDomainId').val(domainId);
    $('#xmlSectionsContainer').html(
        '<div class="text-center"><i class="fa fa-spinner fa-pulse fa-2x"></i></div>'
    );
    // Hide virt_install-specific buttons when editing virt_install directly
    if (xmlSectionsMode === 'virt_install') {
        $('#xmlSectionsSaveVirtInstall').hide();
    } else {
        $('#xmlSectionsSaveVirtInstall').show();
    }
    $('#modalEditXmlSections').modal({backdrop: 'static', keyboard: false}).modal('show');

    // Fetch sections and capabilities in parallel
    $.when(
        $.ajax({type: "GET", url: xmlSectionsApiUrl(domainId)}),
        $.ajax({type: "GET", url: "/api/v3/admin/domains/xml_capabilities"})
    ).done(function(sectionsResp, capsResp) {
        renderXmlSections(sectionsResp[0].sections, capsResp[0]);
    }).fail(function(data) {
        $('#xmlSectionsContainer').html(
            '<div class="alert alert-danger">Failed to load XML sections: ' +
            escapeHtml(data.responseJSON ? data.responseJSON.description : 'Something went wrong') +
            '</div>'
        );
    });
}

function renderXmlSections(sections, capabilities) {
    var container = $('#xmlSectionsContainer');
    container.empty();
    capabilities = capabilities || {};

    // Build grouped dropdown nav bar (all sections, including empty)
    var groups = {};
    var groupOrder = [];
    sections.forEach(function(section) {
        var group = section.group || 'Other';
        if (!groups[group]) {
            groups[group] = [];
            groupOrder.push(group);
        }
        groups[group].push(section);
    });

    var navHtml = '<div id="xmlSectionsNav" style="position: sticky; top: 0; z-index: 10; background: #fff; padding: 4px; border-bottom: 1px solid #ddd; margin-bottom: 10px;">';
    groupOrder.forEach(function(group) {
        var safeGroup = escapeHtml(group);
        var items = groups[group];
        if (items.length === 1) {
            // Single-item group: direct link, no dropdown
            var s = items[0];
            navHtml += '<a href="#xml-section-' + escapeHtml(s.key) + '" class="btn btn-xs btn-default xml-nav-link" ' +
                'data-target="xml-section-' + escapeHtml(s.key) + '" style="margin: 1px 2px; font-size: 11px;">' +
                safeGroup + '</a>';
        } else {
            // Multi-item group: dropdown
            navHtml += '<div class="btn-group" style="margin: 1px 2px;">' +
                '<button type="button" class="btn btn-xs btn-default dropdown-toggle" data-toggle="dropdown" style="font-size: 11px;">' +
                safeGroup + ' <span class="caret"></span></button>' +
                '<ul class="dropdown-menu" style="font-size: 12px;">';
            items.forEach(function(s) {
                var isEmpty = !s.xml || !s.xml.trim();
                var dimStyle = isEmpty ? ' style="color: #aaa;"' : '';
                var emptyTag = isEmpty ? ' <small>(empty)</small>' : '';
                navHtml += '<li><a href="#xml-section-' + escapeHtml(s.key) + '" class="xml-nav-link" ' +
                    'data-target="xml-section-' + escapeHtml(s.key) + '"' + dimStyle + '>' +
                    escapeHtml(s.label) + emptyTag + '</a></li>';
            });
            navHtml += '</ul></div>';
        }
    });
    navHtml += '<span style="float: right;">' +
        '<label class="btn btn-xs btn-warning" style="margin: 1px 2px; font-size: 11px; cursor: pointer;">' +
        '<i class="fa fa-upload"></i> Upload XML' +
        '<input type="file" id="xmlUploadFile" accept=".xml" style="display: none;">' +
        '</label></span>';
    navHtml += '</div>';
    container.append(navHtml);

    // Handle nav link clicks (smooth scroll within modal body)
    container.on('click', '.xml-nav-link', function(e) {
        e.preventDefault();
        var targetId = $(this).data('target');
        var target = document.getElementById(targetId);
        if (target) {
            // Scroll the modal body, not the page
            var modalBody = $('#modalEditXmlSections .modal-body')[0];
            if (modalBody) {
                var offset = target.offsetTop - modalBody.offsetTop - 50;
                modalBody.scrollTo({top: offset, behavior: 'smooth'});
            }
            // Brief highlight to show which section was navigated to
            $(target).css('box-shadow', '0 0 8px rgba(51,122,183,0.6)');
            setTimeout(function() { $(target).css('box-shadow', ''); }, 1500);
        }
        // Close dropdown after clicking
        $(this).closest('.btn-group').find('.dropdown-toggle').dropdown('toggle');
    });

    // Handle XML file upload
    container.on('change', '#xmlUploadFile', function(e) {
        var file = e.target.files[0];
        if (!file) return;

        var reader = new FileReader();
        reader.onload = function(ev) {
            var xmlContent = ev.target.result;

            $.ajax({
                type: 'POST',
                url: '/api/v3/admin/domains/xml_sections/parse',
                data: JSON.stringify({xml: xmlContent}),
                contentType: 'application/json',
                success: function(resp) {
                    var updated = [];
                    var skipped = [];
                    resp.sections.forEach(function(section) {
                        if (!section.key || !/^[a-z_]+$/.test(section.key)) return;
                        var panel = $('#xml-section-' + section.key);
                        if (!panel.length) return;
                        var hiddenInput = panel.find('.xml-section-protect');
                        if (hiddenInput.length === 0) {
                            skipped.push(escapeHtml(section.label) + ' (system-locked)');
                            return;
                        }
                        if (hiddenInput.val() === '1') {
                            skipped.push(escapeHtml(section.label) + ' (admin-locked)');
                            return;
                        }
                        panel.find('.xml-section-textarea').val(section.xml);
                        updated.push(escapeHtml(section.label));
                    });

                    var msg = '';
                    if (updated.length) msg += '<b>Updated:</b> ' + updated.join(', ');
                    if (skipped.length) msg += (msg ? '<br>' : '') + '<b>Skipped (locked):</b> ' + skipped.join(', ');
                    if (!updated.length && !skipped.length) msg = 'No sections found in the uploaded XML.';

                    new PNotify({
                        title: 'XML Uploaded',
                        text: msg,
                        type: updated.length ? 'success' : 'info',
                        hide: true,
                        delay: 6000,
                        icon: 'fa fa-upload'
                    });
                },
                error: function(data) {
                    new PNotify({
                        title: 'Upload Error',
                        text: data.responseJSON ? escapeHtml(data.responseJSON.description) : 'Failed to parse uploaded XML',
                        type: 'error',
                        hide: true,
                        delay: 5000,
                        icon: 'fa fa-warning'
                    });
                }
            });
        };
        reader.readAsText(file);
        $(this).val('');
    });

    // Render section panels
    sections.forEach(function(section) {
        var isProtectable = section.protectable;
        var isProtected = section.protected;
        var isSystemLocked = !isProtectable;
        var hasContent = section.xml && section.xml.trim().length > 0;

        var lineCount = hasContent ? section.xml.split('\n').length : 1;
        var rows = Math.max(2, Math.min(lineCount + 1, 15));

        var safeKey = escapeHtml(section.key);
        var safeLabel = escapeHtml(section.label);

        // Lock toggle HTML (right side)
        var lockHtml = '';
        if (isSystemLocked) {
            lockHtml = '<span class="xml-lock-display" style="color: #856404; cursor: default;">' +
                '<i class="fa fa-lock"></i> <small>Always locked</small></span>';
        } else if (isProtected) {
            lockHtml = '<span class="xml-lock-toggle" style="color: #28a745; cursor: pointer;" title="Click to unlock">' +
                '<i class="fa fa-lock"></i> <small>Locked</small></span>' +
                '<input type="hidden" class="xml-section-protect" data-key="' + safeKey + '" value="1">';
        } else {
            lockHtml = '<span class="xml-lock-toggle" style="color: #999; cursor: pointer;" title="Click to lock">' +
                '<i class="fa fa-unlock"></i> <small>Unlocked</small></span>' +
                '<input type="hidden" class="xml-section-protect" data-key="' + safeKey + '" value="0">';
        }

        // Color scheme: blue=system-locked, white=unlocked, light-gray=admin-locked
        var borderColor, bgColor, textColor;
        if (isSystemLocked) {
            borderColor = '#b8daff';
            bgColor = '#e8f0fe';
            textColor = '#6c757d';
        } else if (isProtected) {
            borderColor = '#c3e6cb';
            bgColor = '#f0f0f0';
            textColor = '#333';
        } else {
            borderColor = '#ddd';
            bgColor = '#fff';
            textColor = '#333';
        }

        // Build capabilities info for this section
        var capsHtml = '';
        var capsKeys = SECTION_CAPS_MAP[section.key];
        if (capsKeys && Object.keys(capabilities).length > 0) {
            var capsItems = [];
            capsKeys.forEach(function(ck) {
                var val = capabilities[ck];
                if (!val) return;
                if (ck === 'cpu_models') {
                    var usable = val.filter(function(m) { return m.usable; });
                    capsItems.push('<li><b>Usable CPU models:</b> ' + escapeHtml(usable.map(function(m) { return m.name; }).join(', ')) + '</li>');
                } else if (ck === 'features') {
                    if (val.hyperv) capsItems.push('<li><b>Hyper-V:</b> ' + escapeHtml(val.hyperv.join(', ')) + '</li>');
                } else if (ck === 'vcpu_max') {
                    capsItems.push('<li><b>Max vCPUs:</b> ' + escapeHtml(String(val)) + '</li>');
                } else if (Array.isArray(val)) {
                    var label = ck.replace(/_/g, ' ');
                    capsItems.push('<li><b>' + escapeHtml(label) + ':</b> ' + escapeHtml(val.join(', ')) + '</li>');
                }
            });
            if (capsItems.length > 0) {
                capsHtml = '<div class="xml-caps-sidebar" style="padding: 6px 8px; background: #fafafa; ' +
                    'border: 1px solid #eee; border-radius: 3px; font-size: 11px; color: #666; ' +
                    'height: 100%; overflow-y: auto;">' +
                    '<div style="font-weight: bold; margin-bottom: 4px;">' +
                    '<i class="fa fa-info-circle"></i> Available Options</div>' +
                    '<ul style="padding-left: 16px; margin: 0;">' +
                    capsItems.join('') +
                    '</ul></div>';
            }
        }

        var textareaHtml =
            '<textarea class="form-control xml-section-textarea" ' +
                'data-key="' + safeKey + '" ' +
                'rows="' + rows + '" ' +
                'style="font-family: monospace; font-size: 12px; background-color: ' + bgColor + '; color: ' + textColor + '; resize: vertical; width: 100%;"' +
                (isSystemLocked ? ' readonly' : '') +
            '>' + escapeHtml(section.xml) + '</textarea>';

        var contentHtml;
        if (capsHtml) {
            contentHtml =
                '<div style="display: flex; align-items: stretch; gap: 5px;">' +
                    '<div style="flex: 2; min-width: 0;">' + textareaHtml + '</div>' +
                    '<div style="flex: 1; min-width: 180px;">' + capsHtml + '</div>' +
                '</div>';
        } else {
            contentHtml = textareaHtml;
        }

        var panelHtml =
            '<div class="x_panel xml-section-panel" id="xml-section-' + safeKey + '" ' +
                'data-section-key="' + safeKey + '" ' +
                'style="margin-bottom: 8px; border: 1px solid ' + borderColor + ';">' +
                '<div class="x_title" style="padding: 5px 10px; margin-bottom: 0; border-bottom: 1px solid #eee;">' +
                    '<div style="display: flex; align-items: center; justify-content: space-between;">' +
                        '<div>' +
                            '<strong>' + safeLabel + '</strong>' +
                            ' <code class="text-muted" style="font-size: 11px;">' + safeKey + '</code>' +
                        '</div>' +
                        '<div>' + lockHtml + '</div>' +
                    '</div>' +
                '</div>' +
                '<div class="x_content" style="padding: 5px;">' +
                    contentHtml +
                '</div>' +
            '</div>';

        container.append(panelHtml);
    });

    // Handle lock/unlock toggle clicks
    container.on('click', '.xml-lock-toggle', function() {
        var panel = $(this).closest('.xml-section-panel');
        var textarea = panel.find('.xml-section-textarea');
        var hiddenInput = panel.find('.xml-section-protect');
        var isLocked = hiddenInput.val() === '1';

        if (isLocked) {
            // Unlock
            hiddenInput.val('0');
            $(this).css('color', '#999').attr('title', 'Click to lock');
            $(this).html('<i class="fa fa-unlock"></i> <small>Unlocked</small>');
            panel.css('border-color', '#ddd');
            textarea.css({'background-color': '#fff', 'color': '#333'});
        } else {
            // Lock
            hiddenInput.val('1');
            $(this).css('color', '#28a745').attr('title', 'Click to unlock');
            $(this).html('<i class="fa fa-lock"></i> <small>Locked</small>');
            panel.css('border-color', '#c3e6cb');
            textarea.css({'background-color': '#f0f0f0', 'color': '#333'});
        }
    });
}

function collectXmlSections() {
    var sections = {};
    var protectedSections = [];

    $('.xml-section-panel').each(function() {
        var key = $(this).data('section-key');
        var textarea = $(this).find('.xml-section-textarea');
        var hiddenInput = $(this).find('.xml-section-protect');

        if (hiddenInput.length > 0) {
            sections[key] = textarea.val();
            if (hiddenInput.val() === '1') {
                protectedSections.push(key);
            }
        }
    });

    return {
        sections: sections,
        xml_protected_sections: protectedSections
    };
}

function escapeHtml(text) {
    if (!text) return '';
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// Validate button
$(document).on('click', '#xmlSectionsValidate', function() {
    var domainId = $('#xmlSectionsDomainId').val();
    var data = collectXmlSections();
    var notice = new PNotify({
        text: 'Validating XML...',
        hide: false,
        opacity: 1,
        icon: 'fa fa-spinner fa-pulse'
    });

    $.ajax({
        type: 'POST',
        url: xmlSectionsApiUrl(domainId),
        data: JSON.stringify(data),
        contentType: 'application/json',
        success: function(resp) {
            notice.update({
                title: 'Valid',
                text: 'XML is well-formed and sections merged successfully',
                type: 'success',
                hide: true,
                delay: 3000,
                icon: 'fa fa-check',
                opacity: 1
            });
        },
        error: function(data) {
            notice.update({
                title: 'Validation Error',
                text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                type: 'error',
                hide: true,
                delay: 8000,
                icon: 'fa fa-warning',
                opacity: 1
            });
        }
    });
});

// Save button
$(document).on('click', '#xmlSectionsSave', function() {
    var domainId = $('#xmlSectionsDomainId').val();
    var data = collectXmlSections();
    var notice = new PNotify({
        text: 'Updating XML sections...',
        hide: false,
        opacity: 1,
        icon: 'fa fa-spinner fa-pulse'
    });

    $.ajax({
        type: 'POST',
        url: xmlSectionsApiUrl(domainId),
        data: JSON.stringify(data),
        contentType: 'application/json',
        success: function(resp) {
            $('#modalEditXmlSections').modal('hide');
            notice.update({
                title: 'Updated',
                text: 'Domain XML sections updated successfully',
                type: 'success',
                hide: true,
                delay: 2000,
                icon: 'fa fa-check',
                opacity: 1
            });
        },
        error: function(data) {
            notice.update({
                title: 'ERROR updating XML',
                text: data.responseJSON ? data.responseJSON.description : 'Something went wrong',
                type: 'error',
                hide: true,
                delay: 5000,
                icon: 'fa fa-warning',
                opacity: 1
            });
        }
    });
});

// Download XML button
$(document).on('click', '#xmlSectionsDownload', function() {
    var domainId = $('#xmlSectionsDomainId').val();
    var data = collectXmlSections();
    var notice = new PNotify({
        text: 'Merging XML for download...',
        hide: false,
        opacity: 1,
        icon: 'fa fa-spinner fa-pulse'
    });

    $.ajax({
        type: 'POST',
        url: xmlSectionsApiUrl(domainId),
        data: JSON.stringify(data),
        contentType: 'application/json',
        success: function(resp) {
            notice.remove();
            var blob = new Blob([resp.xml], {type: 'application/xml'});
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = domainId + '.xml';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        },
        error: function(data) {
            notice.update({
                title: 'Download Error',
                text: data.responseJSON ? data.responseJSON.description : 'Failed to merge XML',
                type: 'error',
                hide: true,
                delay: 5000,
                icon: 'fa fa-warning',
                opacity: 1
            });
        }
    });
});

// Save as virt_install button — open name prompt
$(document).on('click', '#xmlSectionsSaveVirtInstall', function() {
    $('#virtInstallName').val('');
    $('#modalVirtInstallName').modal('show');
});

// Confirm save as virt_install
$(document).on('click', '#virtInstallNameConfirm', function() {
    var name = $('#virtInstallName').val().trim();
    if (!name) {
        new PNotify({
            title: 'Error',
            text: 'Please enter a name',
            type: 'error',
            hide: true,
            delay: 3000,
            opacity: 1
        });
        return;
    }

    var domainId = $('#xmlSectionsDomainId').val();
    var data = collectXmlSections();
    data.name = name;

    var notice = new PNotify({
        text: 'Saving as virt_install...',
        hide: false,
        opacity: 1,
        icon: 'fa fa-spinner fa-pulse'
    });

    $.ajax({
        type: 'POST',
        url: '/api/v3/admin/domains/xml_sections/' + domainId + '/save_virt_install',
        data: JSON.stringify(data),
        contentType: 'application/json',
        success: function(resp) {
            $('#modalVirtInstallName').modal('hide');
            notice.update({
                title: 'Saved',
                text: 'virt_install "' + escapeHtml(resp.name) + '" created (ID: ' + escapeHtml(resp.id) + ')',
                type: 'success',
                hide: true,
                delay: 4000,
                icon: 'fa fa-check',
                opacity: 1
            });
        },
        error: function(data) {
            notice.update({
                title: 'Error',
                text: data.responseJSON ? data.responseJSON.description : 'Failed to save virt_install',
                type: 'error',
                hide: true,
                delay: 5000,
                icon: 'fa fa-warning',
                opacity: 1
            });
        }
    });
});
