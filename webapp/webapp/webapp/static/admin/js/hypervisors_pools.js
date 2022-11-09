/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$hypervisor_pool_template = $(".hyper-pool-detail");
var tablepools;
$(document).ready(function() {

    tablepools = $('#hypervisors_pools').DataTable( {
        "ajax": {
            "url": "/admin/table/hypervisors_pools",
            "method": "POST",
            "data": function(d){return JSON.stringify({'order_by':'name'})},
            "dataSrc": ""
        },
        "rowId": "id",
        "deferRender": false,
        "columns": [
                {
                "className":      'details-control',
                "orderable":      false,
                "data":           null,
                "width": "10px",
                "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
                },
            { "data": "name"},
            { "data": "description"}]
    } );

    $('#hypervisors_pools').find('tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        var row = tablepools.row( tr );

        if ( row.child.isShown() ) {
            // This row is already open - close it
            row.child.hide();
            tr.removeClass('shown');
        }
        else {
            // Open this row
            row.child( formatHypervisorPool(row.data()) ).show();
            data = row.data();
            $.each( data['paths'], function( k, v) {
                $.each( data['paths'][k], function( key, val ) {
                    $('#hyper-pools-paths-'+data.id+' tbody').append('<tr><td>'+k+'</td><td>'+val['path']+'</td><td>'+val['disk_operations']+'</td><td>'+val['weight']+'</td></tr>');
                });
            });
            if(data['interfaces'].length==0){
                $('#hyper-pools-nets-'+data.id+' tbody').append('[All interfaces available for selection]')
            }else{
                $.each( data['interfaces'], function( k, v) {
                    $.each( data['interfaces'][k], function( key, val ) {
                        $('#hyper-pools-nets-'+data.id+' tbody').append('<tr><td>'+k+'</td><td>'+key+'</td><td>'+val['disk_operations']+'</td><td>'+val['weight']+'</td></tr>');
                    });
                });
            }
            if(data['viewer']['certificate'].length >10){data['viewer']['certificate']='Yes';}
            $('#hyper-pools-viewer-'+data.id+' tbody').append('<tr><td>'+data['viewer']['defaultMode']+'</td><td>'+data['viewer']['domain']+'</td><td>'+data['viewer']['certificate']
            );
            tr.addClass('shown');

        }
    } );




});// document ready

function formatHypervisorPool ( d ) {
        $newPanel = $hypervisor_pool_template.clone();
        $newPanel.html(function(i, oldHtml){
            return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name);
        });
        return $newPanel
}


function table2json(){
                            var newFormData = [];
                              $('#datatable_paths tr:not(:first)').each(function(i) {
                                var tb = jQuery(this);
                                var obj = {};
                                tb.find('input').each(function() {
                                  obj[this.name] = this.value;
                                });
                                newFormData.push(obj);
                              });


}
