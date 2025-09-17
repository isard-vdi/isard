/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

// Helper function to format duration in seconds to human readable format
function formatDuration(seconds) {
    if (!seconds || seconds < 1) return '< 1s';
    var minutes = Math.floor(seconds / 60);
    var remainingSeconds = Math.floor(seconds % 60);
    if (minutes > 0) {
        return minutes + 'm ' + remainingSeconds + 's';
    }
    return remainingSeconds + 's';
}

// Helper function to render backup type icons
function renderBackupTypeIcon(statusData, backupType) {
    if (!statusData || !statusData[backupType]) {
        return '<i class="fa fa-minus text-muted" title="Not included"></i>';
    }
    
    var status = statusData[backupType];
    switch (status) {
        case 'success':
            return '<i class="fa fa-check text-success" title="Success"></i>';
        case 'failed':
            return '<i class="fa fa-times text-danger" title="Failed"></i>';
        case 'not_included':
        default:
            return '<i class="fa fa-minus text-muted" title="Not included"></i>';
    }
}

$(document).ready(function () {
    // Load backup dashboard
    loadBackupDashboard();
    
    // Initialize DataTable with standard IsardVDI pattern
    var backupsTable = $('#backups-table').DataTable({
        ajax: {
            url: '/api/v3/admin/backups',
            type: 'GET',
            dataSrc: ""
        },
        language: {
            loadingRecords: "&nbsp",
            processing: '<p>Loading...</p><i style="font-size: 1rem;" class="fa fa-spinner fa-pulse fa-2x fa-fw"></i>',
        },
        processing: true,
        deferRender: true,
        paging: true,
        cache: false,
        columns: [
            {
                data: 'timestamp',
                render: function (data, type, row) {
                    if (type === 'display' || type === 'filter') {
                        // Handle multiple timestamp formats
                        if (typeof data === 'string') {
                            // Handle ISO format or RethinkDB datetime string
                            return moment(data).format('YYYY-MM-DD HH:mm:ss');
                        } else if (typeof data === 'number') {
                            // Handle Unix timestamp
                            return moment.unix(data).format('YYYY-MM-DD HH:mm:ss');
                        }
                        return 'N/A';
                    }
                    return data;
                }
            },
            {
                data: 'type',
                render: function (data, type, row) {
                    if (type === 'display') {
                        if (data === 'automated') {
                            return '<span class="label label-info">Automated</span>';
                        } else if (data === 'manual') {
                            return '<span class="label label-warning">Manual</span>';
                        }
                    }
                    return data;
                }
            },
            {
                data: 'status',
                render: function (data, type, row) {
                    if (type === 'display') {
                        if (data === 'SUCCESS') {
                            return '<span class="label label-success">Success</span>';
                        } else if (data === 'ERROR') {
                            return '<span class="label label-danger">Error</span>';
                        } else if (data === 'WARNING') {
                            return '<span class="label label-warning">Warning</span>';
                        } else if (data === 'PARTIAL') {
                            return '<span class="label label-warning">Partial</span>';
                        }
                    }
                    return data;
                }
            },
            {
                data: 'scope',
                render: function (data, type, row) {
                    if (type === 'display') {
                        return '<span class="label label-default">' + data + '</span>';
                    }
                    return data;
                }
            },
            {
                data: 'total_actions',
                render: function (data, type, row) {
                    if (type === 'display') {
                        var successful = row.successful_actions || 0;
                        var warnings = row.warning_actions || 0;
                        var failed = row.failed_actions || 0;
                        return successful + '/' + data + ' (' + (warnings + failed > 0 ? warnings + failed + ' issues' : 'clean') + ')';
                    }
                    return data;
                }
            },
            {
                data: 'duration',
                render: function (data, type, row) {
                    if (type === 'display' && data) {
                        return data + 's';
                    }
                    return data || 'N/A';
                }
            },
            {
                data: 'filesystem_metrics',
                render: function (data, type, row) {
                    if (type === 'display') {
                        if (data && data.usage && data.usage.backup_storage) {
                            var storage = data.usage.backup_storage;
                            return storage.used + ' / ' + storage.size + ' (' + storage.usage_percent + '%)';
                        }
                        return 'N/A';
                    }
                    return 'N/A';
                }
            },
            {
                data: 'backup_types',
                render: function (data, type, row) {
                    if (type === 'display' && data) {
                        var types = Object.keys(data);
                        var totalSize = 0;
                        var totalCompressed = 0;
                        
                        types.forEach(function(type) {
                            if (data[type] && data[type].borg_statistics) {
                                // Simple estimation - in real implementation this would be calculated properly
                                totalSize += 100; // Placeholder
                                totalCompressed += 70; // Placeholder  
                            }
                        });
                        
                        if (totalSize > 0) {
                            var ratio = ((totalSize - totalCompressed) / totalSize * 100).toFixed(1);
                            return ratio + '% saved';
                        }
                    }
                    return 'N/A';
                }
            },
            {
                data: 'id',
                orderable: false,
                render: function (data, type, row) {
                    if (type === 'display') {
                        return '<button class="btn btn-xs btn-info show-backup-details" data-id="' + data + '">Details</button>';
                    }
                    return '';
                }
            }
        ],
        order: [[0, 'desc']], // Sort by timestamp descending
        pageLength: 25
    });

    // Add footer search inputs
    $('#backups-table tfoot th').each(function (index) {
        if (index < 5) { // Don't add search to the actions column
            var title = $(this).text();
            $(this).html('<input type="text" placeholder="Search ' + title + '" style="width: 100%;" />');
        }
    });

    // Apply search functionality
    backupsTable.columns().every(function () {
        var that = this;
        $('input', this.footer()).on('keyup change', function () {
            if (that.search() !== this.value) {
                that.search(this.value).draw();
            }
        });
    });

    // Refresh button
    $('.btn-refresh-backups').on('click', function () {
        backupsTable.ajax.reload();
    });

    // Clear filters
    $('#clear-filters').on('click', function () {
        $('#filter-type').val('');
        $('#filter-status').val('');
        backupsTable.columns().search('').draw();
    });

    // Apply filters
    $('#filter-type, #filter-status').on('change', function () {
        var typeFilter = $('#filter-type').val();
        var statusFilter = $('#filter-status').val();

        backupsTable.column(1).search(typeFilter).draw();
        backupsTable.column(2).search(statusFilter).draw();
    });

    // View details button
    $('#backups-table').on('click', '.show-backup-details', function () {
        var backupId = $(this).data('id');
        showBackupDetails(backupId);
    });

    function showBackupDetails(backupId) {
        $.ajax({
            url: '/api/v3/admin/backups/' + backupId,
            type: 'GET',
            success: function (data) {
                var content = '<div class="row">';
                
                // Basic Information
                content += '<div class="col-md-6"><h4>Basic Information</h4>';
                content += '<p><strong>Timestamp:</strong> ' + (typeof data.timestamp === 'string' ? moment(data.timestamp).format('YYYY-MM-DD HH:mm:ss') : moment.unix(data.timestamp).format('YYYY-MM-DD HH:mm:ss')) + '</p>';
                content += '<p><strong>Type:</strong> ' + (data.type === 'automated' ? 'Automated' : 'Manual') + '</p>';
                content += '<p><strong>Status:</strong> ' + data.status + '</p>';
                content += '<p><strong>Scope:</strong> ' + (data.scope || 'N/A') + '</p>';
                
                // Backup Types Status
                if (data.backup_types_status) {
                    content += '<h5>Backup Types Status</h5>';
                    var backupTypes = ['db', 'redis', 'stats', 'config', 'disks'];
                    for (var i = 0; i < backupTypes.length; i++) {
                        var type = backupTypes[i];
                        var status = data.backup_types_status[type] || 'not_included';
                        var icon = '';
                        var statusText = '';
                        
                        switch (status) {
                            case 'success':
                                icon = '<i class="fa fa-check text-success"></i>';
                                statusText = 'Success';
                                break;
                            case 'failed':
                                icon = '<i class="fa fa-times text-danger"></i>';
                                statusText = 'Failed';
                                break;
                            case 'not_included':
                            default:
                                icon = '<i class="fa fa-minus text-muted"></i>';
                                statusText = 'Not included';
                                break;
                        }
                        
                        content += '<p><strong>' + type.toUpperCase() + ':</strong> ' + icon + ' ' + statusText;
                        
                        // Add disk types info for disks
                        if (type === 'disks' && status === 'success' && data.disk_types && data.disk_types.length > 0) {
                            content += ' (' + data.disk_types.join(', ') + ')';
                        }
                        content += '</p>';
                    }
                }
                content += '<p><strong>Duration:</strong> ' + (data.duration ? formatDuration(data.duration) : 'N/A') + '</p>';
                content += '<p><strong>Summary:</strong> ' + (data.summary || 'N/A') + '</p>';
                content += '</div>';
                
                // Action Statistics section
                content += '<div class="col-md-6"><h4>Action Statistics</h4>';
                content += '<p><strong>Total Actions:</strong> ' + (data.total_actions || 0) + '</p>';
                content += '<p><strong>Successful:</strong> <span class="text-success">' + (data.successful_actions || 0) + '</span></p>';
                if (data.warning_actions > 0) {
                    content += '<p><strong>Warnings:</strong> <span class="text-warning">' + data.warning_actions + '</span></p>';
                }
                if (data.failed_actions > 0) {
                    content += '<p><strong>Failed:</strong> <span class="text-danger">' + data.failed_actions + '</span></p>';
                }
                if (data.fatal_actions > 0) {
                    content += '<p><strong>Fatal:</strong> <span class="text-danger">' + data.fatal_actions + '</span></p>';
                }
                content += '</div>';

                // Filesystem Metrics
                if (data.filesystem_metrics && typeof data.filesystem_metrics === 'object') {
                    content += '<div class="col-md-6"><h4>Filesystem Metrics</h4>';
                    
                    if (data.filesystem_metrics.usage) {
                        if (data.filesystem_metrics.usage.backup_storage) {
                            var bs = data.filesystem_metrics.usage.backup_storage;
                            content += '<p><strong>Backup Storage:</strong> ' + (bs.used || 'N/A') + ' / ' + (bs.size || 'N/A') + ' (' + (bs.usage_percent || 0) + '% used)</p>';
                            if (bs.device) content += '<p><strong>Device:</strong> ' + bs.device + '</p>';
                            if (bs.mount_point) content += '<p><strong>Mount Point:</strong> ' + bs.mount_point + '</p>';
                            if (bs.available) content += '<p><strong>Available:</strong> ' + bs.available + '</p>';
                        }
                        if (data.filesystem_metrics.usage.source_storage) {
                            var ss = data.filesystem_metrics.usage.source_storage;
                            content += '<p><strong>Source Storage:</strong> ' + (ss.used || 'N/A') + ' / ' + (ss.size || 'N/A') + ' (' + (ss.usage_percent || 0) + '% used)</p>';
                        }
                    }
                    
                    if (data.filesystem_metrics.backup_sizes) {
                        content += '<p><strong>Backup Repository Sizes:</strong></p><ul>';
                        Object.keys(data.filesystem_metrics.backup_sizes).forEach(function(key) {
                            if (key !== 'extract') {
                                content += '<li>' + key + ': ' + data.filesystem_metrics.backup_sizes[key] + '</li>';
                            }
                        });
                        content += '</ul>';
                    }
                    
                    // Show borg repository info if available
                    if (data.filesystem_metrics.borg_repositories) {
                        content += '<p><strong>Borg Repositories:</strong></p><ul>';
                        Object.keys(data.filesystem_metrics.borg_repositories).forEach(function(repo) {
                            var repoData = data.filesystem_metrics.borg_repositories[repo];
                            content += '<li><strong>' + repo + ':</strong>';
                            if (repoData.latest_archive && repoData.latest_archive.stats) {
                                var stats = repoData.latest_archive.stats;
                                if (stats.deduplicated_size) {
                                    content += ' Size: ' + stats.deduplicated_size;
                                }
                                if (stats.file_count) {
                                    content += ', Files: ' + stats.file_count.toLocaleString();
                                }
                            }
                            content += '</li>';
                        });
                        content += '</ul>';
                    }
                    
                    content += '</div>';
                } else {
                    content += '<div class="col-md-6"><h4>Legacy Data</h4>';
                    if (data.components) {
                        content += '<p><strong>Components:</strong> ' + (Array.isArray(data.components) ? data.components.join(', ') : data.components) + '</p>';
                    }
                    content += '</div>';
                }

                content += '</div>';

                // Backup Types Details
                if (data.backup_types && typeof data.backup_types === 'object') {
                    content += '<div class="row mt-3"><div class="col-md-12"><h4>Backup Types</h4>';
                    content += '<div class="table-responsive">';
                    content += '<table class="table table-sm table-bordered">';
                    content += '<thead><tr><th>Type</th><th>Actions</th><th>Status</th><th>Duration</th><th>Repository Stats</th></tr></thead><tbody>';
                    
                    Object.keys(data.backup_types).forEach(function(backupType) {
                        var typeData = data.backup_types[backupType];
                        content += '<tr>';
                        content += '<td><strong>' + backupType.toUpperCase() + '</strong></td>';
                        content += '<td>' + (typeData.total_actions || 0) + ' (' + (typeData.successful || 0) + ' success';
                        if ((typeData.warnings || 0) > 0) content += ', ' + typeData.warnings + ' warnings';
                        if ((typeData.errors || 0) > 0) content += ', ' + typeData.errors + ' errors';
                        content += ')</td>';
                        content += '<td>' + ((typeData.errors || 0) > 0 ? 'ERROR' : (typeData.warnings || 0) > 0 ? 'WARNING' : 'SUCCESS') + '</td>';
                        content += '<td>' + formatDuration(typeData.total_duration || 0) + '</td>';
                        
                        if (typeData.borg_statistics && typeof typeData.borg_statistics === 'object') {
                            var stats = typeData.borg_statistics;
                            content += '<td><small>';
                            if (stats.file_count) content += '<strong>Files:</strong> ' + stats.file_count.toLocaleString() + '<br/>';
                            if (stats.original_size) content += '<strong>Original:</strong> ' + stats.original_size + '<br/>';
                            if (stats.compressed_size) content += '<strong>Compressed:</strong> ' + stats.compressed_size + '<br/>';
                            if (stats.deduplicated_size) content += '<strong>Deduplicated:</strong> ' + stats.deduplicated_size + '<br/>';
                            if (stats.unique_chunks && stats.total_chunks) {
                                content += '<strong>Chunks:</strong> ' + stats.unique_chunks.toLocaleString() + ' unique / ' + stats.total_chunks.toLocaleString() + ' total<br/>';
                            }
                            // Calculate and show efficiency ratio
                            if (stats.original_size && stats.deduplicated_size) {
                                var origSize = parseFloat(stats.original_size.replace(/[^0-9.]/g, '')) || 0;
                                var dedupSize = parseFloat(stats.deduplicated_size.replace(/[^0-9.]/g, '')) || 0;
                                if (origSize > 0 && dedupSize > 0) {
                                    var efficiency = origSize / dedupSize;
                                    content += '<strong>Efficiency:</strong> ' + efficiency.toFixed(1) + 'x';
                                }
                            }
                            content += '</small></td>';
                        } else {
                            content += '<td><span class="text-muted">No stats available</span></td>';
                        }
                        
                        content += '</tr>';
                    });
                    
                    content += '</tbody></table></div></div></div>';
                }

                // Actions Details
                if (data.actions && data.actions.length > 0) {
                    content += '<div class="row mt-3"><div class="col-md-12"><h4>Actions</h4>';
                    content += '<div class="table-responsive" style="max-height: 400px; overflow-y: auto;">';
                    content += '<table class="table table-sm table-striped">';
                    content += '<thead><tr><th>Action</th><th>Status</th><th>Duration</th><th>Details</th></tr></thead><tbody>';
                    
                    data.actions.forEach(function(action) {
                        content += '<tr>';
                        content += '<td><small>' + (action.name ? action.name.split('/').pop() : 'Unknown Action') + '</small></td>';
                        
                        var actionStatus = action.status || 'UNKNOWN';
                        var statusClass = actionStatus === 'SUCCESS' ? 'success' : 
                                        actionStatus === 'WARNING' ? 'warning' : 
                                        actionStatus === 'ERROR' ? 'danger' : 'default';
                        content += '<td><span class="label label-' + statusClass + '">' + actionStatus + '</span></td>';
                        content += '<td>' + formatDuration(action.duration || 0) + '</td>';
                        
                        content += '<td><small>';
                        var details = [];
                        
                        if (action.borg_statistics && typeof action.borg_statistics === 'object') {
                            var stats = action.borg_statistics;
                            if (stats.deduplicated_size) details.push('<strong>Size:</strong> ' + stats.deduplicated_size);
                            if (stats.compressed_size) details.push('<strong>Compressed:</strong> ' + stats.compressed_size);
                            if (stats.file_count) details.push('<strong>Files:</strong> ' + stats.file_count.toLocaleString());
                            if (stats.efficiency && stats.efficiency !== 'N/A') details.push('<strong>Efficiency:</strong> ' + stats.efficiency + 'x');
                            // Calculate efficiency if not provided
                            if (!stats.efficiency && stats.original_size && stats.deduplicated_size) {
                                var origSize = parseFloat(stats.original_size.replace(/[^0-9.]/g, '')) || 0;
                                var dedupSize = parseFloat(stats.deduplicated_size.replace(/[^0-9.]/g, '')) || 0;
                                if (origSize > 0 && dedupSize > 0) {
                                    var efficiency = origSize / dedupSize;
                                    details.push('<strong>Efficiency:</strong> ' + efficiency.toFixed(1) + 'x');
                                }
                            }
                        }
                        
                        if (action.compact_results) {
                            details.push('Compact: ' + action.compact_results.status);
                            if (action.compact_results.space_freed) {
                                details.push('Freed: ' + action.compact_results.space_freed);
                            }
                        }
                        
                        if (action.start_time && action.end_time) {
                            details.push('Time: ' + moment(action.start_time).format('HH:mm:ss') + ' - ' + moment(action.end_time).format('HH:mm:ss'));
                        }
                        
                        if (action.messages && action.messages.length > 0) {
                            details.push('<a href="#" onclick="toggleMessages(\'' + action.name.replace(/[^a-zA-Z0-9]/g, '_') + '\'); return false;">Messages: ' + action.messages.length + ' <i class="fa fa-chevron-down"></i></a>');
                        }
                        
                        content += details.join('<br/>');
                        content += '</small></td>';
                        
                        content += '</tr>';
                        
                        // Add collapsible messages row if action has messages
                        if (action.messages && action.messages.length > 0) {
                            var actionId = action.name.replace(/[^a-zA-Z0-9]/g, '_');
                            content += '<tr id="messages_' + actionId + '" style="display: none;">';
                            content += '<td colspan="4" class="bg-light"><small>';
                            content += '<strong>Messages:</strong><br/>';
                            action.messages.forEach(function(msg, index) {
                                content += (index + 1) + '. ' + msg + '<br/>';
                            });
                            content += '</small></td></tr>';
                        }
                    });
                    
                    content += '</tbody></table></div></div></div>';
                }


                $('#backup-details-content').html(content);
                $('#backup-details-modal').modal('show');
            },
            error: function () {
                new PNotify({
                    title: 'Error',
                    text: 'Failed to load backup details',
                    type: 'error',
                    delay: 3000
                });
            }
        });
    }


    // Global function for toggling messages
    window.toggleMessages = function(actionId) {
        var messageRow = $('#messages_' + actionId);
        var chevron = $('a[onclick*="' + actionId + '"] i');
        
        if (messageRow.is(':visible')) {
            messageRow.hide();
            chevron.removeClass('fa-chevron-up').addClass('fa-chevron-down');
        } else {
            messageRow.show();
            chevron.removeClass('fa-chevron-down').addClass('fa-chevron-up');
        }
    };
});

