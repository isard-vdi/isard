//
//   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
//   Copyright (C) 2023
//
//   This program is free software: you can redistribute it and/or modify
//   it under the terms of the GNU Affero General Public License as published by
//   the Free Software Foundation, either version 3 of the License, or
//   (at your option) any later version.
//
//   This program is distributed in the hope that it will be useful,
//   but WITHOUT ANY WARRANTY; without even the implied warranty of
//   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
//   GNU Affero General Public License for more details.
//
//   You should have received a copy of the GNU Affero General Public License
//   along with this program. If not, see <https://www.gnu.org/licenses/>.
//
// SPDX-License-Identifier: AGPL-3.0-or-later

//
// Pipelining function for DataTables. To be used to the `ajax` option of DataTables
//

$.fn.dataTable.pipeline = function ( opts ) {
    // Configuration options
    var conf = $.extend( {
        pages: 5,     // number of pages to cache
        url: '',      // script url
        data: null,   // function or object with parameters to send to the server
                      // matching how `ajax.data` works in DataTables
        method: 'GET' // Ajax HTTP method
    }, opts );

    // Private variables for storing the cache
    var cacheLower = -1;
    var cacheUpper = null;
    var cacheLastRequest = null;
    var cacheLastJson = null;

    return function ( request, drawCallback, settings ) {
        var ajax          = false;
        var requestStart  = request.start;
        var drawStart     = request.start;
        var requestLength = request.length;
        var requestEnd    = requestStart + requestLength;
        
        if ( settings.clearCache ) {
            // API requested that the cache be cleared
            ajax = true;
            settings.clearCache = false;
        }
        else if ( cacheLower < 0 || requestStart < cacheLower || requestEnd > cacheUpper ) {
            // outside cached data - need to make a request
            ajax = true;
        }
        else if ( JSON.stringify( request.order )   !== JSON.stringify( cacheLastRequest.order ) ||
                  JSON.stringify( request.columns ) !== JSON.stringify( cacheLastRequest.columns ) ||
                  JSON.stringify( request.search )  !== JSON.stringify( cacheLastRequest.search )
        ) {
            // properties changed (ordering, columns, searching)
            ajax = true;
        }
        
        // Store the request for checking next time around
        cacheLastRequest = $.extend( true, {}, request );

        if ( ajax ) {
            // Need data from the server
            if ( requestStart < cacheLower ) {
                requestStart = requestStart - (requestLength*(conf.pages-1));

                if ( requestStart < 0 ) {
                    requestStart = 0;
                }
            }
            
            cacheLower = requestStart;
            cacheUpper = requestStart + (requestLength * conf.pages);

            request.start = requestStart;
            request.length = requestLength*conf.pages;

            // Provide the same `data` options as DataTables.
            if ( typeof conf.data === 'function' ) {
                // As a function it is executed with the data object as an arg
                // for manipulation. If an object is returned, it is used as the
                // data object to submit
                var d = conf.data( request );
                if ( d ) {
                    $.extend( request, d );
                }
            }
            else if ( $.isPlainObject( conf.data ) ) {
                // As an object, the data given extends the default
                $.extend( request, conf.data );
            }

            return $.ajax( {
                "type":     conf.method,
                "url":      conf.url,
                "data":     request,
                "dataType": "json",
                "cache":    false,
                "success":  function ( json ) {
                    cacheLastJson = $.extend(true, {}, json);

                    if ( cacheLower != drawStart ) {
                        json.data.splice( 0, drawStart-cacheLower );
                    }
                    if ( requestLength >= -1 ) {
                        json.data.splice( requestLength, json.data.length );
                    }
                    
                    drawCallback( json );
                }
            } );
        }
        else {
            json = $.extend( true, {}, cacheLastJson );
            json.draw = request.draw; // Update the echo for each response
            json.data.splice( 0, requestStart-cacheLower );
            json.data.splice( requestLength, json.data.length );

            drawCallback(json);
        }
    }
};

// Register an API method that will empty the pipelined data, forcing an Ajax
// fetch on the next draw (i.e. `table.clearPipeline().draw()`)
$.fn.dataTable.Api.register( 'clearPipeline()', function () {
    return this.iterator( 'table', function ( settings ) {
        settings.clearCache = true;
    } );
} );
 
logs_desktops_raw_table = null;
logs_desktops_desktop_table = null;

$(document).ready(function () {
    $(".nav-link").click(function(e){
        if ($(this).attr('id') == 'btn-raw-view-tab'){
            if (logs_desktops_raw_table == null){
                raw_table();
            }else{
                logs_desktops_raw_table.clearPipeline().draw();
            }
        }
        if ($(this).attr('id') == 'btn-desktop-view-tab'){
            if (logs_desktops_desktop_table == null){
                desktop_table();
            }else{
                logs_desktops_desktop_table.clearPipeline().draw();
            }
        }
    });
});

