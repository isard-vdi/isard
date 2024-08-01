$(document).ready(function () {

    var emptyDeploymentsCols = [
        {
            data: 'name',
            title: 'Name'
        },
        {
            data: 'category_name',
            title: 'Category'
        },
        {
            data: 'group_name',
            title: 'Group'
        },
        {
            data: 'username',
            title: 'User'
        },
        {
            data: 'id',
            title: 'Id',
            visible: false
        }
    ]

    var unusedDesktopsCols = [
        {
            data: 'name',
            title: 'Name'
        },
        {
            data: 'category_name',
            title: 'Category'
        },
        {
            data: 'group_name',
            title: 'Group'
        },
        {
            data: 'username',
            title: 'User'
        },
        {
            data: 'size',
            title: 'Size (GB)',
            render: function (size) {
                return size.toFixed(2)
              }
        },
        // {
        //     data: 'last_log',
        //     title: 'Last used',
        //     render: function (last) {
        //         return last
        //       }
        // },
        {
            data: null,
            title: 'Actions',
            className: "actions-control text-center",
            orderable: false,
            defaultContent:
              '<button title="Delete" class="btn btn-xs btn-danger btn-delete-desktop" type="button" data-placement="top" ><i class="fa fa-times"></i></button>'
        },
        {
            data: 'id',
            title: 'Id',
            visible: false
        }
    ]

    // $.getScript("/isard-admin/static/admin/js/socketio.js", socketio_on)

    const filter_list = ['category'];
    const options = filter_list.map(item => `<option value="${item}">${item.charAt(0).toUpperCase() + item.slice(1).replace(/_/g, ' ')}</option>`);
    $('#filter-select').append(options.join(''));
    $('.panel-heading button').click(function(e) {
        e.stopPropagation();
      });

    // set the filter box category on loading the document
    initial_filters();
    fetchStorageUsage();
    fetchResourcesCount();
    fetchSuggestedRemovals(6);


    function initial_filters() {
        var node = newFilterBox('category');
        $('#filter-boxes').append(node);
        populateSelect('category');
        $('#filter-select').find(`option[value='category']`).remove();
    }

    function newFilterBox(item) {
        $('#filter-select').val('null');
        return `
            <div class="select2-container--focus select2-container--resize" id="filter-${item}"
                <label>
                    <h4>${item.charAt(0).toUpperCase() + item.slice(1).replace(/_/g, ' ')}</h4>
                </label>
                <select class="filter-box form-control" id="${item}" name="${item}[]"
                ${$('meta[id=user_data]').attr('data-role') == 'manager' && item == 'category' ? "disabled" : ""} 
                multiple="multiple"></select>
                <div class="select2-resize-handle"></div>
            </div>
        `;
    }

    function populateSelect(item) {
        const elem = $("#" + item)
        elem.select2();
        elem.attr("index", item);
        switch (item) {
            case ("category"):
                $.ajax({
                    url: '/api/v3/admin/userschema',
                    type: 'GET',
                    contentType: 'application/json',
                    dataType: 'json',
                    async: false
                })
                    .then(function (d) {
                        $.each(d[item], function (pos, it) {
                            if (item == 'category') { var value = it.id } else { var value = it.name }
                            if ($("#" + item + " option:contains(" + it.name + ")").length == 0) {
                                elem.append('<option value=' + value + '>' + it.name + '</option>');
                            }
                        });
                    });
                if (item == 'category') { elem.val([$('meta[id=user_data]').attr('data-categoryid')]); }

                break;
        }
        elem.html(elem.children('option').sort(function (a, b) {
            return a.text.localeCompare(b.text);
        }));
    }

    $('#filter-category').on('change', function () {
        fetchStorageUsage()
        fetchResourcesCount()
        fetchSuggestedRemovals($('#suggestedRemovals .btn-success').data('months-without-use'))
    })

    $('.months-without-use-button').on('click', function () {
        $('.months-without-use-button').removeClass('btn-success')
        $(this).data('months-without-use')
        $(this).addClass('btn-success')
        fetchSuggestedRemovals($(this).data('months-without-use'))
    })

    function fetchStorageUsage() {
        var data = ''
        var categories = $('#filter-category #category').val();
        if ($('#filter-category #category').val()) {
            data = {
                'categories': categories
            };
        } else {
            data = {
                'categories': []
            };
        }

        $.ajax({
            url: '/api/v3/analytics/storage',
            type: 'POST',
            data: JSON.stringify(data),
            contentType: 'application/json',
            dataType: 'json',
        }).then(function (data) {
                if (typeof (echarts) === 'undefined') { return; }
                if ($('#echart_pie').length) {

                    var echartPie = echarts.init(document.getElementById('echart_pie'));

                    echartPie.setOption({
                        tooltip: {
                            trigger: 'item',
                            formatter: "{a} <br/>{b} ({d}%)"
                        },
                        legend: {
                            x: 'center',
                            y: 'bottom',
                            data: ['Domains: ' + data["domains"].toFixed(2) + ' GB', 'Media: ' + data["media"].toFixed(2) + ' GB']
                        },
                        toolbox: {
                            show: true,
                            feature: {
                                magicType: {
                                    show: true,
                                    type: ['pie', 'funnel'],
                                    option: {
                                        funnel: {
                                            x: '25%',
                                            width: '50%',
                                            funnelAlign: 'left',
                                            max: 1548
                                        }
                                    }
                                },
                                saveAsImage: {
                                    show: true,
                                    title: "Save Image"
                                }
                            }
                        },
                        calculable: true,
                        series: [{
                            name: 'Storage use',
                            type: 'pie',
                            radius: '55%',
                            center: ['50%', '48%'],
                            data: [{
                                value: data["domains"].toFixed(2),
                                name: 'Domains: ' + data["domains"].toFixed(2) + ' GB'
                            }, {
                                value: data["media"].toFixed(2),
                                name: 'Media: ' + data["media"].toFixed(2) + ' GB'
                            }]
                        }]
                    });

                }

                $("#totalUsage").html('(' + (data["domains"] + data["media"]).toFixed(2) + ' GB)')
            });
    }

    function fetchResourcesCount() {
        var data = ''
        var categories = $('#filter-category #category').val();
        if ($('#filter-category').length) {
            data = {
                'categories': categories
            };
        } else {
            data = {
                'categories': []
            };
        }
        $.ajax({
            url: '/api/v3/analytics/resources/count',
            type: 'POST',
            data: JSON.stringify(data),
            contentType: 'application/json',
            dataType: 'json'
        }).then(function (data) {
                $("#resourcesCount #desktops").html(data["desktops"])
                $("#resourcesCount #templates").html(data["templates"])
                $("#resourcesCount #media").html(data["media"])
                $("#resourcesCount #users").html(data["users"])
                $("#resourcesCount #groups").html(data["groups"])
                $("#resourcesCount #deployments").html(data["deployments"])
            });
    }

    function fetchSuggestedRemovals(months_without_use) {
        showLoading(true)
        var data = ''
        var categories = $('#filter-category #category').val();
        if ($('#filter-category').length) {
            data = {
                'categories': categories,
                'months_without_use': months_without_use
            }
        } else {
            data = {
                'categories': [],
                'months_without_use': months_without_use
            }
        }
        $.ajax({
            url: '/api/v3/analytics/suggested_removals',
            type: 'POST',
            data: JSON.stringify(data),
            contentType: 'application/json',
            dataType: 'json'
        }).then(function (data) {
                showLoading(false)
                loadEmptyDeployments(data)
                loadUnusedDesktops(data)
            });
    }

    function loadEmptyDeployments(data) {
        $('#suggestedRemovals #emptyDeployments').html(data['empty_deployments'].length)
        loadDatatable('#collapseEmptyDeployments', '#emptyDeploymentsTable', data['empty_deployments'], emptyDeploymentsCols)
        $('#collapseEmptyDeployments tfoot th').each(function () {
            var title = $(this).text();
            $(this).html('<input type="text" placeholder="Search ' + title + '" />');
        });

        // Aplicar el filtro en el pie
        table.columns().every(function () {
            var that = this;

            $('input', this.footer()).on('keyup change', function () {
                if (that.search() !== this.value) {
                    that
                        .search(this.value)
                        .draw();
                }
            });
        });
    }

    function loadUnusedDesktops(data) {
        $('#suggestedRemovals #unusedDesktops').html(data['unused_desktops']['desktops'].length)
        $('#suggestedRemovals #unusedDesktopsSize').html(data['unused_desktops']['size'].toFixed(2) )
        loadDatatable('#collapseUnusedDesktops', '#unusedDesktopsTable', data['unused_desktops']['desktops'], unusedDesktopsCols)
        $('#unusedDesktopsTable_filter').after('<button type="button" class="btn btn-danger pull-right btn-delete-all">Delete all</button>');
        $('#unusedDesktopsTable_wrapper .btn-delete-all').off('click').on('click', function() {
            new PNotify({
                title: 'Confirmation Needed',
                    text: "Are you sure you want to delete all the desktops in the table? The desktops will be sent to the recycle bin and could be restored.",
                    hide: false,
                    opacity: 0.9,
                    confirm: {
                        confirm: true
                    },
                    buttons: {
                        closer: false,
                        sticker: false
                    },
                    history: {
                        history: false
                    },
                    addclass: 'pnotify-center'
                }).get().on('pnotify.confirm', function() {
                    var ids = table.rows().data().toArray().map(function(rowData) {
                        return rowData.id;
                      });
                      deleteDesktops(ids)
                  });
                }).on('pnotify.cancel', function() {
            });
        $('#unusedDesktopsTable tbody').off('click').on('click', 'button', function () {
            var row = $(this).closest('table').DataTable().row($(this).closest('tr'));
            var id = row.data().id;
            if ($(this).hasClass('btn-delete-desktop')) {
                new PNotify({
                    title: 'Confirmation Needed',
                        text: "Are you sure you want to delete virtual desktop: " + row.data().name + "? The desktops will be sent to the recycle bin and could be restored.",
                        hide: false,
                        opacity: 0.9,
                        confirm: {
                            confirm: true
                        },
                        buttons: {
                            closer: false,
                            sticker: false
                        },
                        history: {
                            history: false
                        },
                        addclass: 'pnotify-center'
                    }).get().on('pnotify.confirm', function() {
                        deleteDesktops([id])
                    }).on('pnotify.cancel', function() {
                });
            }
        })
    
    }

    function deleteDesktops(ids) {
        $.ajax({
            type: "POST",
            url: "/api/v3/admin/multiple_actions",
            data: JSON.stringify({ 'ids': ids, 'action': 'delete' }),
            success: function () {
                location.reload()
            },
            error: function (data) {
                new PNotify({
                    title: 'ERROR deleting desktop',
                    text: data.responseJSON.description,
                    type: 'error',
                    hide: true,
                    icon: 'fa fa-warning',
                    delay: 5000,
                    opacity: 1
                })
            },
        });
    }

    function loadDatatable(collapseId, tableId, data, columns) {
        if ($.fn.dataTable.isDataTable(tableId)) {
            $(tableId).DataTable().destroy();
        } else {
            $(collapseId).collapse()
        }
        table = $(tableId).DataTable({
            data,
            columns
        })
        adminShowIdCol(table)
    }

    // function socketio_on(){
    //     socket.on('desktop_delete', function(data){
    //         var data = JSON.parse(data);
    //         if(!typeof($('#unusedDesktopsTable').DataTable().row('#'+data.id).id())=='undefined'){
    //             $('#unusedDesktopsTable').DataTable().row('#'+data.id).remove().draw();
    //         }
    //     });
    // }
})