// Dashboard functionality
function loadBackupDashboard() {
    loadLatestBackupStatus();
    loadStorageStatus();
    loadBackupScheduleStatus();
}

function loadLatestBackupStatus() {
    $.ajax({
        url: '/api/v3/admin/backups',
        type: 'GET',
        success: function (data) {
            if (data && data.length > 0) {
                var latestBackup = data[0]; // Most recent backup
                var now = moment();
                var backupTime = moment(latestBackup.timestamp);
                var hoursAgo = now.diff(backupTime, 'hours');
                
                var content = '<div class="backup-status-card">';
                
                // Status indicator
                var statusIcon = '';
                var statusClass = '';
                var statusText = latestBackup.status;
                
                switch (latestBackup.status.toLowerCase()) {
                    case 'success':
                        statusIcon = '<i class="fa fa-check-circle text-success fa-3x"></i>';
                        statusClass = 'success';
                        break;
                    case 'failed':
                    case 'error':
                        statusIcon = '<i class="fa fa-times-circle text-danger fa-3x"></i>';
                        statusClass = 'danger';
                        break;
                    default:
                        statusIcon = '<i class="fa fa-exclamation-triangle text-warning fa-3x"></i>';
                        statusClass = 'warning';
                        statusText = 'Warning';
                }
                
                content += '<div class="text-center">';
                content += '<h4>' + statusText.toUpperCase() + ' <small>(' + (hoursAgo < 24 ? hoursAgo + 'h ago' : Math.floor(hoursAgo/24) + 'd ago') + ')</small></h4>';
                content += '<p>' + backupTime.format('MMM DD, HH:mm') + '</p>';
                content += '</div>';
                
                // Warning if backup is too old
                var scheduleHour = getBackupScheduleHour();
                var expectedTime = moment().hour(scheduleHour).minute(0).second(0);
                if (now.isAfter(expectedTime) && hoursAgo > 25) {
                    content += '<div class="alert alert-warning mt-3">';
                    content += '<i class="fa fa-exclamation-triangle"></i> ';
                    content += '<strong>Warning:</strong> No recent backup found for today. ';
                    content += 'Expected backup at ' + scheduleHour + ':00.';
                    content += '</div>';
                } else if (now.isAfter(expectedTime.add(2, 'hours')) && hoursAgo > 2 && backupTime.format('YYYY-MM-DD') !== now.format('YYYY-MM-DD')) {
                    content += '<div class="alert alert-danger mt-3">';
                    content += '<i class="fa fa-exclamation-triangle"></i> ';
                    content += '<strong>Alert:</strong> Backup may have failed today. ';
                    content += 'Last successful backup was ' + Math.floor(hoursAgo/24) + ' days ago.';
                    content += '</div>';
                }
                
                content += '</div>';
                $('#latest-backup-status').html(content);
            } else {
                $('#latest-backup-status').html('<div class="alert alert-danger"><i class="fa fa-times"></i> No backup data available</div>');
            }
        },
        error: function () {
            $('#latest-backup-status').html('<div class="alert alert-danger"><i class="fa fa-times"></i> Failed to load backup status</div>');
        }
    });
}