function raw_table(){
    logs_desktops_raw_table = $('#table-logs-desktops').DataTable({
        serverSide: true,
		responsive: true,
        autoWidth: false,
        ajax: $.fn.dataTable.pipeline({
            url: "/api/v3/admin/logs_desktops",
            pages: 5, // number of pages to cache
            method: 'POST',
        }),
        columns: [
            {
                "className": 'details-control',
                "orderable": false,
                "data": null,
                "width": "10px",
                "defaultContent": '<button class="btn btn-xs btn-info" type="button" data-placement="top" ><i class="fa fa-plus"></i></button>'
            },
            { "data": "starting_time"},
            { "data": "desktop_name"},
            { "data": "owner_user_name"},
            { "data": "owner_group_name"},
            { "data": "owner_category_name"},
        ],
        order: [[1, "asc"]], // Should be a column with a db index!
        initComplete: function (settings, json) {
			let table = this.api()
            this.api()
                .columns()
                .every(function () {
                    let column = this;
					let columnDataField = column.settings().init().columns[column.index()].data;
					if ( ! column.header().classList.contains('sorting_disabled') && $.inArray(columnDataField, json.indexs) > -1 ){
						let input = document.createElement('input');
						column.header().appendChild(input);
						input.addEventListener('click', (event) => {
							event.stopPropagation();
						});

						let debouncedKeyUp = debounce(function () {
							if (column.search() !== input.value) {
								column.search(input.value).draw();
							}
						}, 1000);

						input.addEventListener('keyup', debouncedKeyUp);
					}else{
						// TODO: remove sort event and icon
					}
				});

				$(table.table().container()).on('processing.dt', function (e, settings, processing) {
					if (processing) {
						$(this).addClass('loading');
	
						// Create and append the overlay with spinner
						let overlay = document.createElement('div');
						overlay.className = 'overlay';
						overlay.innerHTML = '<div class="text-primary" role="status"><i class="fa fa-spinner fa-spin fa-5x fa-fw"></i></div>';
						this.appendChild(overlay);
					} else {
						$(this).removeClass('loading');
						$(this).find('.overlay').remove();
					}
				});
        }
    });
}

function desktop_table(){
    logs_desktops_desktop_table = $('#table-logs-desktops-desktop-view').DataTable({
        serverSide: true,
		responsive: true,
        autoWidth: false,
        processing: true,
        ajax: $.fn.dataTable.pipeline({
            url: "/api/v3/admin/logs_desktops/desktops_view",
            pages: 5, // number of pages to cache
            method: 'POST',
        }),
        columns: [
            {
                "className": 'details-control',
                "orderable": false,
                "data": null,
                "width": "10px",
                "defaultContent": '<button class="btn btn-xs btn-info" type="button" data-placement="top" ><i class="fa fa-plus"></i></button>'
            },
            { "data": "desktop_name"},
            { "data": "starting_time"},
            { "data": "owner_user_name"},
            { "data": "owner_group_name"},
            { "data": "owner_category_name"},
        ],
        order: [[1, "asc"]], // Should be a column with a db index!
        initComplete: function (settings, json) {
			let table = this.api()
            this.api()
                .columns()
                .every(function () {
                    let column = this;
					let columnDataField = column.settings().init().columns[column.index()].data;
					if ( ! column.header().classList.contains('sorting_disabled') && $.inArray(columnDataField, json.indexs) > -1 ){
						let input = document.createElement('input');
						column.header().appendChild(input);
						input.addEventListener('click', (event) => {
							event.stopPropagation();
						});

						let debouncedKeyUp = debounce(function () {
							if (column.search() !== input.value) {
								column.search(input.value).draw();
							}
						}, 1000);

						input.addEventListener('keyup', debouncedKeyUp);
					}else{
						// TODO: remove sort event and icon
					}
				});

				$(table.table().container()).on('processing.dt', function (e, settings, processing) {
					if (processing) {
						$(this).addClass('loading');
	
						// Create and append the overlay with spinner
						let overlay = document.createElement('div');
						overlay.className = 'overlay';
						overlay.innerHTML = '<div class="text-primary" role="status"><i class="fa fa-spinner fa-spin fa-5x fa-fw"></i></div>';
						this.appendChild(overlay);
					} else {
						$(this).removeClass('loading');
						$(this).find('.overlay').remove();
					}
				});
        }
    });
}


function debounce(fn, delay) {
    let timeoutId;
    return function () {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => {
            fn.apply(this, arguments);
        }, delay);
    };
}