/**
 * User Logs Modal - Reusable component for displaying user login logs
 *
 * Usage:
 *   1. Include this script in your page
 *   2. Call showUserLogs(userId, userName) to open the modal
 */
(function(window, $) {
    'use strict';

    var MODAL_ID = 'user-logs-modal';

    var MODAL_HTML = [
        '<div class="modal fade" id="' + MODAL_ID + '" tabindex="-1" role="dialog">',
        '  <div class="modal-dialog modal-lg" role="document">',
        '    <div class="modal-content">',
        '      <div class="modal-header">',
        '        <button type="button" class="close" data-dismiss="modal">&times;</button>',
        '        <h4 class="modal-title"><i class="fa fa-folder-open"></i> <span id="user-logs-title">User Logs</span></h4>',
        '      </div>',
        '      <div class="modal-body">',
        '        <table id="table-user-logs" class="table table-stripped" style="width:100%">',
        '          <thead>',
        '            <tr>',
        '              <th>Login Time</th>',
        '              <th>Logout Time</th>',
        '              <th>User Name</th>',
        '              <th>IP</th>',
        '              <th>Group</th>',
        '              <th>Category</th>',
        '            </tr>',
        '          </thead>',
        '          <tbody></tbody>',
        '        </table>',
        '      </div>',
        '      <div class="modal-footer">',
        '        <button type="button" class="btn btn-primary" id="user-logs-csv-btn"><i class="fa fa-download"></i> Download CSV</button>',
        '        <button type="button" class="btn btn-default" data-dismiss="modal">Close</button>',
        '      </div>',
        '    </div>',
        '  </div>',
        '</div>'
    ].join('\n');

    function formatTime(data) {
        if (!data || data === false) return '';
        return moment(data).format('YYYY-MM-DD HH:mm:ss');
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

    var currentUserId = null;

    function showUserLogs(userId, userName) {
        if (!userId) return;

        currentUserId = userId;
        ensureModalExists();
        $('#user-logs-title').text('User Logs: ' + (userName || userId));

        // Destroy previous DataTable instance if any
        if ($.fn.DataTable.isDataTable('#table-user-logs')) {
            $('#table-user-logs').DataTable().destroy();
        }

        $('#' + MODAL_ID).modal('show');

        var columns = [
            { "data": "started_time" },
            { "data": "stopped_time" },
            { "data": "owner_user_name" },
            { "data": "request_ip" },
            { "data": "owner_group_name" },
            { "data": "owner_category_name" },
            { "data": "expiry_time" }
        ];

        $('#table-user-logs').DataTable({
            serverSide: true,
            responsive: true,
            autoWidth: false,
            searching: false,
            ajax: {
                url: '/api/v3/admin/logs_users/user/' + encodeURIComponent(userId),
                type: 'POST'
            },
            columns: columns,
            columnDefs: [
                {
                    targets: 0,
                    render: function(data) { return formatTime(data); }
                },
                {
                    targets: 1,
                    render: function(data, type, row) {
                        if (data && data !== false) return formatTime(data);
                        if (row.expiry_time) return formatTime(row.expiry_time) + ' <span class="label label-warning">Expired</span>';
                        return '<span class="label label-success">Active</span>';
                    }
                },
                {
                    targets: 6,
                    visible: false
                }
            ],
            order: [[0, "desc"]]
        });

        // CSV download handler
        $('#user-logs-csv-btn').off('click').on('click', function() {
            var $btn = $(this);
            $btn.prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> Downloading...');

            var formData = 'draw=1&start=0&length=100000&order[0][column]=0&order[0][dir]=desc';
            columns.forEach(function(col, i) {
                formData += '&columns[' + i + '][data]=' + encodeURIComponent(col.data);
            });

            $.ajax({
                url: '/api/v3/admin/logs_users/user/' + encodeURIComponent(currentUserId),
                type: 'POST',
                data: formData,
                success: function(resp) {
                    var headers = ['Login Time', 'Logout Time', 'User Name', 'IP', 'Group', 'Category'];
                    var rows = resp.data.map(function(r) {
                        var endTime;
                        if (r.stopped_time && r.stopped_time !== false) {
                            endTime = formatTime(r.stopped_time);
                        } else if (r.expiry_time) {
                            endTime = formatTime(r.expiry_time) + ' (Expired)';
                        } else {
                            endTime = 'Active';
                        }
                        return [
                            formatTime(r.started_time),
                            endTime,
                            r.owner_user_name || '',
                            r.request_ip || '',
                            r.owner_group_name || '',
                            r.owner_category_name || ''
                        ];
                    });
                    downloadCsv('user_logs.csv', headers, rows);
                },
                complete: function() {
                    $btn.prop('disabled', false).html('<i class="fa fa-download"></i> Download CSV');
                }
            });
        });
    }

    window.showUserLogs = showUserLogs;

})(window, jQuery);