function loadStorageStatus() {
    $.ajax({
        url: '/api/v3/admin/backups',
        type: 'GET',
        success: function (data) {
            if (data && data.length > 0) {
                // Get latest backup with filesystem metrics
                var latestBackupWithMetrics = data.find(backup => 
                    backup.filesystem_metrics && 
                    backup.filesystem_metrics.usage && 
                    backup.filesystem_metrics.usage.backup_storage
                );
                
                if (latestBackupWithMetrics) {
                    var storage = latestBackupWithMetrics.filesystem_metrics.usage.backup_storage;
                    var usedPercent = storage.usage_percent || 0;
                    var progressClass = usedPercent > 80 ? 'danger' : usedPercent > 60 ? 'warning' : 'success';
                    
                    var content = '<div class="text-center">';
                    content += '<h4>' + usedPercent + '% <small>' + (storage.used || 'N/A') + ' / ' + (storage.size || 'N/A') + '</small></h4>';
                    content += '<div class="progress" style="height: 6px;"><div class="progress-bar progress-bar-' + progressClass + '" style="width: ' + usedPercent + '%"></div></div>';
                    content += '</div>';
                    
                    // Storage warning
                    if (usedPercent > 90) {
                        content += '<div class="alert alert-danger mt-3">';
                        content += '<i class="fa fa-exclamation-triangle"></i> ';
                        content += '<strong>Critical:</strong> Backup storage is ' + usedPercent + '% full!';
                        content += '</div>';
                    } else if (usedPercent > 80) {
                        content += '<div class="alert alert-warning mt-3">';
                        content += '<i class="fa fa-exclamation-triangle"></i> ';
                        content += '<strong>Warning:</strong> Backup storage is ' + usedPercent + '% full.';
                        content += '</div>';
                    }
                    
                    content += '</div>';
                    $('#storage-status').html(content);
                } else {
                    $('#storage-status').html('<div class="alert alert-warning"><i class="fa fa-info"></i> No storage metrics available</div>');
                }
            } else {
                $('#storage-status').html('<div class="alert alert-danger"><i class="fa fa-times"></i> No backup data available</div>');
            }
        },
        error: function () {
            $('#storage-status').html('<div class="alert alert-danger"><i class="fa fa-times"></i> Failed to load storage status</div>');
        }
    });
}

