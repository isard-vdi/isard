/**
 * Desktop Logs Modal - Reusable component for displaying desktop start/stop logs
 *
 * Usage:
 *   1. Include this script in your page
 *   2. Call showDesktopLogs(desktopId, desktopName) to open the modal
 */
(function(window, $) {
    'use strict';

    var MODAL_ID = 'desktop-logs-modal';

    var MODAL_HTML = [
        '<div class="modal fade" id="' + MODAL_ID + '" tabindex="-1" role="dialog">',
        '  <div class="modal-dialog" style="width:95vw;max-width:95vw" role="document">',
        '    <div class="modal-content">',
        '      <div class="modal-header">',
        '        <button type="button" class="close" data-dismiss="modal">&times;</button>',
        '        <h4 class="modal-title"><i class="fa fa-folder-open"></i> <span id="desktop-logs-title">Desktop Logs</span></h4>',
        '      </div>',
        '      <div class="modal-body">',
        '        <ul class="nav nav-tabs" role="tablist">',
        '          <li role="presentation" class="active"><a href="#tab-desktop-logs" data-toggle="tab">Desktop Logs</a></li>',
        '          <li role="presentation"><a href="#tab-directviewer-logs" data-toggle="tab">Direct Viewer Logs</a></li>',
        '        </ul>',
        '        <div class="tab-content" style="padding-top:15px">',
        '          <div role="tabpanel" class="tab-pane active" id="tab-desktop-logs">',
        '            <table id="table-desktop-logs" class="table table-stripped" style="width:100%">',
        '              <thead>',
        '                <tr>',
        '                  <th></th>',
        '                  <th>Starting Time</th>',
        '                  <th>Stopping Time</th>',
        '                  <th>Duration</th>',
        '                  <th>Started By</th>',
        '                  <th>Stopped By</th>',
        '                  <th>User Name</th>',
        '                  <th>IP</th>',
        '                  <th>Browser</th>',
        '                  <th>Viewers</th>',
        '                </tr>',
        '              </thead>',
        '              <tbody></tbody>',
        '            </table>',
        '          </div>',
        '          <div role="tabpanel" class="tab-pane" id="tab-directviewer-logs">',
        '            <table id="table-directviewer-logs" class="table table-stripped" style="width:100%">',
        '              <thead>',
        '                <tr>',
        '                  <th>Time</th>',
        '                  <th>Viewer Type</th>',
        '                  <th>IP</th>',
        '                  <th>Browser</th>',
        '                  <th>Platform</th>',
        '                </tr>',
        '              </thead>',
        '              <tbody></tbody>',
        '            </table>',
        '          </div>',
        '        </div>',
        '      </div>',
        '      <div class="modal-footer">',
        '        <button type="button" class="btn btn-primary" id="desktop-logs-csv-btn"><i class="fa fa-download"></i> Download CSV</button>',
        '        <button type="button" class="btn btn-default" data-dismiss="modal">Close</button>',
        '      </div>',
        '    </div>',
        '  </div>',
        '</div>'
    ].join('\n');

    function escapeHtml(str) {
        if (!str) return '';
        return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function formatAgent(val) {
        var labels = {
            'desktop-owner': 'Owner',
            'system-admins': 'Admin',
            'isard-scheduler': 'Scheduler',
            'desktop-directviewer': 'Direct Viewer',
            'isard-engine': 'Engine',
            'deployment-owner': 'Deploy Owner',
            'deployment-co-owner': 'Deploy Co-owner'
        };
        return labels[val] || escapeHtml(val) || '';
    }

    function formatTime(data) {
        if (!data || data === false) return '';
        return moment(data).format('YYYY-MM-DD HH:mm:ss');
    }

    function formatDuration(startData, stopData) {
        if (!startData || !stopData || stopData === false) return '\u2014';
        var start = moment(startData);
        var stop = moment(stopData);
        var diff = stop.diff(start);
        if (diff < 0) return '\u2014';
        var duration = moment.duration(diff);
        var days = Math.floor(duration.asDays());
        var hours = duration.hours();
        var minutes = duration.minutes();
        var seconds = duration.seconds();
        var parts = [];
        if (days > 0) parts.push(days + 'd');
        if (hours > 0) parts.push(hours + 'h');
        if (minutes > 0) parts.push(minutes + 'm');
        parts.push(seconds + 's');
        return parts.join(' ');
    }

    function renderEventDetails(events) {
        if (!events || events.length === 0) {
            return '<p style="padding:8px">No viewer events recorded.</p>';
        }
        var html = '<table class="table table-condensed table-bordered" style="margin:8px;width:calc(100% - 16px)">';
        html += '<thead><tr><th>Time</th><th>Type</th><th>User</th><th>Viewer</th><th>IP</th><th>Browser</th></tr></thead><tbody>';
        events.forEach(function(ev) {
            html += '<tr>';
            html += '<td>' + escapeHtml(formatTime(ev.time)) + '</td>';
            html += '<td>' + escapeHtml(ev.event) + '</td>';
            html += '<td>' + escapeHtml(ev.action_user) + '</td>';
            html += '<td>' + escapeHtml(ev.viewer_type) + '</td>';
            html += '<td>' + escapeHtml(ev.request_ip) + '</td>';
            html += '<td>' + escapeHtml(ev.request_agent_browser) + '</td>';
            html += '</tr>';
        });
        html += '</tbody></table>';
        return html;
    }

    function downloadCsv(filename, headers, rows) {
        var csv = headers.join(',') + '\n';
        rows.forEach(function(row) {
            csv += row.map(function(cell) {
                return '"' + String(cell || '').replace(/"/g, '""') + '"';
            }).join(',') + '\n';
        });
        var blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        var link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        link.click();
        URL.revokeObjectURL(link.href);
    }

    function ensureModalExists() {
        if ($('#' + MODAL_ID).length === 0) {
            $('body').append(MODAL_HTML);
        }
    }

    var currentDesktopId = null;

    function showDesktopLogs(desktopId, desktopName) {
        if (!desktopId) return;

        currentDesktopId = desktopId;
        ensureModalExists();
        $('#desktop-logs-title').text('Desktop Logs: ' + (desktopName || desktopId));

        // Destroy previous DataTable instances
        if ($.fn.DataTable.isDataTable('#table-desktop-logs')) {
            $('#table-desktop-logs').DataTable().destroy();
        }
        if ($.fn.DataTable.isDataTable('#table-directviewer-logs')) {
            $('#table-directviewer-logs').DataTable().destroy();
            $('#table-directviewer-logs tbody').empty();
        }

        // Reset to first tab
        $('#' + MODAL_ID + ' .nav-tabs a:first').tab('show');

        $('#' + MODAL_ID).modal('show');

        // === Tab 1: Desktop Logs (server-side DataTable) ===
        var columns = [
            { "data": null, "defaultContent": '<button class="btn btn-xs btn-info" type="button"><i class="fa fa-plus"></i></button>' },
            { "data": "starting_time" },
            { "data": "stopping_time" },
            { "data": null, "defaultContent": "" },
            { "data": "starting_by" },
            { "data": "stopping_by" },
            { "data": "owner_user_name" },
            { "data": "request_ip" },
            { "data": "request_agent_browser" },
            { "data": "events" }
        ];

        var table = $('#table-desktop-logs').DataTable({
            serverSide: true,
            responsive: true,
            autoWidth: false,
            searching: false,
            ajax: {
                url: '/api/v3/admin/logs_desktops/desktop/' + encodeURIComponent(desktopId),
                type: 'POST'
            },
            columns: columns,
            columnDefs: [
                {
                    targets: 0,
                    className: 'details-control',
                    orderable: false,
                    width: "10px"
                },
                {
                    targets: 1,
                    render: function(data) { return formatTime(data); }
                },
                {
                    targets: 2,
                    render: function(data) {
                        if (!data || data === false) return '<span class="label label-success">Running</span>';
                        return formatTime(data);
                    }
                },
                {
                    targets: 3,
                    orderable: false,
                    render: function(data, type, row) {
                        return formatDuration(row.starting_time, row.stopping_time);
                    }
                },
                {
                    targets: 4,
                    render: function(data) { return formatAgent(data); }
                },
                {
                    targets: 5,
                    render: function(data) { return formatAgent(data); }
                },
                {
                    targets: 9,
                    orderable: false,
                    render: function(data) {
                        var count = (data && data.length) || 0;
                        if (count === 0) return '<span class="label label-default">0</span>';
                        return '<span class="label label-info">' + count + '</span>';
                    }
                }
            ],
            order: [[1, "desc"]]
        });

        // Row detail expand/collapse
        $('#table-desktop-logs tbody').off('click', 'td.details-control').on('click', 'td.details-control', function() {
            var tr = $(this).closest('tr');
            var row = table.row(tr);
            if (row.child.isShown()) {
                row.child.hide();
                tr.removeClass('shown');
                $(this).find('i').removeClass('fa-minus').addClass('fa-plus');
            } else {
                row.child(renderEventDetails(row.data().events)).show();
                tr.addClass('shown');
                $(this).find('i').removeClass('fa-plus').addClass('fa-minus');
            }
        });

        // === Tab 2: Direct Viewer Logs (client-side, extracted from events) ===
        loadDirectViewerLogs(desktopId);

        // CSV download handler (context-aware: downloads from active tab)
        $('#desktop-logs-csv-btn').off('click').on('click', function() {
            var $btn = $(this);
            var activeTab = $('#' + MODAL_ID + ' .tab-pane.active').attr('id');
            $btn.prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> Downloading...');

            if (activeTab === 'tab-directviewer-logs') {
                downloadDirectViewerCsv($btn);
            } else {
                downloadDesktopLogsCsv($btn, columns);
            }
        });
    }

    function loadDirectViewerLogs(desktopId) {
        var formData = 'draw=1&start=0&length=100000&order[0][column]=1&order[0][dir]=desc';
        var cols = ['', 'starting_time', 'stopping_time', '', 'starting_by', 'stopping_by', 'owner_user_name', 'request_ip', 'request_agent_browser', 'events'];
        cols.forEach(function(col, i) {
            formData += '&columns[' + i + '][data]=' + encodeURIComponent(col);
        });

        $.ajax({
            url: '/api/v3/admin/logs_desktops/desktop/' + encodeURIComponent(desktopId),
            type: 'POST',
            data: formData,
            success: function(resp) {
                var dvEvents = [];
                resp.data.forEach(function(log) {
                    if (log.events) {
                        log.events.forEach(function(ev) {
                            if (ev.event === 'directviewer') {
                                dvEvents.push(ev);
                            }
                        });
                    }
                });

                if ($.fn.DataTable.isDataTable('#table-directviewer-logs')) {
                    $('#table-directviewer-logs').DataTable().destroy();
                    $('#table-directviewer-logs tbody').empty();
                }

                $('#table-directviewer-logs').DataTable({
                    data: dvEvents,
                    responsive: true,
                    autoWidth: false,
                    searching: false,
                    columns: [
                        { data: 'time' },
                        { data: 'viewer_type' },
                        { data: 'request_ip' },
                        { data: 'request_agent_browser' },
                        { data: 'request_agent_platform' }
                    ],
                    columnDefs: [
                        {
                            targets: 0,
                            render: function(data) { return formatTime(data); }
                        }
                    ],
                    order: [[0, "desc"]]
                });
            }
        });
    }

    function downloadDirectViewerCsv($btn) {
        var dt = $('#table-directviewer-logs').DataTable();
        var data = dt.data().toArray();
        var headers = ['Time', 'Viewer Type', 'IP', 'Browser', 'Platform'];
        var rows = data.map(function(ev) {
            return [
                formatTime(ev.time),
                ev.viewer_type || '',
                ev.request_ip || '',
                ev.request_agent_browser || '',
                ev.request_agent_platform || ''
            ];
        });
        downloadCsv('directviewer_logs.csv', headers, rows);
        $btn.prop('disabled', false).html('<i class="fa fa-download"></i> Download CSV');
    }

    function downloadDesktopLogsCsv($btn, columns) {
        var formData = 'draw=1&start=0&length=100000&order[0][column]=1&order[0][dir]=desc';
        columns.forEach(function(col, i) {
            formData += '&columns[' + i + '][data]=' + encodeURIComponent(col.data || '');
        });

        $.ajax({
            url: '/api/v3/admin/logs_desktops/desktop/' + encodeURIComponent(currentDesktopId),
            type: 'POST',
            data: formData,
            success: function(resp) {
                var headers = ['Starting Time', 'Stopping Time', 'Duration', 'Started By', 'Stopped By', 'User Name', 'IP', 'Browser', 'Viewers'];
                var rows = resp.data.map(function(r) {
                    return [
                        formatTime(r.starting_time),
                        (!r.stopping_time && r.stopping_time !== 0) ? 'Running' : formatTime(r.stopping_time),
                        formatDuration(r.starting_time, r.stopping_time),
                        formatAgent(r.starting_by),
                        formatAgent(r.stopping_by),
                        r.owner_user_name || '',
                        r.request_ip || '',
                        r.request_agent_browser || '',
                        (r.events && r.events.length) || 0
                    ];
                });
                downloadCsv('desktop_logs.csv', headers, rows);
            },
            complete: function() {
                $btn.prop('disabled', false).html('<i class="fa fa-download"></i> Download CSV');
            }
        });
    }

    window.showDesktopLogs = showDesktopLogs;

})(window, jQuery);
