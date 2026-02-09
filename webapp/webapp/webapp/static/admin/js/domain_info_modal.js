/**
 * Domain Info Modal - Reusable component for displaying domain details
 *
 * Usage:
 *   1. Include this script in your page: <script src="/isard-admin/static/admin/js/domain_info_modal.js"></script>
 *   2. Call showDomainInfo(domainId) to open the modal programmatically
 *   3. Or add data-domain-info="<domain_id>" to any clickable element for auto-binding
 *
 * Example:
 *   <button class="btn btn-xs btn-info" data-domain-info="abc123"><i class="fa fa-info-circle"></i></button>
 *
 * The modal displays:
 *   - Domain details: ID, name, kind, status, hypervisor, deployment, storage, description
 *   - Owner details: username, name, role, category, group, email
 *   - Network interfaces: name, MAC address
 */
(function(window, $) {
    'use strict';

    var MODAL_ID = 'domain-info-modal';

    var MODAL_HTML = [
        '<div class="modal fade" id="' + MODAL_ID + '" tabindex="-1" role="dialog">',
        '  <div class="modal-dialog modal-lg" role="document">',
        '    <div class="modal-content">',
        '      <div class="modal-header">',
        '        <button type="button" class="close" data-dismiss="modal">&times;</button>',
        '        <h4 class="modal-title"><i class="fa fa-desktop"></i> <span id="domain-info-title">Domain Information</span></h4>',
        '      </div>',
        '      <div class="modal-body">',
        '        <div id="domain-info-loading" class="text-center" style="padding: 40px;">',
        '          <i class="fa fa-spinner fa-spin fa-3x"></i>',
        '          <p style="margin-top: 15px;">Loading domain information...</p>',
        '        </div>',
        '        <div id="domain-info-content" style="display:none;">',
        '          <div class="row">',
        '            <div class="col-md-6">',
        '              <h5><i class="fa fa-desktop"></i> Domain Details</h5>',
        '              <table class="table table-condensed table-striped">',
        '                <tbody id="domain-info-table"></tbody>',
        '              </table>',
        '            </div>',
        '            <div class="col-md-6">',
        '              <h5><i class="fa fa-user"></i> Owner Details</h5>',
        '              <table class="table table-condensed table-striped">',
        '                <tbody id="owner-info-table"></tbody>',
        '              </table>',
        '            </div>',
        '          </div>',
        '          <div class="row">',
        '            <div class="col-md-12">',
        '              <h5><i class="fa fa-plug"></i> Network Interfaces</h5>',
        '              <table class="table table-condensed table-striped">',
        '                <thead>',
        '                  <tr>',
        '                    <th>Network</th>',
        '                    <th>ID</th>',
        '                    <th>MAC Address</th>',
        '                  </tr>',
        '                </thead>',
        '                <tbody id="interfaces-info-table"></tbody>',
        '              </table>',
        '            </div>',
        '          </div>',
        '          <div class="row" id="bastion-section" style="display:none;">',
        '            <div class="col-md-12">',
        '              <h5><i class="fa fa-globe"></i> Bastion Access</h5>',
        '              <table class="table table-condensed table-striped">',
        '                <tbody id="bastion-info-table"></tbody>',
        '              </table>',
        '            </div>',
        '          </div>',
        '        </div>',
        '        <div id="domain-info-error" class="alert alert-danger" style="display:none;"></div>',
        '      </div>',
        '      <div class="modal-footer">',
        '        <button type="button" class="btn btn-default" data-dismiss="modal">Close</button>',
        '      </div>',
        '    </div>',
        '  </div>',
        '</div>',
        '<style>',
        '.copy-btn { cursor: pointer; opacity: 0.6; margin-left: 5px; }',
        '.copy-btn:hover { opacity: 1; }',
        '.copyable-text { font-family: monospace; font-size: 11px; word-break: break-all; }',
        '</style>'
    ].join('\n');

    function ensureModalExists() {
        if ($('#' + MODAL_ID).length === 0) {
            $('body').append(MODAL_HTML);
            // Bind copy handlers
            $(document).on('click', '.copy-btn', function(e) {
                e.preventDefault();
                e.stopPropagation();
                var text = $(this).data('copy');
                copyToClipboard(text);
                // Visual feedback
                var icon = $(this).find('i');
                icon.removeClass('fa-copy').addClass('fa-check');
                setTimeout(function() {
                    icon.removeClass('fa-check').addClass('fa-copy');
                }, 1500);
            });
        }
    }

    function copyToClipboard(text) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text);
        } else {
            // Fallback for older browsers
            var textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
        }
    }

    function showLoading() {
        var $modal = $('#' + MODAL_ID);
        $modal.find('#domain-info-loading').show();
        $modal.find('#domain-info-content').hide();
        $modal.find('#domain-info-error').hide();
        $modal.find('#domain-info-title').text('Domain Information');
    }

    function showError(message) {
        var $modal = $('#' + MODAL_ID);
        $modal.find('#domain-info-loading').hide();
        $modal.find('#domain-info-content').hide();
        $modal.find('#domain-info-error').text(message).show();
    }

    function escapeHtml(text) {
        if (!text) return '';
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // Add a row with plain text value (will be escaped)
    function addRowText(table, label, value) {
        var displayValue = value ? escapeHtml(value) : '-';
        table.append('<tr><th style="width:35%">' + escapeHtml(label) + '</th><td>' + displayValue + '</td></tr>');
    }

    // Add a row with pre-formatted HTML value (not escaped)
    function addRowHtml(table, label, html) {
        table.append('<tr><th style="width:35%">' + escapeHtml(label) + '</th><td>' + html + '</td></tr>');
    }

    // Format a copyable ID/UUID field
    function formatCopyable(value) {
        if (!value) return '-';
        var escaped = escapeHtml(value);
        return '<span class="copyable-text">' + escaped + '</span>' +
               '<span class="copy-btn" data-copy="' + escaped + '" title="Copy to clipboard">' +
               '<i class="fa fa-copy"></i></span>';
    }

    // Format a copyable code field (monospace, smaller)
    function formatCode(value) {
        if (!value) return '-';
        return '<code>' + escapeHtml(value) + '</code>' +
               '<span class="copy-btn" data-copy="' + escapeHtml(value) + '" title="Copy to clipboard">' +
               '<i class="fa fa-copy"></i></span>';
    }

    // Format an external link that opens in a new tab
    function formatExternalLink(url, text) {
        if (!url) return '-';
        return '<a href="' + escapeHtml(url) + '" target="_blank">' +
               escapeHtml(text || url) + ' <i class="fa fa-external-link"></i></a>';
    }

    function formatStatus(status) {
        var statusClasses = {
            'Started': 'label-success',
            'Stopped': 'label-default',
            'Failed': 'label-danger',
            'Starting': 'label-info',
            'Stopping': 'label-warning',
            'Creating': 'label-info',
            'CreatingDisk': 'label-info',
            'Shutting-down': 'label-warning'
        };
        var cls = statusClasses[status] || 'label-default';
        return '<span class="label ' + cls + '">' + escapeHtml(status || 'Unknown') + '</span>';
    }

    function formatRole(role) {
        var roleClasses = {
            'admin': 'label-danger',
            'manager': 'label-warning',
            'advanced': 'label-info',
            'user': 'label-default'
        };
        var cls = roleClasses[role] || 'label-default';
        return '<span class="label ' + cls + '">' + escapeHtml(role || 'Unknown') + '</span>';
    }

    function showContent(data) {
        var $modal = $('#' + MODAL_ID);
        $modal.find('#domain-info-loading').hide();
        $modal.find('#domain-info-error').hide();

        var domain = data.domain || {};
        var owner = data.owner || {};

        // Update title
        $modal.find('#domain-info-title').text(domain.name || 'Domain Information');

        // Populate domain info
        var domainTable = $modal.find('#domain-info-table');
        domainTable.empty();
        addRowHtml(domainTable, 'ID', formatCopyable(domain.id));
        addRowText(domainTable, 'Name', domain.name);
        addRowText(domainTable, 'Kind', domain.kind);
        addRowHtml(domainTable, 'Status', formatStatus(domain.status));
        if (domain.hyp_started) {
            addRowText(domainTable, 'Hypervisor', domain.hyp_started);
        }
        if (domain.guest_ip) {
            addRowHtml(domainTable, 'Guest IP', formatCode(domain.guest_ip));
        }
        if (domain.deployment_name) {
            addRowText(domainTable, 'Deployment', domain.deployment_name);
        }
        if (domain.storage_id) {
            addRowHtml(domainTable, 'Storage ID', formatCopyable(domain.storage_id));
        }
        if (domain.description) {
            addRowText(domainTable, 'Description', domain.description);
        }

        // Populate owner info
        var ownerTable = $modal.find('#owner-info-table');
        ownerTable.empty();
        if (owner.id) {
            addRowHtml(ownerTable, 'User ID', formatCopyable(owner.id));
            addRowText(ownerTable, 'Username', owner.username);
            addRowText(ownerTable, 'Name', owner.name);
            addRowHtml(ownerTable, 'Role', formatRole(owner.role_id));
            addRowText(ownerTable, 'Category', owner.category_name || owner.category_id);
            addRowText(ownerTable, 'Group', owner.group_name || owner.group_id);
            if (owner.email) {
                addRowText(ownerTable, 'Email', owner.email);
            }
        } else {
            ownerTable.append('<tr><td colspan="2" class="text-muted">No owner information available</td></tr>');
        }

        // Populate interfaces
        var ifaceTable = $modal.find('#interfaces-info-table');
        ifaceTable.empty();
        var interfaces = domain.interfaces || [];
        if (interfaces.length === 0) {
            ifaceTable.append('<tr><td colspan="3" class="text-muted">No interfaces configured</td></tr>');
        } else {
            interfaces.forEach(function(iface) {
                var name = escapeHtml(iface.name || iface.id || '-');
                var id = iface.id ? formatCopyable(iface.id) : '-';
                var mac = iface.mac ? formatCode(iface.mac) : '-';
                ifaceTable.append('<tr><td>' + name + '</td><td>' + id + '</td><td>' + mac + '</td></tr>');
            });
        }

        // Populate bastion info
        var bastionSection = $modal.find('#bastion-section');
        var bastionTable = $modal.find('#bastion-info-table');
        bastionTable.empty();

        var bastion = data.bastion;
        if (bastion && bastion.target_id) {
            bastionSection.show();
            var autoSubdomain = bastion.target_id + '.' + bastion.bastion_domain;

            // SSH Access
            if (bastion.ssh && bastion.ssh.enabled) {
                var sshPort = bastion.ssh_port || '443';
                var sshCommand = 'ssh ' + bastion.target_id + '@' + bastion.bastion_domain + ' -p ' + sshPort;
                addRowHtml(bastionTable, 'SSH Command', formatCode(sshCommand));
            } else {
                addRowHtml(bastionTable, 'SSH Access', '<span class="text-muted">Disabled</span>');
            }

            // HTTP/HTTPS Access
            if (bastion.http && bastion.http.enabled) {
                var httpsUrl = 'https://' + autoSubdomain;
                addRowHtml(bastionTable, 'Web Access', formatExternalLink(httpsUrl, autoSubdomain));

                // Custom CNAMEs with links
                if (bastion.domains && bastion.domains.length > 0) {
                    var cnameLinks = bastion.domains.map(function(domain) {
                        return formatExternalLink('https://' + domain, domain);
                    }).join('<br>');
                    addRowHtml(bastionTable, 'Custom Domains', cnameLinks);
                }
            } else {
                addRowHtml(bastionTable, 'Web Access', '<span class="text-muted">Disabled</span>');
            }
        } else {
            bastionSection.hide();
        }

        $modal.find('#domain-info-content').show();
    }

    /**
     * Show domain info modal for the given domain ID
     * @param {string} domainId - The domain ID to show info for
     */
    function showDomainInfo(domainId) {
        if (!domainId) {
            console.error('showDomainInfo: domainId is required');
            return;
        }

        ensureModalExists();
        showLoading();
        $('#' + MODAL_ID).modal('show');

        $.ajax({
            type: 'GET',
            url: '/api/v3/admin/domain/' + encodeURIComponent(domainId) + '/info',
            contentType: 'application/json',
            success: function(data) {
                showContent(data);
            },
            error: function(xhr) {
                var msg = 'Failed to load domain information';
                try {
                    var resp = JSON.parse(xhr.responseText);
                    msg = resp.error || resp.description || resp.message || msg;
                } catch(e) {}
                showError(msg);
            }
        });
    }

    // Auto-bind to elements with data-domain-info attribute
    $(document).on('click', '[data-domain-info]', function(e) {
        e.preventDefault();
        e.stopPropagation();
        var domainId = $(this).data('domain-info');
        showDomainInfo(domainId);
    });

    // Export to global scope
    window.showDomainInfo = showDomainInfo;

})(window, jQuery);