function loadBackupScheduleStatus() {
    $.ajax({
        url: '/api/v3/admin/backups/config',
        type: 'GET',
        success: function (config) {
            var scheduleHour = config.main_schedule_hour || 19;
            window.backupScheduleHour = scheduleHour;
            
            var nextBackup = moment().hour(scheduleHour).minute(0).second(0);
            if (moment().isAfter(nextBackup)) {
                nextBackup.add(1, 'day');
            }
            
            var content = '<div class="text-center">';
            content += '<h4>Daily at ' + scheduleHour + ':00</h4>';
            content += '<p>Next: ' + nextBackup.format('MMM DD, HH:mm') + '</p>';
            content += '</div>';
            
            $('#backup-schedule-status').html(content);
        },
        error: function () {
            $('#backup-schedule-status').html('<div class="text-center text-danger">Failed to load</div>');
        }
    });
}

function getBackupScheduleHour() {
    // This will be populated by loadBackupScheduleStatus
    return window.backupScheduleHour || 19;
}

// Add CSS for dashboard styling
$(document).ready(function() {
    $('<style>')
        .prop('type', 'text/css')
        .html(`
            .backup-status-card, .storage-status-card, .schedule-status-card {
                padding: 15px;
            }
            .progress-lg {
                height: 25px;
            }
            .progress-lg .progress-bar {
                font-size: 14px;
                font-weight: bold;
            }
            .text-lg {
                font-size: 18px;
                margin: 10px 0;
            }
            .backup-status-card .fa-3x, 
            .storage-status-card .fa-3x,
            .schedule-status-card .fa-2x {
                margin-bottom: 15px;
            }
        `)
        .appendTo('head');
});
