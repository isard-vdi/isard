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
    'features': ['features']
};

function openXmlSections(domainId) {
    $('#xmlSectionsDomainId').val(domainId);
    $('#xmlSectionsContainer').html(
        '<div class="text-center"><i class="fa fa-spinner fa-pulse fa-2x"></i></div>'
    );
    $('#modalEditXmlSections').modal({backdrop: 'static', keyboard: false}).modal('show');

    // Fetch sections and capabilities in parallel
    $.when(
        $.ajax({type: "GET", url: "/api/v3/admin/domains/xml_sections/" + domainId}),
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
                    capsItems.push('<b>Usable CPU models:</b> ' + escapeHtml(usable.map(function(m) { return m.name; }).join(', ')));
                } else if (ck === 'features') {
                    if (val.hyperv) capsItems.push('<b>Hyper-V:</b> ' + escapeHtml(val.hyperv.join(', ')));
                } else if (ck === 'vcpu_max') {
                    capsItems.push('<b>Max vCPUs:</b> ' + escapeHtml(String(val)));
                } else if (Array.isArray(val)) {
                    var label = ck.replace(/_/g, ' ');
                    capsItems.push('<b>' + escapeHtml(label) + ':</b> ' + escapeHtml(val.join(', ')));
                }
            });
            if (capsItems.length > 0) {
                capsHtml = '<div class="xml-caps-info" style="margin-top: 4px; padding: 4px 8px; background: #fafafa; border: 1px solid #eee; border-radius: 3px; font-size: 11px; color: #666;">' +
                    '<i class="fa fa-info-circle"></i> ' + capsItems.join(' &nbsp;|&nbsp; ') + '</div>';
            }
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
                    '<textarea class="form-control xml-section-textarea" ' +
                        'data-key="' + safeKey + '" ' +
                        'rows="' + rows + '" ' +
                        'style="font-family: monospace; font-size: 12px; background-color: ' + bgColor + '; color: ' + textColor + '; resize: vertical;"' +
                        (isSystemLocked ? ' readonly' : '') +
                    '>' + escapeHtml(section.xml) + '</textarea>' +
                    capsHtml +
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
        url: '/api/v3/admin/domains/xml_sections/' + domainId,
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
        url: '/api/v3/admin/domains/xml_sections/' + domainId,
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
